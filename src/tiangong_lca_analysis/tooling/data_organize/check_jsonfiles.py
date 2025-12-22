import json
import os
from pathlib import Path

def check_process_files():
    """检查process_list_all.json中的所有ID是否都有对应的简化JSON文件"""
    
    # 定义文件路径
    base_dir = Path("/home/Rui/tiangong-lca-analysis")
    process_list_path = base_dir / "data/process_list_all.json"
    simplified_dir = base_dir / "data/processes"
    
    # 加载process_list_all.json
    with open(process_list_path, 'r', encoding='utf-8') as f:
        process_ids = json.load(f)
    
    print(f"从process_list_all.json中加载了 {len(process_ids)} 个进程ID")
    
    # 获取简化目录中所有JSON文件的列表
    if not simplified_dir.exists():
        print(f"错误: {simplified_dir} 目录不存在")
        return
        
    simplified_files = [f.stem for f in simplified_dir.glob("*.json")]
    print(f"在processes_simplified目录中找到 {len(simplified_files)} 个JSON文件")
    
    # 检查每个ID是否有对应的简化文件
    missing_ids = []
    
    for process_id in process_ids:
        if process_id not in simplified_files:
            missing_ids.append(process_id)
    
    # 打印结果
    if missing_ids:
        print(f"发现 {len(missing_ids)} 个ID没有对应的简化JSON文件:")
        for missing_id in missing_ids[:10]:  # 只打印前10个，避免输出过长
            print(f"  - {missing_id}")
        
        if len(missing_ids) > 10:
            print(f"  ... 以及 {len(missing_ids) - 10} 个其他ID")
            
        # 将缺失的ID保存到文件中
        missing_file = base_dir / "data/missing_process_files.json"
        with open(missing_file, 'w', encoding='utf-8') as f:
            json.dump(missing_ids, f, indent=2)
        print(f"所有缺失的ID已保存到 {missing_file}")
    else:
        print("所有ID都有对应的简化JSON文件")
    
    # 检查是否有多余的文件
    extra_files = []
    for file_name in simplified_files:
        if file_name not in process_ids:
            extra_files.append(file_name)
    
    if extra_files:
        print(f"发现 {len(extra_files)} 个额外的简化JSON文件（不在process_list_all.json中）:")
        for extra_file in extra_files[:10]:  # 只打印前10个
            print(f"  - {extra_file}")
        
        if len(extra_files) > 10:
            print(f"  ... 以及 {len(extra_files) - 10} 个其他文件")

if __name__ == "__main__":
    check_process_files()