import json
import time
import logging
import os
from pathlib import Path
from typing import Dict, List

from lca_agent import config 

from lca_agent.data_fetcher import load_static_data, fetch_data_for_process
from lca_agent.lca_analyst import LCAAnalystAgent

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

        try:
            # 为当前循环的模型实例化 Agent
            analyst = LCAAnalystAgent(model_name=model_name)
        except Exception as e:
            logging.critical(f"Could not initialize agent for model {model_name}. Skipping. Error: {e}", exc_info=True)
            continue # 如果Agent初始化失败，则跳过此模型

        # 2. 主循环
        #    遍历每一个需要分析的单元过程ID
        for i, process_id in enumerate(process_ids):
            logging.info("-" * 50)
            logging.info(f"Processing... [{i+1}/{total_processes}]: {process_id}")

            try:
                # 检查输出文件是否已存在，如果存在则跳过，支持断点续传
                output_path = model_results_dir / f"{process_id}.json"
                if output_path.exists():
                    logging.warning(f"Result for {process_id} already exists. Skipping.")
                    continue

                # Step A: 调用 Data Fetcher 获取此过程的数据
                process_data_package = fetch_data_for_process(process_id, flows_to_analyze_map, ghg_combos)
                if not process_data_package:
                    # fetch_data_for_process 内部会打印警告/错误，这里直接继续即可
                    continue
                
                process_json_content, target_flows, relevant_ghg_list_str, relevant_ghgs = process_data_package

                ghg_log_str = ", ".join(relevant_ghgs) if relevant_ghgs else "None"
                logging.info(f"Relevant GHG combos for {process_id}: {ghg_log_str}")

                # Step B: 调用 LCA Analyst 进行分析, 调用LCA Analyst获取“无ID”的分析结果, 加入重试逻辑
                max_retries = 3 # 设置最大重试次数
                flows_to_process = target_flows[:] # 创建一个待处理列表的副本
                all_results = [] # 存储所有成功返回的结果
                
                for attempt in range(max_retries + 1):
                    if not flows_to_process:
                        break # 如果所有flow都处理完了，就跳出循环

                    logging.info(f"Analysis attempt {attempt + 1}/{max_retries + 1}. Analyzing {len(flows_to_process)} flows for process {process_id}.")
                        
                    analysis_result_dict = analyst.analyze_process(
                        process_id=process_id,
                        process_json_content=process_json_content,
                        target_flows=flows_to_process, # 只发送待处理的flow
                        ghg_list_str=relevant_ghg_list_str
                    )
                
                    if not analysis_result_dict or "flow_analyses" not in analysis_result_dict:
                        logging.error(f"Analysis attempt {attempt + 1} failed for {process_id}. No valid response from LLM.")
                        continue

                    returned_analyses = analysis_result_dict.get("flow_analyses", [])
                    all_results.extend(returned_analyses) # 将本次成功的结果加入总列表

                    # 找出哪些flow被遗漏了，准备下一次重试
                    processed_combos = {item.get('flow_combo') for item in returned_analyses if item.get('flow_combo')}
                    flows_to_process = [flow for flow in flows_to_process if flow['flow_combo'] not in processed_combos]

                if flows_to_process:
                    logging.warning(
                        f"After all retries, {len(flows_to_process)} flows were still not analyzed for process {process_id}."
                    )

                # Step C: 构建最终的、ID准确的JSON结构
                logging.info(f"Matching results from array and aligning flow combos for process: {process_id}...")
                
                # 为了快速匹配，将LLM返回的列表转换为以 flow_combo 为键的字典
                llm_results_map = {item.get('flow_combo'): item for item in all_results if 'flow_combo' in item}
                #初始化为列表而非字典
                final_flow_analyses = []
                # 遍历target_flows 列表
                for flow_info in target_flows:
                    flow_combo = flow_info['flow_combo']

                    # 从转换后的map中查找对应的分析数据
                    analysis_data = llm_results_map.get(flow_combo)

                    if analysis_data:
                        analysis_data['flow_combo'] = flow_combo
                        final_flow_analyses.append(analysis_data)
                    else:
                        logging.warning(
                            f"LLM response did not contain a result for flow '{flow_combo}'. This flow will be omitted."
                        )
                        
                # 用正确的 process_id 将所有内容包装起来，形成最终结构
                final_output_dict = {
                    process_id: final_flow_analyses
                }

                # Step D: 存储最终的、完全准确的结果
                logging.info(f"Saving final structured JSON output for {process_id}...")          
                with open(output_path, 'w', encoding='utf-8') as f:
                    # ensure_ascii=False 确保中文等非ASCII字符能被正确写入，而不是被转义
                    json.dump(final_output_dict, f, indent=4, ensure_ascii=False)
                
                logging.info(f"Successfully saved result to {output_path}")
                
                time.sleep(1)

            except Exception as e:
                # 捕获循环中的意外错误，记录并继续处理下一个，而不是让整个程序崩溃
                logging.error(f"An unexpected error occurred while processing {process_id}: {e}", exc_info=True) # exc_info=True会记录完整的错误堆栈信息
                continue

        logging.info(f"\nANALYSIS COMPLETE FOR MODEL: {model_name}\n")

    logging.info("\n=============================================")
    logging.info("===      Pipeline Finished Successfully!    ===")


if __name__ == "__main__":
    run_pipeline()
