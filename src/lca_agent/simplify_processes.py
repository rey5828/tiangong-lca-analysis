import json
import os
from pathlib import Path

def simplify_process_json(input_file, output_dir):
    """
    读取工艺流程的JSON文件，提取重要信息，并保存为简化版本。
    
    Args:
        input_file: 输入JSON文件的路径
        output_dir: 输出目录
    """
    # 创建输出目录（如果不存在）
    output_dir.mkdir(parents=True, exist_ok=True)

    # 读取输入文件
    with open(input_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # 创建一个新的简化JSON对象
    simplified = {}
    
    # 提取基本信息
    simplified["name"] = data.get("name", "")
    simplified["description"] = data.get("description", "")
    
    # 提取工艺文档信息
    if "processDocumentation" in data:
        simplified["processDocumentation"] = {
            "timeDescription": data["processDocumentation"].get("timeDescription", ""),
            "technologyDescription": data["processDocumentation"].get("technologyDescription", ""),
            "samplingDescription": data["processDocumentation"].get("samplingDescription", "")
        }
    
    # 提取交换信息
    simplified["exchanges"] = []
    if "exchanges" in data:
        for exchange in data["exchanges"]:
            simplified_exchange = {
                "isInput": bool(exchange.get("isInput", False)),
                "amount": exchange.get("amount", 0),
            }
            
            # 提取流信息
            if "flow" in exchange:
                flow_data = exchange["flow"]
                is_input = simplified_exchange["isInput"]
                flow_type = flow_data.get("flowType", "")

                flow_info = {
                    "name": flow_data.get("name", "")
                }

                include_category = False
                include_flow_type = True

                if is_input:
                    include_category = False
                else:
                    if flow_type in {"PRODUCT_FLOW", "WASTE_FLOW"}:
                        include_category = False
                    elif flow_type == "ELEMENTARY_FLOW":
                        include_category = True
                        include_flow_type = False
                    else:
                        include_category = True

                if include_category:
                    flow_info["category"] = flow_data.get("category", "")
                if include_flow_type and flow_type:
                    flow_info["flowType"] = flow_type

                simplified_exchange["flow"] = flow_info
            
            # 提取单位信息
            if "unit" in exchange:
                simplified_exchange["unit"] = {
                    "name": exchange["unit"].get("name", "")
                }
            
            simplified["exchanges"].append(simplified_exchange)
    
    # 提取输出文件名（保持原文件名）
    output_file = output_dir / input_file.name
    
    # 写入输出文件
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(simplified, f, indent=2, ensure_ascii=False)
    
    return output_file

def process_selected_json_files():
    """处理在process_ids.json中列出的JSON文件"""
    # 定义目录路径
    base_dir = Path("/home/rui/tiangong-lca-analysis")
    input_dir = base_dir / "data/processes"
    output_dir = base_dir / "data/processes_simplified"
    process_list_path = base_dir / "data/jsons/process_ids.json"
    
    # 确保输出目录存在
    output_dir.mkdir(parents=True, exist_ok=True)
    
    with open(process_list_path, 'r', encoding='utf-8') as f:
        process_ids = json.load(f)
    
    print(f"从列表加载了 {len(process_ids)} 个需要处理的process ID")
    
    # 处理所有在列表中的JSON文件
    processed_count = 0
    skipped_count = 0
    missing_count = 0
    
    for process_id in process_ids:
        # 构建输入文件路径
        input_file = input_dir / f"{process_id}.json"
        
        # 检查文件是否存在
        if not input_file.exists():
            print(f"警告: ID为 {process_id} 的文件不存在")
            missing_count += 1
            continue
            
        try:
            output_path = simplify_process_json(input_file, output_dir)
            processed_count += 1
            # 每处理100个文件输出一次进度
            if processed_count % 100 == 0:
                print(f"进度: {processed_count}/{len(process_ids)} - {processed_count/len(process_ids)*100:.1f}%")
        except Exception as e:
            print(f"处理文件 {process_id} 时出错: {e}")
            skipped_count += 1
    
    print(f"\n处理完成:")
    print(f"- 总共处理成功: {processed_count} 个文件")
    print(f"- 处理失败: {skipped_count} 个文件")
    print(f"- 未找到文件: {missing_count} 个文件")

if __name__ == "__main__":
    process_selected_json_files()
