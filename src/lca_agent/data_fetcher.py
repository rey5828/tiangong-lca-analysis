import json
from typing import Dict, List, Tuple, Any, Optional

from . import config

def load_static_data() -> Tuple[List[str], Dict, Dict[str, Dict]]:
    """
    加载在整个运行过程中保持不变的静态数据。
    这包括过程ID列表、待分析Flows的映射和GHG列表。
    这个函数应该在主循环开始前只调用一次。
    
    Returns:
        A tuple containing:
        - a list of process IDs to be analyzed.
        - a dictionary mapping process IDs to their target flows.
        - a dictionary of all GHGs, keyed by their ID for fast lookup.
    """
    print("[*] Loading static data...")

    # 加载过程列表
    with open(config.PROCESS_LIST_PATH, 'r', encoding='utf-8') as f:
        process_ids = json.load(f)

    # 加载待分析Flows的完整映射
    with open(config.FLOWS_TO_ANALYZE_PATH, 'r', encoding='utf-8') as f:
        flows_to_analyze_map = json.load(f)

    # 加载所有GHG，并转换为以ID为键的字典
    with open(config.GHG_LIST_PATH, 'r', encoding='utf-8') as f:
        all_ghg_data = json.load(f)

    ghg_map_by_id = {item['id']: item for item in all_ghg_data}
    
    print("[+] Static data loaded successfully.")
    return process_ids, flows_to_analyze_map, ghg_map_by_id


def fetch_data_for_process(process_id: str, flows_map: Dict, all_ghgs_map: Dict[str, Dict]) -> Optional[Tuple[str, List[Dict[str, Any]], str]]:
    """
    为单个给定的process_id提取其特定的数据，筛选出相关的GHG, 并为待分析flow添加临时分析ID。

    Args:
        process_id: 需要分析的单元过程的ID。
        flows_map: 包含所有过程及其对应待分析Flows的字典。
        all_ghgs_map: 包含所有GHG数据的字典，以ID为键。

    Returns:
        一个元组，包含 (过程JSON内容的字符串, 此过程待分析的flows列表, 与此过程相关的GHG列表字符串)。
        如果找不到对应的JSON文件，则返回 None。
    """
    print(f"[*] Fetching data for process: {process_id}")
    
    # 1. 获取此过程需要分析的 elementary flows 列表
    # 使用 .get() 方法，如果ID不存在于map中，则返回一个空列表，避免错误
    original_target_flows = flows_map.get(process_id, [])
    
    # 如果没有为这个过程定义需要分析的flow，可以提前返回
    if not original_target_flows:
        print(f"[!] Warning: No target flows defined for process {process_id}. Skipping.")
        return None

    # 2. 为待分析的 flows 添加临时分析 ID用于匹配
    target_flows_with_aid = []
    for i, flow in enumerate(original_target_flows):
        flow['analysis_id'] = str(i) # 将索引作为分析ID
        target_flows_with_aid.append(flow)

    # 3. 读取该过程对应的JSON文件内容
    process_json_path = config.PROCESS_JSONS_DIR / f"{process_id}.json"
    
    try:
        with open(process_json_path, 'r', encoding='utf-8') as f:
            process_json_content = f.read()
            process_data = json.loads(process_json_content)
    except FileNotFoundError:
        print(f"[X] Error: JSON file not found for process {process_id} at {process_json_path}")
        return None
    except Exception as e:
        print(f"[X] Error reading JSON file for {process_id}: {e}")
        return None
    
    # 4. **新逻辑：筛选与此过程相关的GHG**
    relevant_ghgs = []
    # 获取所有温室气体的ID集合，用于高效判断
    ghg_id_set = set(all_ghgs_map.keys())

    for exchange in process_data.get('exchanges', []):
        is_emission = not exchange.get('isInput', True)
        flow = exchange.get('flow', {})
        flow_type = flow.get('flowType')
        flow_id = flow.get('@id')

        if is_emission and flow_type == 'ELEMENTARY_FLOW' and flow_id in ghg_id_set:
            # 这是一个在此过程中排放的温室气体
            # 从我们的GHG总表中获取它的完整信息
            ghg_info = all_ghgs_map[flow_id]
            if ghg_info not in relevant_ghgs: # 避免重复添加
                relevant_ghgs.append(ghg_info)
    
    if not relevant_ghgs:
        print(f"[!] Warning: No relevant GHGs found in process {process_id}. The GHG list for the prompt will be empty.")
        # 即使为空，我们仍然可以继续，让模型知道这个过程没有GHG排放
    
    # 5. 格式化筛选后的GHG列表以注入Prompt
    relevant_ghg_list_str = "\n".join([f"- {item['GHG_name']} (ID: {item['id']}, GWP: {item['GWP']})" for item in relevant_ghgs])


    print(f"[+] Successfully fetched data and found {len(relevant_ghgs)} relevant GHGs for {process_id}.")

    return (process_json_content, target_flows_with_aid, relevant_ghg_list_str)