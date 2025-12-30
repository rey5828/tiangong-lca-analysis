import json
from typing import Dict, List, Tuple, Any, Optional

from . import config

FlowMap = Dict[str, List[str]]


def _split_combo(combo: str) -> Tuple[str, str]:
    parts = combo.split(" | ", 1)
    name = parts[0].strip()
    category = parts[1].strip() if len(parts) > 1 else ""
    return name, category


def load_static_data() -> Tuple[List[str], FlowMap, List[str]]:
    """
    加载在整个运行过程中保持不变的静态数据。
    这包括过程ID列表、待分析Flows的映射和GHG列表。
    这个函数应该在主循环开始前只调用一次。
    
    Returns:
        A tuple containing:
        - a list of process IDs to be analyzed.
        - a dictionary mapping each process ID to its target flow combo strings.
        - a list of all canonical GHG flow combos.
    """
    print("[*] Loading static data...")

    # 加载过程列表
    with open(config.PROCESS_LIST_PATH, 'r', encoding='utf-8') as f:
        process_ids = json.load(f)

    # 加载待分析Flows的完整映射（process_id -> ["name | category", ...]）
    with open(config.FLOWS_TO_ANALYZE_PATH, 'r', encoding='utf-8') as f:
        flows_to_analyze_map = json.load(f)

    # 加载所有GHG组合字符串
    with open(config.GHG_LIST_PATH, 'r', encoding='utf-8') as f:
        ghg_combos = json.load(f)

    print("[+] Static data loaded successfully.")
    return process_ids, flows_to_analyze_map, ghg_combos


def fetch_data_for_process(
    process_id: str,
    flows_map: FlowMap,
    ghg_combos: List[str],
) -> Optional[Tuple[Dict[str, Any], Dict[str, List[Dict[str, Any]]], List[Dict[str, Any]], str, List[str]]]:
    """
    为单个给定的process_id提取其特定的数据，并筛选出相关的GHG。

    Args:
        process_id: 需要分析的单元过程的ID。
        flows_map: 包含所有过程及其对应待分析flow组合的字典。
        ghg_combos: 所有GHG组合信息列表。

    Returns:
        一个元组，包含 (过程数据字典, exchange映射, 此过程待分析的flows列表, 与此过程相关的GHG列表字符串, 相关GHG组合列表)。
        如果找不到对应的JSON文件，则返回 None。
    """
    print(f"[*] Fetching data for process: {process_id}")
    
    # 1. 获取此过程需要分析的 elementary flows 组合列表
    original_target_flows = flows_map.get(process_id, [])
    
    # 如果没有为这个过程定义需要分析的flow，可以提前返回
    if not original_target_flows:
        print(f"[!] Warning: No target flows defined for process {process_id}. Skipping.")
        return None

    # 2. 构造待分析flows的结构化列表
    target_flows = []
    for combo in original_target_flows:
        flow_name, flow_category = _split_combo(combo)
        target_flows.append(
            {
                'flow_combo': combo,
                'flow_name': flow_name,
                'flow_category': flow_category,
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
    
    # 4. 筛选与此过程相关的GHG
    relevant_ghgs: List[str] = []
    ghg_combo_set = set(ghg_combos)

    exchange_map: Dict[str, List[Dict[str, Any]]] = {}

    for exchange in process_data.get('exchanges', []):
        is_emission = not exchange.get('isInput', True)
        flow = exchange.get('flow', {})
        flow_name = flow.get('name')
        flow_category = flow.get('category')

        # 在压缩后的JSON里，输出elementary flows通常只包含 name 与 category
        if not (is_emission and flow_name and flow_category):
            continue

        combo = f"{flow_name} | {flow_category}"
        if combo in ghg_combo_set and combo not in relevant_ghgs:
            relevant_ghgs.append(combo)

        # 为后续 prompt 压缩构建 exchange 映射
        entry = {
            "is_input": exchange.get("isInput", True),
            "amount": exchange.get("amount"),
            "unit": (exchange.get("unit") or {}).get("name"),
            "flow_type": flow.get("flowType"),
            "location": exchange.get("location"),
        }
        exchange_map.setdefault(combo, []).append(entry)
    
    if not relevant_ghgs:
        print(f"[!] Warning: No relevant GHGs found in process {process_id}. The GHG list for the prompt will be empty.")
        # 即使为空，我们仍然可以继续，让模型知道这个过程没有GHG排放
    
    # 5. 格式化筛选后的GHG列表以注入Prompt
    if relevant_ghgs:
        relevant_ghg_list_str = "\n".join([f"- {combo}" for combo in relevant_ghgs])
    else:
        relevant_ghg_list_str = "- None"


    print(f"[+] Successfully fetched data and found {len(relevant_ghgs)} relevant GHGs for {process_id}.")

    return (process_data, exchange_map, target_flows, relevant_ghg_list_str, relevant_ghgs)
