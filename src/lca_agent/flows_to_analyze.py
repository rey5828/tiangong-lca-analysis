import json
import os

# 读取flows_list_all.json文件
def load_json(file_path):
    with open(file_path, 'r', encoding='utf-8') as file:
        return json.load(file)

# 读取ghgs文件并提取所有id
def get_ghgs_ids(ghgs_file_path):
    ghgs_data = load_json(ghgs_file_path)
    ghgs_ids = set()
    # 这里需要根据ghgs的实际结构来提取id
    # 例如：如果ghgs是一个包含id字段的对象列表
    for item in ghgs_data:
        if 'id' in item:
            ghgs_ids.add(item['id'])
    return ghgs_ids

# 过滤flows_list_all.json中与ghgs中id重复的记录

def filter_flows(flows_data, ghgs_ids):
    filtered_flows = {}
    total_records = 0
    excluded_records = 0
    
    for key, flows in flows_data.items():
        total_records += len(flows)
        filtered_list = [flow for flow in flows if flow['flow_id'] not in ghgs_ids]
        excluded_records += len(flows) - len(filtered_list)
        filtered_flows[key] = filtered_list
    
    return filtered_flows, total_records, excluded_records

# 保存过滤后的数据
def save_filtered_flows(filtered_data, output_file_path):
    with open(output_file_path, 'w', encoding='utf-8') as file:
        json.dump(filtered_data, file, indent=2)

def main():
    # 文件路径
    flows_file_path = os.path.join('data', 'flows_list_all.json')
    ghgs_file_path = os.path.join('data', 'ghgs.json')
    output_file_path = os.path.join('data', 'flows_list_analyze.json')
    
    # 加载数据
    flows_data = load_json(flows_file_path)
    
    # 如果ghgs.json文件不存在，提示用户
    if not os.path.exists(ghgs_file_path):
        print(f"Warning: {ghgs_file_path} not found. Please provide the GHGs data file.")
        return
    
    # 获取ghgs中的id
    ghgs_ids = get_ghgs_ids(ghgs_file_path)
    
    # 过滤flows
    filtered_flows, total_records, excluded_records = filter_flows(flows_data, ghgs_ids)
    
    # 统计保留的记录数
    retained_records = total_records - excluded_records
    
    # 保存结果
    save_filtered_flows(filtered_flows, output_file_path)
    
    # 输出统计信息
    print(f"\n过滤结果:")
    print(f"- 原始记录总数: {total_records}")
    print(f"- 排除的记录数: {excluded_records}")
    print(f"- 保留的记录数: {retained_records}")
    print(f"- 过滤后的流数据保存到: {output_file_path}")

if __name__ == "__main__":
    main()