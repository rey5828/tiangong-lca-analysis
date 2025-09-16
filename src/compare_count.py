from elasticsearch import Elasticsearch
from elasticsearch.helpers import scan
import os

# 初始化 Elasticsearch 客户端
es = Elasticsearch(
    hosts=["http://39.105.216.221:9200/"],
    basic_auth=(os.getenv("USERNAME"), os.getenv("PASSWORD")),
)

# 索引名称
filtered_index = "filteredprocesses_index"
original_index = "process_index"

def get_process_counts(index_name):
    """
    提取索引中所有 process_id 和其对应的文档数量
    """
    process_counts = {}
    
    # 使用 scan 高效提取所有文档的 process_id
    query = {
        "_source": ["process_id"],
        "query": {"match_all": {}}
    }
    
    for doc in scan(es, index=index_name, query=query):
        process_id = doc["_source"]["process_id"]
        if process_id not in process_counts:
            process_counts[process_id] = 0
        process_counts[process_id] += 1
    
    return process_counts

def compare_counts(filtered_counts, original_counts):
    """
    比较两个索引中的文档数量
    """
    inconsistencies = []
    
    for process_id, filtered_count in filtered_counts.items():
        original_count = original_counts.get(process_id, 0)
        if filtered_count != original_count:
            inconsistencies.append((process_id, filtered_count, original_count))
    
    return inconsistencies

# 提取两个索引中的 process_id 文档数量
print("提取 filteredprocesses_index 中的文档计数...")
filtered_counts = get_process_counts(filtered_index)

print("提取 process_index 中的文档计数...")
original_counts = get_process_counts(original_index)

# 比较两个索引中的文档数量
print("比较两个索引中的文档计数...")
inconsistencies = compare_counts(filtered_counts, original_counts)

# 输出不一致的结果
if inconsistencies:
    print("以下 process_id 在两个索引中的文档计数不一致：")
    for process_id, filtered_count, original_count in inconsistencies:
        print(f"process_id: {process_id}, filtered_count: {filtered_count}, original_count: {original_count}")
else:
    print("所有 process_id 的文档计数一致！")
