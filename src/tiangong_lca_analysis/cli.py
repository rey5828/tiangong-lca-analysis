import json
import logging
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, Iterable, List

# Ensure package root is on sys.path when running as a script.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from tiangong_lca_analysis.agents import config
from tiangong_lca_analysis.agents.data_fetcher import fetch_data_for_process, load_static_data
from tiangong_lca_analysis.agents.lca_analyst import LCAAnalystAgent


def safe_model_name_for_path(model_name: str) -> str:
    return model_name.replace("/", "_")


def chunked(items: List[str], chunk_size: int) -> Iterable[List[str]]:
    for index in range(0, len(items), chunk_size):
        yield items[index : index + chunk_size]


def configure_logging() -> Path:
    log_dir = Path(config.ROOT_DIR) / "logs"
    log_dir.mkdir(exist_ok=True, parents=True)
    log_filepath = log_dir / f"lca_analysis_{time.strftime('%Y%m%d_%H%M%S')}.log"

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[
            logging.FileHandler(log_filepath, encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
        force=True,
    )
    logging.info("Logging to file: %s", log_filepath)
    return log_filepath


def atomic_write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    with temp_path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=4, ensure_ascii=False)
    temp_path.replace(path)


def load_existing_flow_results(output_path: Path, process_id: str) -> Dict[str, Dict[str, Any]]:
    if not output_path.exists():
        return {}

    try:
        with output_path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except Exception as exc:
        logging.warning("[%s] Failed to load existing output %s: %s", process_id, output_path, exc)
        return {}

    if isinstance(payload, dict) and process_id in payload and isinstance(payload[process_id], list):
        flow_analyses = payload[process_id]
    elif isinstance(payload, dict) and isinstance(payload.get("flow_analyses"), list):
        flow_analyses = payload["flow_analyses"]
    else:
        logging.warning("[%s] Existing output %s has an unexpected structure. Ignoring it.", process_id, output_path)
        return {}

    normalized: Dict[str, Dict[str, Any]] = {}
    for flow_analysis in flow_analyses:
        if not isinstance(flow_analysis, dict):
            continue
        flow_combo = flow_analysis.get("flow_combo")
        if not flow_combo:
            continue

        entry = normalized.setdefault(
            flow_combo,
            {
                "process_id": flow_analysis.get("process_id") or process_id,
                "flow_combo": flow_combo,
                "individual_ghg_analyses": [],
            },
        )

        ghg_map = {
            item.get("ghg_combo"): item
            for item in entry.get("individual_ghg_analyses") or []
            if isinstance(item, dict) and item.get("ghg_combo")
        }
        for ghg_analysis in flow_analysis.get("individual_ghg_analyses") or []:
            if isinstance(ghg_analysis, dict) and ghg_analysis.get("ghg_combo"):
                ghg_map[ghg_analysis["ghg_combo"]] = ghg_analysis
        entry["individual_ghg_analyses"] = list(ghg_map.values())
        entry["process_id"] = flow_analysis.get("process_id") or process_id

    return normalized


def merge_flow_results_maps(
    primary_map: Dict[str, Dict[str, Any]],
    secondary_map: Dict[str, Dict[str, Any]],
    process_id: str,
) -> Dict[str, Dict[str, Any]]:
    merged: Dict[str, Dict[str, Any]] = {}
    flow_keys = set(primary_map) | set(secondary_map)

    for flow_combo in flow_keys:
        flow_entries = [
            entry
            for entry in (primary_map.get(flow_combo), secondary_map.get(flow_combo))
            if isinstance(entry, dict)
        ]
        if not flow_entries:
            continue

        ghg_map: Dict[str, Dict[str, Any]] = {}
        for flow_entry in flow_entries:
            for ghg_analysis in flow_entry.get("individual_ghg_analyses") or []:
                ghg_combo = ghg_analysis.get("ghg_combo") if isinstance(ghg_analysis, dict) else None
                if ghg_combo:
                    ghg_map[ghg_combo] = ghg_analysis

        merged[flow_combo] = {
            "process_id": flow_entries[0].get("process_id") or process_id,
            "flow_combo": flow_combo,
            "individual_ghg_analyses": list(ghg_map.values()),
        }

    return merged


def build_completed_pairs_map(
    flow_results_map: Dict[str, Dict[str, Any]],
    relevant_ghgs: List[str],
) -> Dict[str, set[str]]:
    relevant_ghg_set = set(relevant_ghgs)
    completed: Dict[str, set[str]] = {}
    for flow_combo, flow_analysis in flow_results_map.items():
        completed[flow_combo] = {
            item.get("ghg_combo")
            for item in flow_analysis.get("individual_ghg_analyses") or []
            if item.get("ghg_combo") in relevant_ghg_set
        }
    return completed


def count_completed_pairs(completed_pairs_map: Dict[str, set[str]]) -> int:
    return sum(len(item) for item in completed_pairs_map.values())


def order_flow_results(
    flow_results_map: Dict[str, Dict[str, Any]],
    target_flows: List[Dict[str, str]],
    relevant_ghgs: List[str],
) -> List[Dict[str, Any]]:
    ghg_order = {ghg: index for index, ghg in enumerate(relevant_ghgs)}
    ordered_results: List[Dict[str, Any]] = []

    for flow_info in target_flows:
        flow_combo = flow_info["flow_combo"]
        flow_analysis = flow_results_map.get(flow_combo)
        if not flow_analysis:
            continue

        ghg_analyses = list(flow_analysis.get("individual_ghg_analyses") or [])
        ghg_analyses.sort(
            key=lambda item: (
                ghg_order.get(item.get("ghg_combo"), len(ghg_order)),
                item.get("ghg_combo") or "",
            )
        )

        ordered_results.append(
            {
                "process_id": flow_analysis.get("process_id"),
                "flow_combo": flow_combo,
                "individual_ghg_analyses": ghg_analyses,
            }
        )

    return ordered_results


def save_process_results(
    output_path: Path,
    process_id: str,
    flow_results_map: Dict[str, Dict[str, Any]],
    target_flows: List[Dict[str, str]],
    relevant_ghgs: List[str],
) -> None:
    atomic_write_json(
        output_path,
        {process_id: order_flow_results(flow_results_map, target_flows, relevant_ghgs)},
    )


def merge_flow_chunk_result(
    flow_results_map: Dict[str, Dict[str, Any]],
    process_id: str,
    flow_combo: str,
    ghg_chunk: List[str],
    chunk_result: Dict[str, Any],
) -> int:
    entry = flow_results_map.setdefault(
        flow_combo,
        {
            "process_id": process_id,
            "flow_combo": flow_combo,
            "individual_ghg_analyses": [],
        },
    )

    ghg_map = {
        item.get("ghg_combo"): item
        for item in entry.get("individual_ghg_analyses") or []
        if isinstance(item, dict) and item.get("ghg_combo")
    }

    new_items = 0
    for ghg_analysis in chunk_result.get("individual_ghg_analyses") or []:
        ghg_combo = ghg_analysis.get("ghg_combo")
        if ghg_combo not in ghg_chunk:
            continue
        if ghg_combo not in ghg_map:
            new_items += 1
        ghg_map[ghg_combo] = ghg_analysis

    entry["process_id"] = chunk_result.get("process_id") or process_id
    entry["flow_combo"] = flow_combo
    entry["individual_ghg_analyses"] = list(ghg_map.values())
    return new_items


def build_empty_flow_results(process_id: str, target_flows: List[Dict[str, str]]) -> Dict[str, Dict[str, Any]]:
    return {
        flow_info["flow_combo"]: {
            "process_id": process_id,
            "flow_combo": flow_info["flow_combo"],
            "individual_ghg_analyses": [],
        }
        for flow_info in target_flows
    }


def process_single_process(
    model_name: str,
    process_id: str,
    flows_to_analyze_map: Dict[str, List[str]],
    ghg_combos: List[str],
    model_results_dir: Path,
    legacy_output_path: Path | None = None,
) -> Dict[str, Any]:
    output_path = model_results_dir / f"{process_id}.json"
    status_payload = {
        "process_id": process_id,
        "status": "failed",
        "expected_pairs": 0,
        "completed_pairs": 0,
    }

    try:
        process_data_package = fetch_data_for_process(process_id, flows_to_analyze_map, ghg_combos)
        if not process_data_package:
            status_payload["status"] = "skipped_no_target_flows"
            return status_payload

        process_data, target_flows, relevant_ghgs = process_data_package
        expected_total_pairs = len(target_flows) * len(relevant_ghgs)
        status_payload["expected_pairs"] = expected_total_pairs

        flow_results_map = load_existing_flow_results(output_path, process_id)
        if legacy_output_path and legacy_output_path != output_path:
            legacy_flow_results_map = load_existing_flow_results(legacy_output_path, process_id)
            flow_results_map = merge_flow_results_maps(
                flow_results_map,
                legacy_flow_results_map,
                process_id,
            )

        if flow_results_map and not output_path.exists():
            save_process_results(output_path, process_id, flow_results_map, target_flows, relevant_ghgs)

        completed_pairs_map = build_completed_pairs_map(flow_results_map, relevant_ghgs)
        completed_total_pairs = count_completed_pairs(completed_pairs_map)

        logging.info(
            "[%s] Starting process analysis. target_flows=%s relevant_ghgs=%s completed_pairs=%s/%s",
            process_id,
            len(target_flows),
            len(relevant_ghgs),
            completed_total_pairs,
            expected_total_pairs,
        )

        if not relevant_ghgs:
            if not flow_results_map:
                flow_results_map = build_empty_flow_results(process_id, target_flows)
                save_process_results(output_path, process_id, flow_results_map, target_flows, relevant_ghgs)
            status_payload["status"] = "completed_no_ghgs"
            return status_payload

        if completed_total_pairs >= expected_total_pairs:
            logging.info("[%s] All %s pairs already completed. Skipping.", process_id, expected_total_pairs)
            status_payload["status"] = "skipped_complete"
            status_payload["completed_pairs"] = completed_total_pairs
            return status_payload

        analyst = LCAAnalystAgent(model_name=model_name)
        flow_count = len(target_flows)
        relevant_ghg_set = set(relevant_ghgs)
        state_lock = threading.Lock()
        progress = {"completed_pairs": completed_total_pairs}

        def process_single_flow(flow_index: int, flow_info: Dict[str, str]) -> None:
            flow_combo = flow_info["flow_combo"]
            with state_lock:
                completed_for_flow = set(completed_pairs_map.setdefault(flow_combo, set()))
            remaining_ghgs = [ghg for ghg in relevant_ghgs if ghg not in completed_for_flow]

            if not remaining_ghgs:
                return

            ghg_chunks = list(chunked(remaining_ghgs, config.MAX_GHGS_PER_CALL))
            logging.info(
                "[%s] Flow %s/%s '%s' has %s remaining GHGs across %s chunk(s).",
                process_id,
                flow_index,
                flow_count,
                flow_combo,
                len(remaining_ghgs),
                len(ghg_chunks),
            )

            for chunk_index, ghg_chunk in enumerate(ghg_chunks, start=1):
                chunk_remaining = [ghg for ghg in ghg_chunk if ghg not in completed_for_flow]
                if not chunk_remaining:
                    continue

                for attempt in range(1, config.MAX_CHUNK_RETRIES + 1):
                    logging.info(
                        "[%s] Flow %s/%s chunk %s/%s attempt %s. Remaining chunk GHGs=%s",
                        process_id,
                        flow_index,
                        flow_count,
                        chunk_index,
                        len(ghg_chunks),
                        attempt,
                        len(chunk_remaining),
                    )

                    try:
                        chunk_result = analyst.analyze_flow_chunk(
                            process_id=process_id,
                            process_data=process_data,
                            flow_info=flow_info,
                            ghg_chunk=chunk_remaining,
                        )
                    except Exception as exc:
                        logging.warning(
                            "[%s] Flow %s/%s chunk %s/%s attempt %s failed: %s",
                            process_id,
                            flow_index,
                            flow_count,
                            chunk_index,
                            len(ghg_chunks),
                            attempt,
                            exc,
                        )
                        continue

                    with state_lock:
                        new_items = merge_flow_chunk_result(
                            flow_results_map=flow_results_map,
                            process_id=process_id,
                            flow_combo=flow_combo,
                            ghg_chunk=chunk_remaining,
                            chunk_result=chunk_result,
                        )
                        completed_for_flow = {
                            item.get("ghg_combo")
                            for item in flow_results_map.get(flow_combo, {}).get("individual_ghg_analyses") or []
                            if item.get("ghg_combo") in relevant_ghg_set
                        }
                        completed_pairs_map[flow_combo] = completed_for_flow
                        progress["completed_pairs"] += new_items
                        completed_total_pairs_local = progress["completed_pairs"]
                        save_process_results(
                            output_path,
                            process_id,
                            flow_results_map,
                            target_flows,
                            relevant_ghgs,
                        )

                    missing_after_attempt = [ghg for ghg in chunk_remaining if ghg not in completed_for_flow]
                    logging.info(
                        "[%s] Flow %s/%s chunk %s/%s saved. New pairs=%s process_pairs=%s/%s missing_in_chunk=%s",
                        process_id,
                        flow_index,
                        flow_count,
                        chunk_index,
                        len(ghg_chunks),
                        new_items,
                        completed_total_pairs_local,
                        expected_total_pairs,
                        len(missing_after_attempt),
                    )

                    chunk_remaining = missing_after_attempt
                    if not chunk_remaining:
                        break

                if chunk_remaining:
                    logging.warning(
                        "[%s] Chunk %s/%s for flow '%s' still missing %s GHG pair(s) after retries: %s",
                        process_id,
                        chunk_index,
                        len(ghg_chunks),
                        flow_combo,
                        len(chunk_remaining),
                        chunk_remaining,
                    )

        flows_to_schedule = list(enumerate(target_flows, start=1))
        per_process_workers = max(
            1,
            min(
                config.MAX_CONCURRENT_FLOWS_PER_PROCESS,
                len(flows_to_schedule),
            ),
        )
        logging.info(
            "[%s] Using up to %s concurrent flow worker(s) inside this process.",
            process_id,
            per_process_workers,
        )

        with ThreadPoolExecutor(max_workers=per_process_workers) as flow_executor:
            future_to_flow = {
                flow_executor.submit(process_single_flow, flow_index, flow_info): (flow_index, flow_info["flow_combo"])
                for flow_index, flow_info in flows_to_schedule
            }
            for future in as_completed(future_to_flow):
                flow_index, flow_combo = future_to_flow[future]
                try:
                    future.result()
                except Exception as exc:
                    logging.error(
                        "[%s] Flow %s/%s '%s' worker crashed: %s",
                        process_id,
                        flow_index,
                        flow_count,
                        flow_combo,
                        exc,
                        exc_info=True,
                    )

        with state_lock:
            completed_total_pairs = progress["completed_pairs"]
        status_payload["completed_pairs"] = completed_total_pairs
        status_payload["status"] = (
            "completed" if completed_total_pairs >= expected_total_pairs else "partial"
        )

        logging.info(
            "[%s] Finished with status=%s completed_pairs=%s/%s",
            process_id,
            status_payload["status"],
            completed_total_pairs,
            expected_total_pairs,
        )
        return status_payload

    except Exception as exc:
        logging.error("[%s] Unexpected error: %s", process_id, exc, exc_info=True)
        return status_payload


def run_pipeline() -> None:
    print("=============================================")
    print("===  LCA Analysis Pipeline Starting...    ===")

    configure_logging()

    try:
        process_ids, flows_to_analyze_map, ghg_combos = load_static_data()
    except Exception as exc:
        logging.critical("Critical error during static data loading: %s", exc, exc_info=True)
        return

    for model_name in config.MODELS_TO_RUN:
        model_path_name = safe_model_name_for_path(model_name)
        model_results_dir = config.RESULTS_JSON_DIR / model_path_name
        model_results_dir.mkdir(exist_ok=True, parents=True)
        seed_model_name = os.getenv("LCA_SEED_MODEL_NAME", "Qwen/Qwen3.5-397B-A17B-GPTQ-Int4")
        seed_results_dir = config.RESULTS_JSON_DIR / safe_model_name_for_path(seed_model_name)

        processes_to_run = [process_id for process_id in process_ids if process_id in flows_to_analyze_map]
        total_processes = len(processes_to_run)
        max_workers = int(os.getenv("LCA_MAX_WORKERS", str(config.DEFAULT_LCA_MAX_WORKERS)))

        logging.info("=" * 60)
        logging.info("STARTING ANALYSIS FOR MODEL: %s", model_name)
        logging.info("Base URLs: %s", ", ".join(config.MODELHUB_BASE_URLS))
        logging.info("Temperature: %s", config.MODEL_TEMPERATURE)
        logging.info("GHG chunk size: %s", config.MAX_GHGS_PER_CALL)
        logging.info("Per-process concurrent flow workers: %s", config.MAX_CONCURRENT_FLOWS_PER_PROCESS)
        logging.info("Max in-flight model requests: %s", config.MAX_IN_FLIGHT_MODEL_REQUESTS)
        logging.info("Processes queued: %s", total_processes)
        logging.info("Max workers: %s", max_workers)
        if seed_results_dir != model_results_dir:
            logging.info("Seed results dir: %s", seed_results_dir)
        logging.info("=" * 60)

        summary_counts = {
            "completed": 0,
            "partial": 0,
            "skipped_complete": 0,
            "completed_no_ghgs": 0,
            "skipped_no_target_flows": 0,
            "failed": 0,
        }
        finished_processes = 0

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_pid = {
                executor.submit(
                    process_single_process,
                    model_name,
                    process_id,
                    flows_to_analyze_map,
                    ghg_combos,
                    model_results_dir,
                    (
                        seed_results_dir / f"{process_id}.json"
                        if seed_results_dir != model_results_dir
                        else None
                    ),
                ): process_id
                for process_id in processes_to_run
            }

            for future in as_completed(future_to_pid):
                process_id = future_to_pid[future]
                try:
                    result = future.result()
                except Exception as exc:
                    logging.error("Process %s failed for model %s: %s", process_id, model_name, exc, exc_info=True)
                    result = {
                        "process_id": process_id,
                        "status": "failed",
                        "expected_pairs": 0,
                        "completed_pairs": 0,
                    }

                finished_processes += 1
                summary_counts[result["status"]] = summary_counts.get(result["status"], 0) + 1
                remaining_processes = total_processes - finished_processes

                logging.info(
                    "[pipeline] %s/%s processes finished. latest=%s status=%s completed_pairs=%s/%s remaining_processes=%s summary=%s",
                    finished_processes,
                    total_processes,
                    result["process_id"],
                    result["status"],
                    result["completed_pairs"],
                    result["expected_pairs"],
                    remaining_processes,
                    summary_counts,
                )

        logging.info("ANALYSIS COMPLETE FOR MODEL: %s", model_name)
        logging.info("Final summary for %s: %s", model_name, summary_counts)

    logging.info("=============================================")
    logging.info("===      Pipeline Finished Successfully!    ===")


if __name__ == "__main__":
    run_pipeline()
