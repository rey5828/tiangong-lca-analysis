from elasticsearch import Elasticsearch, helpers
import json
from collections import defaultdict
import time
from tqdm import tqdm
import os

# Elasticsearch 连接配置
es = Elasticsearch(
    hosts=["http://39.105.216.221:9200/"],
    basic_auth=(os.getenv("USERNAME"), os.getenv("PASSWORD")),
)

# 源索引和目标索引名称
SOURCE_INDEX = "processwithghg_dedup2"
TARGET_INDEX = "process_unit_claude"  # 新索引的名称

# 定义索引映射
mapping = {
    "mappings": {
        "properties": {
            "category": {"type": "keyword"},
            "eco_quality": {"type": "double"},
            "flow_amount": {"type": "double"},
            "flow_category": {"type": "keyword"},
            "flow_direction": {"type": "keyword"},
            "flow_id": {"type": "keyword"},
            "flow_name": {"type": "keyword"},
            "flow_type": {"type": "keyword"},
            "flow_unit": {"type": "keyword"},
            "gwp": {"type": "double"},
            "human_health": {"type": "double"},
            "process_category": {"type": "keyword"},
            "process_id": {"type": "keyword"},
            "process_location": {"type": "keyword"},
            "process_name": {"type": "keyword"},
            "process_type": {"type": "keyword"},
            "ratio": {"type": "double"},
            "resources": {"type": "double"}
        }
    }
}

def create_new_index():
    """创建新索引"""
    # 如果索引已存在则删除
    if es.indices.exists(index=TARGET_INDEX):
        es.indices.delete(index=TARGET_INDEX)
    
    # 创建新索引
    es.indices.create(index=TARGET_INDEX, body=mapping)
    print(f"创建索引 {TARGET_INDEX} 成功")

def copy_filtered_documents():
    """复制符合条件的文档到新索引"""
    query = {
        "query": {
            "bool": {
                "must": [
                    {"term": {"flow_type": "ELEMENTARY_FLOW"}},
                    {"term": {"process_type": "UNIT_PROCESS"}}
                ]
            }
        }
    }
    
    # 设置批量操作
    def process_hits(hits):
        for hit in hits:
            yield {
                "_index": TARGET_INDEX,
                "_source": hit["_source"]
            }
    
    # 获取文档总数
    count = es.count(index=SOURCE_INDEX, body=query)["count"]
    print(f"需要复制的文档总数: {count}")
    
    # 使用scroll API来处理大量数据
    scan_resp = helpers.scan(
        client=es,
        query=query,
        index=SOURCE_INDEX,
        scroll="10m"
    )
    
    # 批量索引文档
    success, failed = helpers.bulk(
        client=es,
        actions=process_hits(scan_resp),
        stats_only=True,
        chunk_size=1000,
        request_timeout=60
    )
    
    print(f"成功索引 {success} 条文档, 失败 {failed} 条")
    
    # 刷新索引确保所有数据都可见
    es.indices.refresh(index=TARGET_INDEX)

def analyze_processes():
    """分析新索引中的数据，找出具有相同输入/输出的process_id"""
    # 获取所有唯一的process_id
    process_query = {
        "size": 0,
        "aggs": {
            "unique_processes": {
                "terms": {
                    "field": "process_id",
                    "size": 100000  # 足够大以获取所有process_id
                }
            }
        }
    }
    
    process_response = es.search(index=TARGET_INDEX, body=process_query)
    process_buckets = process_response["aggregations"]["unique_processes"]["buckets"]
    
    print(f"找到 {len(process_buckets)} 个唯一的process_id")
    
    # 存储每个process的输入和输出flow_id
    process_data = {}
    
    # 遍历每个process_id，获取其输入和输出flow
    for process_bucket in tqdm(process_buckets, desc="分析过程"):
        process_id = process_bucket["key"]
        
        # 获取process的基本信息
        basic_info_query = {
            "size": 1,
            "query": {
                "term": {"process_id": process_id}
            }
        }
        
        basic_info = es.search(index=TARGET_INDEX, body=basic_info_query)["hits"]["hits"]
        if basic_info:
            process_name = basic_info[0]["_source"]["process_name"]
            process_category = basic_info[0]["_source"]["process_category"]
            gwp = basic_info[0]["_source"].get("gwp", 0)
        else:
            process_name = "Unknown"
            process_category = "Unknown"
            gwp = 0
        
        # 获取输入flow
        input_query = {
            "size": 10000,
            "query": {
                "bool": {
                    "must": [
                        {"term": {"process_id": process_id}},
                        {"term": {"flow_direction": "input"}}
                    ]
                }
            }
        }
        
        input_response = es.search(index=TARGET_INDEX, body=input_query)
        input_flows = [hit["_source"]["flow_id"] for hit in input_response["hits"]["hits"]]
        
        # 获取输出flow
        output_query = {
            "size": 10000,
            "query": {
                "bool": {
                    "must": [
                        {"term": {"process_id": process_id}},
                        {"term": {"flow_direction": "output"}}
                    ]
                }
            }
        }
        
        output_response = es.search(index=TARGET_INDEX, body=output_query)
        output_flows = [hit["_source"]["flow_id"] for hit in output_response["hits"]["hits"]]
        
        # 存储数据
        process_data[process_id] = {
            "process_name": process_name,
            "process_category": process_category,
            "gwp": gwp,
            "input_flows": input_flows,
            "output_flows": output_flows,
            "input_count": len(input_flows),
            "output_count": len(output_flows)
        }
    
    # 寻找具有相同输入/输出流的进程
    similar_processes = defaultdict(list)
    
    print("开始查找具有相同输入/输出流的进程...")
    process_ids = list(process_data.keys())
    
    for i in tqdm(range(len(process_ids)), desc="比较进程"):
        pid1 = process_ids[i]
        p1_data = process_data[pid1]
        
        # 创建特征键: 输入流数量和输出流数量
        feature_key = f"{p1_data['input_count']}_{p1_data['output_count']}"
        
        similar_processes[feature_key].append({
            "process_id": pid1,
            "process_name": p1_data["process_name"],
            "process_category": p1_data["process_category"],
            "gwp": p1_data["gwp"]
        })
    
    # 保存结果到JSON文件
    result = {
        "similar_processes_by_io_count": dict(similar_processes)
    }
    
    with open("process_analysis_results.json", "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    
    print("分析完成，结果已保存到 process_analysis_results.json")

def main():
    start_time = time.time()
    
    create_new_index()
    copy_filtered_documents()
    analyze_processes()
    
    elapsed_time = time.time() - start_time
    print(f"脚本执行完成，总耗时: {elapsed_time:.2f} 秒")

if __name__ == "__main__":
    main()