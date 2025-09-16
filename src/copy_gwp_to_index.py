from elasticsearch import Elasticsearch
from elasticsearch.helpers import scan, bulk
import time
import os

es = Elasticsearch(
    hosts=["http://39.105.216.221:9200/"],
    basic_auth=(os.getenv("USERNAME"), os.getenv("PASSWORD")),
)

def add_gwp_field():
    # 1. 首先添加 gwp 字段到 mapping
    mapping_body = {
        "properties": {
            "gwp": {
                "type": "double"
            }
        }
    }
    
    try:
        response = es.indices.put_mapping(
            index="processwithghg_dedup2",
            body=mapping_body
        )
        print("GWP 字段映射添加成功" if response.get('acknowledged') else "GWP 字段映射添加失败")
    except Exception as e:
        print(f"添加映射时发生错误: {str(e)}")
        return False
    
    return True

def update_gwp_values():
    # 2. 从 uniqueaggregatedgwp_index 获取 process_id 和 gwp 的映射关系
    gwp_query = {
        "_source": ["process_id", "gwp"],
        "query": {
            "match_all": {}
        }
    }
    
    # 创建 process_id 到 gwp 的映射字典
    process_gwp_map = {}
    try:
        for doc in scan(es, query=gwp_query, index="uniqueaggregatedgwp_index"):
            source = doc['_source']
            if 'process_id' in source and 'gwp' in source:
                process_gwp_map[source['process_id']] = source['gwp']
        
        print(f"已加载 {len(process_gwp_map)} 条 GWP 数据")
    except Exception as e:
        print(f"加载 GWP 数据时发生错误: {str(e)}")
        return False

    # 3. 更新 processwithghg_dedup 中的文档
    update_actions = []
    try:
        # 扫描 processwithghg_dedup 中的所有文档
        query = {
            "_source": ["process_id"],
            "query": {
                "match_all": {}
            }
        }
        
        processed_count = 0
        updated_count = 0
        
        for doc in scan(es, query=query, index="processwithghg_dedup2"):
            processed_count += 1
            
            source = doc['_source']
            process_id = source.get('process_id')
            
            if process_id in process_gwp_map:
                update_actions.append({
                    '_op_type': 'update',
                    '_index': 'processwithghg_dedup2',
                    '_id': doc['_id'],
                    'doc': {
                        'gwp': process_gwp_map[process_id]
                    }
                })
                updated_count += 1
                
                # 每1000条更新一次
                if len(update_actions) >= 1000:
                    bulk(es, update_actions)
                    update_actions = []
                    print(f"已处理: {processed_count}, 已更新: {updated_count}")
        
        # 处理剩余的更新
        if update_actions:
            bulk(es, update_actions)
            
        print(f"\n更新完成！总处理文档数: {processed_count}, 成功更新数: {updated_count}")
        
    except Exception as e:
        print(f"更新文档时发生错误: {str(e)}")
        return False
    
    return True

def main():
    start_time = time.time()
    
    print("开始添加 GWP 字段...")
    if not add_gwp_field():
        return
    
    print("\n开始更新 GWP 值...")
    if not update_gwp_values():
        return
    
    end_time = time.time()
    print(f"\n总耗时: {(end_time - start_time):.2f} 秒")

if __name__ == "__main__":
    main()