from elasticsearch import Elasticsearch, helpers
import os
from collections import defaultdict

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
            "flow_unit": {"type": "keyword"},
            "flow_type": {"type": "keyword"},
            "flow_direction": {"type": "keyword"},
            "location_country": {"type": "keyword"},
            "gwp": {"type": "double"}
        }
    }
}

if not es.indices.exists(index="uniqueaggregatedgwp_index"):
    es.indices.create(index="uniqueaggregatedgwp_index", body=process_mapping)

# 源索引和目标索引
source_index = "processeswithghg_index"
target_index = "uniqueaggregatedgwp_index"

# Scroll API 参数设置
scroll_time = "2m"
batch_size = 1000

# 需要聚合的字段
fields_to_check = [
    "flow_direction", "flow_type", "flow_unit", "location_country",
    "process_category", "process_id", "process_location", "process_name", "process_type"
]

# 初始化存储聚合结果的字典
aggregation_results = defaultdict(lambda: {
    "gwp_sum": 0,
    "fields": {field: None for field in fields_to_check}
})

# Scroll API 读取源索引中的文档
def aggregate_documents():
    query = {
        "_source": ["gwp"] + fields_to_check,  # 只取需要的字段
        "size": batch_size,
        "query": {"match_all": {}}
    }

    response = es.search(index=source_index, body=query, scroll=scroll_time)
    scroll_id = response['_scroll_id']
    hits = response['hits']['hits']

    while len(hits) > 0:
        for hit in hits:
            doc_id = hit['_id']
            source = hit['_source']
            process_id = source['process_id']

            # 累加 gwp 字段
            if 'gwp' in source and isinstance(source['gwp'], (int, float)):
                aggregation_results[process_id]["gwp_sum"] += source['gwp']

            # 对其他字段进行聚合检查，如果一致则保留，否则设置为 None
            for field in fields_to_check:
                field_value = source.get(field)
                if aggregation_results[process_id]["fields"][field] is None:
                    aggregation_results[process_id]["fields"][field] = field_value
                elif aggregation_results[process_id]["fields"][field] != field_value:
                    aggregation_results[process_id]["fields"][field] = None

        # 获取下一批文档
        response = es.scroll(scroll_id=scroll_id, scroll=scroll_time)
        hits = response['hits']['hits']

    # 清除 scroll
    es.clear_scroll(scroll_id=scroll_id)

# 将聚合结果写入新索引
def write_aggregated_results():
    actions = []
    for process_id, result in aggregation_results.items():
        doc = {
            "_op_type": "index",
            "_index": target_index,
            "_id": process_id,
            "gwp": result["gwp_sum"],
            **result["fields"]
        }
        actions.append(doc)

        # 批量写入
        if len(actions) >= batch_size:
            helpers.bulk(es, actions)
            actions = []

    # 写入剩余的文档
    if actions:
        helpers.bulk(es, actions)

# 执行聚合和写入
aggregate_documents()
write_aggregated_results()

print(f"Aggregation completed and results written to {target_index}.")