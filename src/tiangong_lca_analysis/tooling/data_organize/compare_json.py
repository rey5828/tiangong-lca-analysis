import json
from collections import defaultdict
import datetime

def compare_json_files():
    # 设置输出文件名，包含时间戳
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = f"comparison_results_{timestamp}.txt"
    
    # 创建输出文件并打开用于写入
    with open(output_file, 'w', encoding='utf-8') as out_file:
        # 记录开始时间和基本信息
        start_time = datetime.datetime.now()
        out_file.write(f"比较开始于: {start_time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        out_file.write("比较 matching_process_pairs.json 和 process_analysis_results.json\n")
        out_file.write("-" * 80 + "\n\n")
        
        # 加载第一个JSON文件 (matching_process_pairs.json)
        try:
            with open('matching_process_pairs.json', 'r', encoding='utf-8') as f:
                matching_data = json.load(f)
                out_file.write("成功加载 matching_process_pairs.json\n")
        except Exception as e:
            out_file.write(f"无法加载 matching_process_pairs.json: {str(e)}\n")
            print(f"错误: 无法加载 matching_process_pairs.json - {str(e)}")
            return
        
        # 加载第二个JSON文件 (process_analysis_results.json)
        try:
            with open('process_analysis_results.json', 'r', encoding='utf-8') as f:
                analysis_data = json.load(f)
                out_file.write("成功加载 process_analysis_results.json\n\n")
        except Exception as e:
            out_file.write(f"无法加载 process_analysis_results.json: {str(e)}\n")
            print(f"错误: 无法加载 process_analysis_results.json - {str(e)}")
            return
        
        # 转换matching_data为字典格式，便于比较
        matching_formatted = {}
        
        # 假设matching_data是列表形式
        if isinstance(matching_data, list):
            for item in matching_data:
                key = f"{item['input_count']}_{item['output_count']}"
                
                processes = []
                for i in range(len(item['process_ids'])):
                    processes.append({
                        "process_id": item['process_ids'][i],
                        "process_name": item['process_names'][i] if 'process_names' in item else None,
                        "process_category": item['process_categories'][i] if 'process_categories' in item else None,
                        "gwp": item['gwps'][i] if 'gwps' in item else None
                    })
                
                # 按process_id排序以确保比较顺序一致
                processes.sort(key=lambda x: x['process_id'])
                matching_formatted[key] = processes
        else:
            # 如果matching_data已经是字典形式
            for key, item in matching_data.items():
                if isinstance(key, str) and '_' in key:
                    # 如果键已经是'input_count_output_count'格式
                    processes = []
                    for i in range(len(item['process_ids'])):
                        processes.append({
                            "process_id": item['process_ids'][i],
                            "process_name": item['process_names'][i] if 'process_names' in item else None,
                            "process_category": item['process_categories'][i] if 'process_categories' in item else None,
                            "gwp": item['gwps'][i] if 'gwps' in item else None
                        })
                    
                    processes.sort(key=lambda x: x['process_id'])
                    matching_formatted[key] = processes
                else:
                    input_count = item.get('input_count')
                    output_count = item.get('output_count')
                    if input_count is not None and output_count is not None:
                        key = f"{input_count}_{output_count}"
                        
                        processes = []
                        for i in range(len(item['process_ids'])):
                            processes.append({
                                "process_id": item['process_ids'][i],
                                "process_name": item['process_names'][i] if 'process_names' in item else None,
                                "process_category": item['process_categories'][i] if 'process_categories' in item else None,
                                "gwp": item['gwps'][i] if 'gwps' in item else None
                            })
                        
                        processes.sort(key=lambda x: x['process_id'])
                        matching_formatted[key] = processes
        
        # 如果analysis_data包含一个特定的键来访问数据
        analysis_formatted = {}
        if "similar_processes_by_io_count" in analysis_data:
            analysis_data = analysis_data["similar_processes_by_io_count"]
        
        # 处理analysis_data
        for key, processes in analysis_data.items():
            # 按process_id排序以确保比较顺序一致
            sorted_processes = sorted(processes, key=lambda x: x['process_id'])
            analysis_formatted[key] = sorted_processes
        
        # 比较两个数据集
        out_file.write("比较两个JSON文件中的数据...\n")
        out_file.write("-" * 80 + "\n")
        
        # 获取所有唯一的键
        all_keys = set(matching_formatted.keys()).union(set(analysis_formatted.keys()))
        
        # 跟踪总体匹配情况
        all_matches = True
        mismatch_count = 0
        
        for key in sorted(all_keys):
            out_file.write(f"\n检查组合 {key}:\n")
            
            # 检查键是否同时存在于两个数据集中
            if key not in matching_formatted:
                out_file.write(f"  组合 {key} 只存在于process_analysis_results.json中\n")
                all_matches = False
                mismatch_count += 1
                continue
            
            if key not in analysis_formatted:
                out_file.write(f"  组合 {key} 只存在于matching_process_pairs.json中\n")
                all_matches = False
                mismatch_count += 1
                continue
            
            # 检查process_id列表是否相同
            matching_processes = matching_formatted[key]
            analysis_processes = analysis_formatted[key]
            
            # 比较process_id
            matching_ids = [p['process_id'] for p in matching_processes]
            analysis_ids = [p['process_id'] for p in analysis_processes]
            
            if set(matching_ids) != set(analysis_ids):
                out_file.write(f"  process_id不匹配:\n")
                only_in_matching = set(matching_ids) - set(analysis_ids)
                if only_in_matching:
                    out_file.write(f"    仅在matching_process_pairs.json中: {only_in_matching}\n")
                
                only_in_analysis = set(analysis_ids) - set(matching_ids)
                if only_in_analysis:
                    out_file.write(f"    仅在process_analysis_results.json中: {only_in_analysis}\n")
                
                all_matches = False
                mismatch_count += 1
            else:
                out_file.write(f"  ✓ process_id匹配 ({len(matching_ids)}个进程)\n")
                
                # 创建process_id到process的映射
                matching_dict = {p['process_id']: p for p in matching_processes}
                analysis_dict = {p['process_id']: p for p in analysis_processes}
                
                # 比较每个process的其他属性
                for process_id in matching_ids:
                    m_process = matching_dict[process_id]
                    a_process = analysis_dict[process_id]
                    
                    # 检查process_name
                    if m_process.get('process_name') != a_process.get('process_name'):
                        out_file.write(f"  ✗ process_id '{process_id}' 的process_name不匹配:\n")
                        out_file.write(f"    matching: {m_process.get('process_name')}\n")
                        out_file.write(f"    analysis: {a_process.get('process_name')}\n")
                        all_matches = False
                        mismatch_count += 1
                    
                    # 检查process_category (在analysis中可能称为process_category)
                    m_category = m_process.get('process_category')
                    a_category = a_process.get('process_category')
                    
                    if m_category != a_category:
                        out_file.write(f"  ✗ process_id '{process_id}' 的process_category不匹配:\n")
                        out_file.write(f"    matching: {m_category}\n")
                        out_file.write(f"    analysis: {a_category}\n")
                        all_matches = False
                        mismatch_count += 1
                    
                    # 检查gwp，考虑浮点数比较的精度问题
                    m_gwp = m_process.get('gwp')
                    a_gwp = a_process.get('gwp')
                    
                    if m_gwp is not None and a_gwp is not None:
                        if abs(m_gwp - a_gwp) > 1e-10:  # 允许微小的浮点数差异
                            out_file.write(f"  ✗ process_id '{process_id}' 的gwp不匹配:\n")
                            out_file.write(f"    matching: {m_gwp}\n")
                            out_file.write(f"    analysis: {a_gwp}\n")
                            all_matches = False
                            mismatch_count += 1
                    elif (m_gwp is None and a_gwp is not None) or (m_gwp is not None and a_gwp is None):
                        out_file.write(f"  ✗ process_id '{process_id}' 的gwp不匹配 (一个为None):\n")
                        out_file.write(f"    matching: {m_gwp}\n")
                        out_file.write(f"    analysis: {a_gwp}\n")
                        all_matches = False
                        mismatch_count += 1
        
        # 写入总结
        out_file.write("\n" + "-" * 80 + "\n")
        end_time = datetime.datetime.now()
        duration = (end_time - start_time).total_seconds()
        
        out_file.write(f"比较完成于: {end_time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        out_file.write(f"耗时: {duration:.2f} 秒\n\n")
        
        if all_matches:
            out_file.write("✓ 两个JSON文件中的数据完全匹配!\n")
        else:
            out_file.write(f"✗ 发现 {mismatch_count} 处不匹配的数据，请查看上述详细信息。\n")
    
    # 打印保存文件的信息
    print(f"比较结果已保存到: {output_file}")
    if not all_matches:
        print(f"发现 {mismatch_count} 处不匹配的数据")
    else:
        print("两个JSON文件中的数据完全匹配!")

if __name__ == "__main__":
    compare_json_files()