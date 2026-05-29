import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from . import config

FlowTargetsMap = Dict[str, Dict[str, List[str]]]


def _split_combo(combo: str) -> Tuple[str, str]:
    parts = combo.split(" | ", 1)
    name = parts[0].strip()
    category = parts[1].strip() if len(parts) > 1 else ""
    return name, category


def _extract_flow_analyses(payload: Any, process_id: str) -> List[Dict[str, Any]]:
    if isinstance(payload, dict):
        if isinstance(payload.get(process_id), list):
            return [item for item in payload[process_id] if isinstance(item, dict)]
        if isinstance(payload.get("flow_analyses"), list):
            return [item for item in payload["flow_analyses"] if isinstance(item, dict)]
    return []


def _is_neutral(relationship: Any) -> bool:
    if not isinstance(relationship, str):
        return False
    return relationship.strip().lower() == "neutral"


def _extract_completed_pairs_from_existing(payload: Any, process_id: str) -> Dict[str, set[str]]:
    flow_analyses = _extract_flow_analyses(payload, process_id)
    completed: Dict[str, set[str]] = {}
    for flow_analysis in flow_analyses:
        flow_combo = flow_analysis.get("flow_combo")
        if not flow_combo:
            continue
        bucket = completed.setdefault(flow_combo, set())
        for ghg_analysis in flow_analysis.get("individual_ghg_analyses") or []:
            if not isinstance(ghg_analysis, dict):
                continue
            ghg_combo = ghg_analysis.get("ghg_combo")
            if ghg_combo:
                bucket.add(ghg_combo)
    return completed


def _all_target_pairs_completed(
    existing_payload: Any,
    process_id: str,
    process_flow_targets: Dict[str, List[str]],
) -> bool:
    completed_pairs = _extract_completed_pairs_from_existing(existing_payload, process_id)
    for flow_combo, target_ghgs in process_flow_targets.items():
        completed_for_flow = completed_pairs.get(flow_combo, set())
        if any(ghg_combo not in completed_for_flow for ghg_combo in target_ghgs):
            return False
    return True


def load_static_data(exclude_results_dir: Path) -> Tuple[List[str], FlowTargetsMap]:
    """
    从历史模型结果中加载待分析的过程、flow 和 ghg 对。
    规则：
    1) 以 SOURCE_RESULTS_DIR 下的 JSON 作为候选集；
    2) 排除 exclude_results_dir 中已存在结果文件的 process_id；
    3) 仅保留 qualitative_relationship != Neutral 的 (flow_combo, ghg_combo)。
    这个函数应该在主循环开始前只调用一次。
    
    Returns:
        A tuple containing:
        - a list of process IDs to be analyzed.
        - a dictionary mapping each process ID to flow targets:
          {process_id: {flow_combo: [ghg_combo, ...]}}.
    """
    print("[*] Loading static data...")
    source_results_dir = config.SOURCE_RESULTS_DIR

    if not source_results_dir.exists():
        raise FileNotFoundError(f"Source results dir does not exist: {source_results_dir}")

    flow_targets_map: FlowTargetsMap = {}
    source_files = sorted(source_results_dir.glob("*.json"))
    fully_completed_in_exclude = 0
    partially_completed_in_exclude = 0
    failed_existing_output_loads = 0

    for source_file in source_files:
        process_id = source_file.stem

        try:
            with source_file.open("r", encoding="utf-8") as handle:
                payload = json.load(handle)
        except Exception as exc:
            print(f"[!] Warning: failed to load {source_file}: {exc}")
            continue

        flow_analyses = _extract_flow_analyses(payload, process_id)
        if not flow_analyses:
            continue

        process_flow_targets: Dict[str, List[str]] = {}
        for flow_analysis in flow_analyses:
            flow_combo = flow_analysis.get("flow_combo")
            if not flow_combo:
                continue

            ghg_targets = process_flow_targets.setdefault(flow_combo, [])
            seen_ghgs = set(ghg_targets)

            for ghg_analysis in flow_analysis.get("individual_ghg_analyses") or []:
                if not isinstance(ghg_analysis, dict):
                    continue
                if _is_neutral(ghg_analysis.get("qualitative_relationship")):
                    continue
                ghg_combo = ghg_analysis.get("ghg_combo")
                if not ghg_combo or ghg_combo in seen_ghgs:
                    continue
                ghg_targets.append(ghg_combo)
                seen_ghgs.add(ghg_combo)

        process_flow_targets = {
            flow_combo: ghg_list
            for flow_combo, ghg_list in process_flow_targets.items()
            if ghg_list
        }
        if not process_flow_targets:
            continue

        existing_output_path = exclude_results_dir / f"{process_id}.json"
        if existing_output_path.exists():
            try:
                with existing_output_path.open("r", encoding="utf-8") as handle:
                    existing_payload = json.load(handle)
            except Exception as exc:
                failed_existing_output_loads += 1
                print(f"[!] Warning: failed to load existing output {existing_output_path}: {exc}")
                flow_targets_map[process_id] = process_flow_targets
                continue

            if _all_target_pairs_completed(existing_payload, process_id, process_flow_targets):
                fully_completed_in_exclude += 1
                continue
            partially_completed_in_exclude += 1

        flow_targets_map[process_id] = process_flow_targets

    process_ids = list(flow_targets_map.keys())
    print(
        "[+] Static data loaded successfully. "
        f"source_files={len(source_files)} "
        f"excluded_fully_completed_processes={fully_completed_in_exclude} "
        f"included_partially_completed_processes={partially_completed_in_exclude} "
        f"failed_existing_output_loads={failed_existing_output_loads} "
        f"selected_processes={len(process_ids)}"
    )
    return process_ids, flow_targets_map


def fetch_data_for_process(
    process_id: str,
    flow_targets_map: FlowTargetsMap,
) -> Optional[Tuple[Dict[str, Any], List[Dict[str, Any]]]]:
    """
    为单个给定的process_id提取其特定的数据，并筛选出相关的GHG。

    Args:
        process_id: 需要分析的单元过程的ID。
        flow_targets_map: 包含所有过程及其对应待分析 flow->ghg 映射的字典。

    Returns:
        一个元组，包含 (过程JSON对象, 此过程待分析的flows列表)。
        如果找不到对应的JSON文件，则返回 None。
    """
    print(f"[*] Fetching data for process: {process_id}")
    
    # 1. 获取此过程需要分析的 elementary flows 组合列表
    process_flow_targets = flow_targets_map.get(process_id, {})
    
    # 如果没有为这个过程定义需要分析的flow，可以提前返回
    if not process_flow_targets:
        print(f"[!] Warning: No target flows defined for process {process_id}. Skipping.")
        return None

    # 2. 构造待分析flows的结构化列表
    target_flows = []
    for combo, ghg_combos in process_flow_targets.items():
        flow_name, flow_category = _split_combo(combo)
        target_flows.append(
            {
                'flow_combo': combo,
                'flow_name': flow_name,
                'flow_category': flow_category,
                'ghg_combos': ghg_combos,
            }
        )

    # 3. 读取该过程对应的JSON文件内容
    process_json_path = config.PROCESS_JSONS_DIR / f"{process_id}.json"
    
    try:
        with open(process_json_path, 'r', encoding='utf-8') as f:
            process_data = json.load(f)
    except FileNotFoundError:
        print(f"[X] Error: JSON file not found for process {process_id} at {process_json_path}")
        return None
    except Exception as e:
        print(f"[X] Error reading JSON file for {process_id}: {e}")
        return None
    
    total_pairs = sum(len(item.get("ghg_combos") or []) for item in target_flows)
    print(
        f"[+] Successfully fetched data and found "
        f"{len(target_flows)} target flows / {total_pairs} target pairs for {process_id}."
    )

    return (process_data, target_flows)
