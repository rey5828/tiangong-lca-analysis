import os
import pandas as pd
import re
from pathlib import Path

def add_consistency_column(csv_file_path):
    """
    为CSV文件添加一个Consistency列，并应用CHOOSE公式
    """
    try:
        # 读取CSV文件
        df = pd.read_csv(csv_file_path)
        
        # 查找需要检查的所有列（除了flow_id和flow_name）
        # 假设所有模型的qualitative_relationship列都是格式为"qualitative_relationship_模型名"
        qual_rel_columns = [col for col in df.columns if "qualitative_relationship" in col]
        
        if not qual_rel_columns:
            print(f"警告: {csv_file_path} 中未找到qualitative_relationship列，跳过")
            return False
        
        # 创建新的Consistency列
        df['Consistency'] = None
        
        # 为每一行计算一致性得分
        for idx, row in df.iterrows():
            # 计算Positive、Negative和Neutral的数量
            positive_count = sum(1 for col in qual_rel_columns if row[col] == "Positive")
            negative_count = sum(1 for col in qual_rel_columns if row[col] == "Negative")
            neutral_count = sum(1 for col in qual_rel_columns if row[col] == "Neutral")
            
            # 获取最大计数
            max_count = max(positive_count, negative_count, neutral_count)
            
            # 应用CHOOSE公式逻辑
            if max_count == 0:
                consistency = 0
            elif max_count == 2:
                consistency = 0.5
            elif max_count == 3:
                consistency = 0.75
            else:
                consistency = 1
            
            df.at[idx, 'Consistency'] = consistency
        
        # 保存修改后的CSV文件
        df.to_csv(csv_file_path, index=False, encoding='utf-8-sig')
        print(f"成功为 {os.path.basename(csv_file_path)} 添加Consistency列")
        return True
    
    except Exception as e:
        print(f"处理 {csv_file_path} 时出错: {e}")
        return False

def process_all_csv_files(directory):
    """
    处理指定目录下的所有CSV文件
    """
    # 确保目录路径是绝对路径
    directory = os.path.abspath(directory)
    
    # 获取目录下所有CSV文件
    csv_files = [f for f in os.listdir(directory) if f.endswith('.csv')]
    print(f"在 {directory} 中找到 {len(csv_files)} 个CSV文件")
    
    # 处理每个CSV文件
    success_count = 0
    for csv_file in csv_files:
        csv_file_path = os.path.join(directory, csv_file)
        if add_consistency_column(csv_file_path):
            success_count += 1
    
    print(f"\n处理完成: 成功处理 {success_count}/{len(csv_files)} 个文件")

if __name__ == "__main__":
    # 指定CSV文件所在目录
    csv_directory = r"/mnt/d/SynologyDrive/SynologyDrive/减污降碳/csv/zhengli"
    process_all_csv_files(csv_directory)