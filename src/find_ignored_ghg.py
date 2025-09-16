import json

def load_json(file_path):
    """加载JSON文件"""
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            return json.load(file)
    except Exception as e:
        print(f"无法加载文件 {file_path}: {e}")
        return None

def get_base_name(name):
    """获取逗号前的基本名称"""
    return name.split(',')[0].strip() if isinstance(name, str) and ',' in name else name

def find_duplicates():
    # 加载两个JSON文件
    ghgs_data = load_json("data/ghgs.json")
    flows_data = load_json("data/flows_to_analyze.json")
    
    if not ghgs_data or not flows_data:
        return
    
    # 提取GHG名称并获取其基本名称（逗号前的部分）
    ghg_base_names = {get_base_name(item["GHG_name"]): item["GHG_name"] for item in ghgs_data}
    
    # 使用集合来存储唯一的重复项
    # 使用(ghg_name, flow_name)元组作为键以确保唯一性
    unique_duplicates = set()
    
    
    # 遍历嵌套字典结构
    for process_id, exchanges in flows_data.items():
        for exchange in exchanges:
            if isinstance(exchange, dict) and "flow_name" in exchange:
                flow_name = exchange.get("flow_name", "")
                flow_base_name = get_base_name(flow_name)
                
                if flow_base_name and flow_base_name in ghg_base_names:
                    ghg_name = ghg_base_names[flow_base_name]
                    unique_duplicates.add((ghg_name, flow_name))
    
    ## 将唯一的重复项转换为列表格式
    unique_duplicates_list = [
        {"ghg_name": ghg_name, "flow_name": flow_name} 
        for ghg_name, flow_name in unique_duplicates
    ]
    
    # 按ghg_name排序，使输出更有组织性
    unique_duplicates_list.sort(key=lambda x: x["ghg_name"])
    
    # 将重复项输出到JSON文件
    if unique_duplicates_list:
        output_path = "data/ignored_ghg.json"
        with open(output_path, 'w', encoding='utf-8') as outfile:
            json.dump(unique_duplicates_list, outfile, ensure_ascii=False, indent=2)
        print(f"发现 {len(unique_duplicates_list)} 个唯一重复项，已保存到 {output_path}")
        print(f"（相比之前的结果减少了 {len(unique_duplicates) - len(unique_duplicates_list)} 个重复记录）")
    else:
        print("未发现重复项")

if __name__ == "__main__":
    find_duplicates()