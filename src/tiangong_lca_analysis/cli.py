import json
import time
import logging
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, List

# Ensure package root is on sys.path when running as a script (python src/tiangong_lca_analysis/cli.py)
PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from tiangong_lca_analysis.agents import config
from tiangong_lca_analysis.agents.data_fetcher import (
    fetch_data_for_process,
    load_static_data,
)
from tiangong_lca_analysis.agents.lca_analyst import LCAAnalystAgent

log_dir = Path(config.ROOT_DIR) / "logs"
log_dir.mkdir(exist_ok=True, parents=True)

# 生成带时间戳的日志文件名
log_filename = f"lca_analysis_{time.strftime('%Y%m%d_%H%M%S')}.log"
log_filepath = log_dir / log_filename

# 修改日志配置，输出到文件
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    # 添加文件处理器
    handlers=[
        logging.FileHandler(log_filepath, encoding='utf-8'),
        # 如果希望同时在控制台看到输出，可以保留以下一行
        # logging.StreamHandler()  
    ]
)

# 添加一条起始日志记录文件位置
logging.info(f"Logging to file: {log_filepath}")

def safe_model_name_for_path(model_name: str) -> str:
    """将模型名称（如 'google/gemini-pro-1.5'）转换为安全的文件路径名（'google_gemini-pro-1.5'）"""
    return model_name.replace("/", "_")


def process_single_process(
    model_name: str,
    process_id: str,
    flows_to_analyze_map: Dict,
    ghg_combos: List,
    model_results_dir: Path,
) -> None:
    """按原有逻辑处理单个 process，便于在线程池中并行调用。"""
    output_path = model_results_dir / f"{process_id}.json"
    if output_path.exists():
        logging.warning(f"Result for {process_id} already exists. Skipping.")
        return

    try:
        process_data_package = fetch_data_for_process(process_id, flows_to_analyze_map, ghg_combos)
        if not process_data_package:
            return

        process_data, exchange_map, target_flows, relevant_ghg_list_str, relevant_ghgs = process_data_package

        ghg_log_str = ", ".join(relevant_ghgs) if relevant_ghgs else "None"
        logging.info(f"[{process_id}] Relevant GHG combos: {ghg_log_str}")

        analyst = LCAAnalystAgent(model_name=model_name)

        max_retries = 5
        flows_to_process = target_flows[:]
        all_results = []

        for attempt in range(max_retries + 1):
            if not flows_to_process:
                break

            logging.info(
                f"[{process_id}] Analysis attempt {attempt + 1}/{max_retries + 1}. "
                f"Analyzing {len(flows_to_process)} flows for model {model_name}."
            )

            analysis_result_dict = analyst.analyze_process(
                process_id=process_id,
                process_data=process_data,
                exchange_map=exchange_map,
                target_flows=flows_to_process,
                ghg_list_str=relevant_ghg_list_str,
                relevant_ghgs=relevant_ghgs,
            )

            if not analysis_result_dict or "flow_analyses" not in analysis_result_dict:
                logging.error(f"[{process_id}] Attempt {attempt + 1} failed. No valid response from LLM.")
                continue

            returned_analyses = analysis_result_dict.get("flow_analyses", [])
            all_results.extend(returned_analyses)

            processed_combos = {item.get('flow_combo') for item in returned_analyses if item.get('flow_combo')}
            flows_to_process = [flow for flow in flows_to_process if flow['flow_combo'] not in processed_combos]

        if flows_to_process:
            logging.warning(f"[{process_id}] After retries, {len(flows_to_process)} flows were not analyzed.")

        llm_results_map = {item.get('flow_combo'): item for item in all_results if 'flow_combo' in item}
        final_flow_analyses = []
        for flow_info in target_flows:
            flow_combo = flow_info['flow_combo']
            analysis_data = llm_results_map.get(flow_combo)
            if analysis_data:
                analysis_data['flow_combo'] = flow_combo
                final_flow_analyses.append(analysis_data)
            else:
                logging.warning(f"[{process_id}] LLM response missing result for flow '{flow_combo}', omitting.")

        final_output_dict = {process_id: final_flow_analyses}

        logging.info(f"[{process_id}] Saving final structured JSON output...")
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(final_output_dict, f, indent=4, ensure_ascii=False)

        logging.info(f"[{process_id}] Successfully saved result to {output_path}")
        time.sleep(1)

    except Exception as e:
        logging.error(f"[{process_id}] Unexpected error: {e}", exc_info=True)
        return


def run_pipeline():
    """
    执行完整分析流水线的主函数。
    """
    print("=============================================")
    print("===  LCA Analysis Pipeline Starting...    ===")

    # 1. 初始化
    #    在循环开始前，加载一次性静态数据，提高效率
    try:
        process_ids, flows_to_analyze_map, ghg_combos = load_static_data()
    except Exception as e:
        logging.critical(f"Critical Error during static data loading: {e}", exc_info=True) 
        return # 如果失败，则无法继续

    for model_name in config.MODELS_TO_RUN:
        
        model_path_name = safe_model_name_for_path(model_name)
        logging.info("=" * 50)
        logging.info(f"STARTING ANALYSIS FOR MODEL: {model_name}")
        logging.info("=" * 50)

        total_processes = len(process_ids)
        logging.info(f"Found {total_processes} processes to analyze with model {model_name}.")
        
        # 为当前模型的输出结果创建一个独立的子文件夹
        model_results_dir = config.RESULTS_JSON_DIR / model_path_name
        model_results_dir.mkdir(exist_ok=True)

        processes_to_run = [
            pid for pid in process_ids
            if not (model_results_dir / f"{pid}.json").exists()
        ]

        if not processes_to_run:
            logging.info(f"All processes already analyzed for model {model_name}. Skipping.")
            continue

        max_workers = int(os.getenv("LCA_MAX_WORKERS", os.cpu_count() or 4))
        logging.info(
            f"Dispatching {len(processes_to_run)} processes for model {model_name} "
            f"with up to {max_workers} workers."
        )

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_pid = {
                executor.submit(
                    process_single_process,
                    model_name,
                    pid,
                    flows_to_analyze_map,
                    ghg_combos,
                    model_results_dir,
                ): pid
                for pid in processes_to_run
            }

            for future in as_completed(future_to_pid):
                pid = future_to_pid[future]
                try:
                    future.result()
                except Exception as exc:
                    logging.error(f"Process {pid} failed for model {model_name}: {exc}", exc_info=True)

        logging.info(f"\nANALYSIS COMPLETE FOR MODEL: {model_name}\n")

    logging.info("\n=============================================")
    logging.info("===      Pipeline Finished Successfully!    ===")


if __name__ == "__main__":
    run_pipeline()
