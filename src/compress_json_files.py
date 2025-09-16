import json
import os
from pathlib import Path

def compress_json_files():
    """
    将data/processes_simplified目录中的所有JSON文件压缩并保存到data/process_compressed目录
    """
    # 定义输入和输出目录
    base_dir = Path("/home/Rui/tiangong-lca-analysis")
    input_dir = base_dir / "data/processes_simplified"
    output_dir = base_dir / "data/process_compressed"
    
    # 确保输出目录存在
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # 获取所有JSON文件
    json_files = list(input_dir.glob("*.json"))
    total_files = len(json_files)
    
    print(f"找到 {total_files} 个JSON文件需要压缩")
    
    # 统计信息
    processed_count = 0
    error_count = 0
    total_size_before = 0
    total_size_after = 0
    
    # 处理每个文件
    for i, json_file in enumerate(json_files, 1):
        try:
            # 构建输出文件路径
            output_file = output_dir / json_file.name
            
            # 读取原始JSON
            with open(json_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # 记录压缩前大小
            file_size_before = json_file.stat().st_size
            total_size_before += file_size_before
            
            # 压缩JSON（无空格和换行）
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, separators=(',', ':'), ensure_ascii=False)
            
            # 记录压缩后大小
            file_size_after = output_file.stat().st_size
            total_size_after += file_size_after
            
            
            processed_count += 1
            
            # 每处理100个文件或处理完最后一个文件时显示进度
            if i % 100 == 0 or i == total_files:
                print(f"进度: {i}/{total_files} ({i/total_files*100:.1f}%)")
                
        except Exception as e:
            print(f"处理文件 {json_file.name} 时出错: {e}")
            error_count += 1
    
    # 计算总体压缩率
    overall_compression_ratio = (1 - total_size_after / total_size_before) * 100
    
    # 打印结果摘要
    print("\n压缩完成:")
    print(f"- 成功处理: {processed_count} 个文件")
    print(f"- 处理失败: {error_count} 个文件")
    print(f"- 压缩前总大小: {total_size_before / (1024*1024):.2f} MB")
    print(f"- 压缩后总大小: {total_size_after / (1024*1024):.2f} MB")
    print(f"- 总体压缩率: {overall_compression_ratio:.2f}%")

if __name__ == "__main__":
    compress_json_files()