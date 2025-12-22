from elasticsearch import Elasticsearch, helpers
import os

es = Elasticsearch(
    hosts=["http://39.105.216.221:9200/"],
    basic_auth=(os.getenv("USERNAME"), os.getenv("PASSWORD")),
)

filtered_index = "processsdep_validation_index"
aggregated_index = "uniqueaggregatedgwp_index"

mapping_body = {
    "properties": {
        "ratio": {
            "type": "double"
        }
    }
}

try:
    # 更新现有索引的映射
    response = es.indices.put_mapping(
        index=filtered_index,
        body=mapping_body
    )
    
    if response.get('acknowledged'):
        print(f"成功为索引 {filtered_index} 添加 ratio 字段")
    else:
        print("更新映射失败")
        
except Exception as e:
    print(f"更新映射时发生错误: {str(e)}")

# Scroll API 参数
scroll_time = "2m"
batch_size = 1000

# 从 uniqueaggregatedgwp_index 中获取 process_id 和 gwp
def get_gwp_mapping(es, index):
    query = {
        "_source": ["process_id", "gwp"],
        "query": {
            "exists": { "field": "gwp" }  # 只获取有gwp字段的文档
        }
    }
    
    # 使用 Scroll API 获取所有结果
    response = es.search(index=index, body=query, scroll=scroll_time, size=batch_size)
    scroll_id = response['_scroll_id']
    hits = response['hits']['hits']
    
    gwp_mapping = {}
    while hits:
        for hit in hits:
            process_id = hit['_source']['process_id']
            gwp = hit['_source']['gwp']
            gwp_mapping[process_id] = gwp  # 创建 process_id 到 gwp 的映射

        # 滚动到下一批文档
        response = es.scroll(scroll_id=scroll_id, scroll=scroll_time)
        hits = response['hits']['hits']
    
    # 清除 scroll ID
    es.clear_scroll(scroll_id=scroll_id)
    
    return gwp_mapping

# 更新 filteredprocesses_index 中的 ratio 字段
def update_filtered_processes_with_ratio(es, filtered_index, gwp_mapping):
    query = {
        "_source": ["process_id", "flow_amount"],
        "query": {
            "exists": { "field": "flow_amount" }  # 只获取有flow_amount字段的文档
        }
    }
    
    response = es.search(index=filtered_index, body=query, scroll=scroll_time, size=batch_size)
    scroll_id = response['_scroll_id']
    hits = response['hits']['hits']
    
    while hits:
        actions = []
        for hit in hits:
            source = hit['_source']
            doc_id = hit['_id']
            process_id = source.get("process_id")
            flow_amount = source.get("flow_amount", None)
            
            # 确保 flow_amount 和 process_id 存在
            if process_id and flow_amount and process_id in gwp_mapping:
                gwp_value = gwp_mapping[process_id]
                
                # 确保 gwp 不为零，避免除零错误
                if gwp_value != 0:
                    ratio = flow_amount / gwp_value
                else:
                    ratio = None  # 如果gwp为0，则设置ratio为None
                    
                # 准备更新文档
                action = {
                    "_op_type": "update",
                    "_index": filtered_index,
                    "_id": doc_id,
                    "doc": { "ratio": ratio }
                }
                actions.append(action)

        # 批量更新文档
        if actions:
            helpers.bulk(es, actions)

        # 滚动到下一批文档
        response = es.scroll(scroll_id=scroll_id, scroll=scroll_time)
        hits = response['hits']['hits']
    
    # 清除 scroll ID
    es.clear_scroll(scroll_id=scroll_id)

# 第一步：获取 uniqueaggregatedgwp_index 中的 gwp 映射
gwp_mapping = get_gwp_mapping(es, aggregated_index)

# 第二步：更新 filteredprocesses_index 中的 ratio 字段
update_filtered_processes_with_ratio(es, filtered_index, gwp_mapping)

print("Ratio 字段更新完成")
