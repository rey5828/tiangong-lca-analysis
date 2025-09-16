from elasticsearch import Elasticsearch, helpers
from collections import defaultdict
import os

es = Elasticsearch(
    hosts=["http://39.105.216.221:9200/"],
    basic_auth=(os.getenv("USERNAME"), os.getenv("PASSWORD")),
)

# 源索引和目标索引
source_index = "filteredprocesses_index"
target_index = "uniqueprocess"

# 1. 获取所有process_id及其对应的文档
def get_all_documents():
    # 使用scroll方式处理大数据量的索引
    query = {
        "size": 10000,  # 一次获取的文档数，可以调整
        "_source": ["process_id", "flow_name", "flow_id", "flow_amount", "flow_unit", "*"],  # 获取所有字段
        "query": {
            "match_all": {}
        }
    }
    results = helpers.scan(es, query=query, index=source_index)
    process_data = {}
    
    # 将文档按process_id进行分组
    for doc in results:
        process_id = doc['_source']['process_id']
        if process_id not in process_data:
            process_data[process_id] = []
        process_data[process_id].append(doc)
    
    return process_data

# 2. 对比两个process下的所有flow
def are_flows_identical(process1, process2):
    flows1 = sorted([(f['_source']['flow_name'], f['_source']['flow_id'], f['_source']['flow_amount'], f['_source']['flow_unit']) for f in process1])
    flows2 = sorted([(f['_source']['flow_name'], f['_source']['flow_id'], f['_source']['flow_amount'], f['_source']['flow_unit']) for f in process2])
    
    return flows1 == flows2

# 3. 过滤重复process，保留唯一process的完整文档
def filter_unique_processes(process_data):
    unique_processes = []
    processed = set()  # 用于存储已经比较过的process_id
    
    process_ids = list(process_data.keys())
    
    for i, process_id_1 in enumerate(process_ids):
        if process_id_1 in processed:
            continue
        
        is_unique = True
        process1 = process_data[process_id_1]
        
        for j in range(i + 1, len(process_ids)):
            process_id_2 = process_ids[j]
            if process_id_2 in processed:
                continue
            
            process2 = process_data[process_id_2]
            
            # 如果两个process的flow相同，保留一个，标记已处理
            if are_flows_identical(process1, process2):
                processed.add(process_id_2)
                is_unique = False
        
        if is_unique:
            unique_processes.extend(process1)
        
        processed.add(process_id_1)
    
    return unique_processes

# 4. 将去重后的文档写入新的索引
def write_to_new_index(unique_processes):
    actions = [
        {
            "_index": target_index,
            "_source": doc['_source']
        }
        for doc in unique_processes
    ]
    
    helpers.bulk(es, actions)

# 主函数
if __name__ == "__main__":
    # 1. 获取所有文档并按process_id分组
    process_data = get_all_documents()
    
    # 2. 过滤唯一的process文档
    unique_processes = filter_unique_processes(process_data)
    
    # 3. 写入到新的索引中
    write_to_new_index(unique_processes)
    
    print(f"去重后的文档已写入索引 {target_index}")
