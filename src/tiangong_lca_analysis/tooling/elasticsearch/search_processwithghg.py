import pandas as pd
from elasticsearch import Elasticsearch, helpers
import os

es = Elasticsearch(
    hosts=["http://39.105.216.221:9200/"],
    basic_auth=(os.getenv("USERNAME"), os.getenv("PASSWORD")),
)

process_mapping = {
    "mappings": {
        "properties": {
            "process_id": {"type": "keyword"},
            "process_name": {"type": "keyword"},
            "process_type": {"type": "keyword"},
            "process_category": {"type": "keyword"},
            "process_location": {"type": "keyword"},
            "flow_id": {"type": "keyword"},
            "flow_amount": {"type": "double"},
            "flow_unit": {"type": "keyword"},
            "flow_name": {"type": "keyword"},
            "flow_type": {"type": "keyword"},
            "flow_category": {"type": "keyword"},
            "flow_direction": {"type": "keyword"}
        }
    }
}

if not es.indices.exists(index="filteredprocesses_index"):
    es.indices.create(index="filteredprocesses_index", body=process_mapping)

# 配置索引名
process_index2 = "process_index"  
new_index = "filteredprocesses_index"  

# 定义查询，获取所有文档的 process_id 字段
query_all_process_ids = {
    "_source": ["process_id"],
    "query": {
        "match_all": {}
    }
}

# 使用 Scroll API 获取所有文档
scroll_time = "2m"
index_name = "processeswithghg_index"
response = es.search(index=index_name, body=query_all_process_ids, scroll=scroll_time)
scroll_id = response['_scroll_id']
hits = response['hits']['hits']

process_ids = set()

while len(hits) > 0:
    for hit in hits:
        process_id = hit['_source'].get('process_id')
        if process_id:
            process_ids.add(process_id)
    
    response = es.scroll(scroll_id=scroll_id, scroll=scroll_time)
    scroll_id = response['_scroll_id']
    hits = response['hits']['hits']

# 将去重后的 process_id 写入数据框
csv_process_ids = pd.DataFrame(list(process_ids), columns=['process_id'])

# Scroll API 参数设置
scroll_time = "2m"  # 滚动窗口时间
batch_size = 1000   # 每次获取的文档数量

# 步骤 2：定义查询，使用 CSV 中的 process_id 进行查询
def search_and_export_processes(es, csv_process_ids, source_index, target_index, batch_size=1000):
    query = {
        "_source": True,  # 导出所有字段
        "size": batch_size,
        "query": {
            "terms": {
                "process_id": csv_process_ids['process_id'].tolist()  # 根据 CSV 中的 process_id 查询
            }
        }
    }

    # 使用 Scroll API 初始化
    response = es.search(index=source_index, body=query, scroll=scroll_time)
    scroll_id = response['_scroll_id']
    matching_documents = response['hits']['hits']

    # 更新 scroll_id
    total_documents = len(response['hits']['hits'])

    # 继续滚动获取文档
    while len(response['hits']['hits']) > 0:
        actions = [
            {
                "_op_type": "index",  # index 操作
                "_index": target_index,  # 新索引
                "_source": doc["_source"]
            }
            for doc in response['hits']['hits']
        ]

        # 使用 bulk 操作将文档导入新索引
        helpers.bulk(es, actions)

        # 获取下一批文档，并更新 scroll_id
        response = es.scroll(scroll_id=scroll_id, scroll=scroll_time)
        scroll_id = response['_scroll_id']
        matching_documents.extend(response['hits']['hits'])
        total_documents += len(response['hits']['hits'])

    # 清除 scroll
    es.clear_scroll(scroll_id=scroll_id)

    print(f"Total documents exported to {target_index}: {len(matching_documents)}")


# 步骤 3：处理 process_id 超过 Elasticsearch 限制的情况
# Elasticsearch 的 terms 查询有一个限制，最多支持 65536 个条目，所以需要对 process_id 列进行分块处理
chunk_size = 1000  # 每次处理 1000 个 process_id

for i in range(0, len(csv_process_ids), chunk_size):
    chunk = csv_process_ids[i:i + chunk_size]
    search_and_export_processes(es, chunk, process_index2, new_index, batch_size)

print("All matching documents have been exported.")
