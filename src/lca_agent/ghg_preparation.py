import pandas as pd
import json

def convert_csv_to_json(csv_path, output_json_path):
    """
    将CSV文件的前三列(value, id, name)转换为JSON格式
    
    参数:
    csv_path: CSV文件的路径
    output_json_path: 输出JSON文件的路径
    """
    try:
        # 读取CSV文件
        print(f"读取CSV文件: {csv_path}")
        df = pd.read_csv(csv_path)
        
        # 检查CSV文件是否至少包含三列
        if len(df.columns) < 3:
            print(f"错误: CSV文件必须至少包含三列，但只找到{len(df.columns)}列")
            return False
        
        # 提取前三列
        required_columns = ['value', 'id', 'name']
        
        # 检查所需列是否存在
        missing_columns = [col for col in required_columns if col not in df.columns]
        if missing_columns:
            print(f"错误: 在CSV文件中找不到以下列: {', '.join(missing_columns)}")
            return False
            
        # 只保留指定的三列
        df = df[required_columns]
        
        # 转换为字典列表
        data_list = []
        for _, row in df.iterrows():
            data_list.append({
                "value": row['value'],
                "id": row['id'],
                "name": row['name']
            })
        
        # 写入JSON文件
        with open(output_json_path, 'w', encoding='utf-8') as f:
            json.dump(data_list, f, ensure_ascii=False, indent=2)
        
        print(f"转换成功! JSON文件已保存到: {output_json_path}")
        print(f"共处理了{len(data_list)}条记录")
        return True
    
    except Exception as e:
        print(f"转换过程中出错: {str(e)}")
        return False

if __name__ == "__main__":
    # CSV文件路径
    csv_path = "/mnt/d/json/extracted_ghgflows.csv"
    
    # 输出JSON文件路径
    output_json_path = "data/ghgs.json"
    
    # 执行转换
    convert_csv_to_json(csv_path, output_json_path)