import os
import json
import csv
import pandas as pd
from pathlib import Path
from collections import defaultdict

def merge_json_to_csv():
    """
    将output/agent_results/individual_jsons下每个文件夹中的json文件整理到CSV文件中。
    同名JSON文件整合进一个CSV，按照flow_id整合，除了flow_id和flow_name外，其他字段用文件夹名作为后缀。
    """
    # 基础目录
    base_dir = Path("/home/Rui/tiangong-lca-analysis")
    input_dir = base_dir / "output/agent_results/individual_jsons"
    output_dir = Path("/mnt/d/SynologyDrive/SynologyDrive/减污降碳/csv")
    
    # 确保输出目录存在
    os.makedirs(output_dir, exist_ok=True)
    
    # 获取所有模型文件夹
    model_folders = [f for f in input_dir.iterdir() if f.is_dir()]
    print(f"找到 {len(model_folders)} 个模型文件夹")
    
    # 用于按文件名分组JSON文件的字典
    json_files_by_name = defaultdict(list)
    
    # 遍历所有模型文件夹，收集同名JSON文件
    for model_folder in model_folders:
        model_name = model_folder.name
        json_files = list(model_folder.glob("*.json"))
        
        for json_file in json_files:
            # 使用文件名（不含扩展名）作为分组键
            file_name = json_file.stem
            json_files_by_name[file_name].append((model_name, json_file))
    
    print(f"找到 {len(json_files_by_name)} 个唯一的JSON文件名")
    
    # 处理每组同名JSON文件
    for file_name, files in json_files_by_name.items():
        print(f"处理文件: {file_name}")
        
        # 用于存储所有合并的数据
        all_data = []
        
        # 存储所有可能的列名
        all_columns = set(['flow_id', 'flow_name'])
        
        # 读取每个JSON文件并提取数据
        for model_name, json_file in files:
            try:
                with open(json_file, 'r', encoding='utf-8') as f:
                    json_data = json.load(f)
                
                # 提取键值，文件ID作为主键
                file_id = list(json_data.keys())[0]
                flow_items = json_data[file_id]
                
                # 处理数组中的每个流项
                for flow_item in flow_items:
                    # 跳过不完整的条目
                    if not isinstance(flow_item, dict) or 'flow_id' not in flow_item or 'flow_name' not in flow_item:
                        continue
                    
                    flow_id = flow_item['flow_id']
                    flow_name = flow_item['flow_name']
                    
                    # 创建一行数据，先包含flow_id和flow_name
                    row_data = {
                        'flow_id': flow_id,
                        'flow_name': flow_name
                    }
                    
                    # 添加其它字段，带有模型名称后缀
                    for key, value in flow_item.items():
                        if key not in ['flow_id', 'flow_name']:
                            column_name = f"{key}_{model_name}"
                            row_data[column_name] = value
                            all_columns.add(column_name)
                    
                    all_data.append(row_data)
            
            except Exception as e:
                print(f"处理文件 {json_file} 时出错: {e}")
                import traceback
                traceback.print_exc()
        
        # 使用pandas合并具有相同flow_id的行
        if all_data:
            df = pd.DataFrame(all_data)
            # 按flow_id分组并合并
            df_merged = df.groupby('flow_id', as_index=False).first()
            
            # 确保flow_name列在第二列
            if 'flow_name' in df_merged.columns and list(df_merged.columns).index('flow_name') != 1:
                cols = df_merged.columns.tolist()
                cols.remove('flow_name')
                cols.insert(1, 'flow_name')
                df_merged = df_merged[cols]
            
            # 保存到CSV文件
            output_file = output_dir / f"{file_name}.csv"
            df_merged.to_csv(output_file, index=False, encoding='utf-8-sig')  # 使用带BOM的UTF-8编码，以便Excel正确显示中文
            
            print(f"已将 {len(files)} 个JSON文件合并为 {output_file}")
        else:
            print(f"警告: {file_name} 没有有效数据，跳过")
    
    print("所有文件处理完成!")

if __name__ == "__main__":
    merge_json_to_csv()