import json
import collections

def compare_ids_and_count_flows():
    # 加载 flows_to_analyze_list.json 文件
    try:
        with open('data/flows_list_all.json', 'r') as f:
            flows_data = json.load(f)
    except FileNotFoundError:
        print("Error: flows_list_all.json not found")
        return
    except json.JSONDecodeError:
        print("Error: Invalid JSON in flows_list_all.json")
        return
    
    # 加载 output_ids.json 文件
    try:
        with open('data/output_ids.json', 'r') as f:
            output_ids = json.load(f)
    except FileNotFoundError:
        print("Error: output_ids.json not found")
        return
    except json.JSONDecodeError:
        print("Error: Invalid JSON in output_ids.json")
        return
    
    # 提取 flows_list.json 中的 ID
    flows_ids = []
    flow_id_counter = collections.Counter()
    flow_name_counter = collections.Counter()

    # 计算总数量
    total_flow_ids = 0
    total_flow_names = 0
    
    # 根据提供的示例调整解析逻辑
    for key, value_list in flows_data.items():
        flows_ids.append(key)  # 添加顶层键作为ID
        
        for item in value_list:
            if isinstance(item, dict) and 'flow_id' in item and 'flow_name' in item:
                flow_id_counter[item['flow_id']] += 1
                flow_name_counter[item['flow_name']] += 1
                total_flow_ids += 1
                total_flow_names += 1
    
    # 提取 output_ids.json 中的 ID
    output_ids_list = list(output_ids.keys()) if isinstance(output_ids, dict) else output_ids
    
    # 比较两个文件中的 ID
    missing_in_output = [id for id in flows_ids if id not in output_ids_list]
    missing_in_flows = [id for id in output_ids_list if id not in flows_ids]
    
    # 输出比较结果
    print(f"IDs in flows_to_analyze_list.json: {len(flows_ids)}")
    print(f"IDs in output_ids.json: {len(output_ids_list)}")
    print(f"IDs match: {len(flows_ids) == len(output_ids_list) and not missing_in_output and not missing_in_flows}")
    
    if missing_in_output:
        print(f"IDs in flows_to_analyze_list.json but not in output_ids.json: {len(missing_in_output)}")
        print(f"Examples: {missing_in_output[:5]}")
    
    if missing_in_flows:
        print(f"IDs in output_ids.json but not in flows_to_analyze_list.json: {len(missing_in_flows)}")
        print(f"Examples: {missing_in_flows[:5]}")
    
    # 输出 flow_id 和 flow_name 的统计信息
    print("\nflow_id statistics:")
    for flow_id, count in flow_id_counter.most_common(10):
        print(f"  {flow_id}: {count} occurrences")
    
    print("\nflow_name statistics:")
    for flow_name, count in flow_name_counter.most_common(10):
        print(f"  {flow_name}: {count} occurrences")
    
    print(f"\nTotal unique flow_ids: {len(flow_id_counter)}")
    print(f"Total unique flow_names: {len(flow_name_counter)}")
    print(f"\nTotal flow_names entries: {total_flow_names}")
    print(f"Total unique flow_names: {len(flow_name_counter)}")

if __name__ == "__main__":
    compare_ids_and_count_flows()