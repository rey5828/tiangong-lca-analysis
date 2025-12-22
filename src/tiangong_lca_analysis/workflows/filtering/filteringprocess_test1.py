import logging
from elasticsearch import Elasticsearch, helpers
from collections import defaultdict
import math
import os
import numpy as np 

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

if not es.indices.exists(index="processwithghg_dedup3"):
    es.indices.create(index="processwithghg_dedup3", body=process_mapping)


# 定义索引名称
source_index = "filteredprocesses_index"
target_index = "processwithghg_dedup3"


# 配置日志
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

def fetch_total_doc_count():
    """获取总文档数"""
    return es.count(index=source_index)["count"]

def fetch_processes_by_batch(batch_size=10000):
    """分页获取流程数据"""
    query = {
        "size": batch_size,
        "query": {"match_all": {}},
        "sort": ["process_id"]
    }

    processes = helpers.scan(
        client=es,
        query=query,
        index=source_index,
        preserve_order=True
    )
    return processes

def are_flows_identical(flow1, flow2):
    """检查两个 flow 是否完全相同"""
    fields_to_compare = ["flow_id", "flow_name", "flow_amount", "flow_unit", "flow_category", "flow_direction", "flow_type"]
    return all(flow1[field] == flow2[field] for field in fields_to_compare)

def is_proportionally_scaled(group1, group2):
    """改进的比例判断"""
    ratios = []
    
    # 确保我们在处理列表
    flows1 = group1 if isinstance(group1, list) else [group1]
    flows2 = group2 if isinstance(group2, list) else [group2]
    
    for flow1, flow2 in zip(flows1, flows2):
        if (isinstance(flow1, dict) and isinstance(flow2, dict) and
            flow1.get("flow_id") == flow2.get("flow_id") and 
            flow1.get("flow_name") == flow2.get("flow_name")):
            amount1 = flow1.get("flow_amount", 0)
            amount2 = flow2.get("flow_amount", 0)
            if amount1 > 0 and amount2 > 0:
                ratios.append(amount2 / amount1)
    
    if not ratios:
        return False
        
    return np.std(ratios) < 0.000001

def filter_and_write_batch(process_batch):
    """改进的筛选逻辑"""
    unique_processes = {}
    to_remove = set()
    
    # 按process name的第一部分分组
    name_groups = defaultdict(list)
    process_flows = defaultdict(list)

    # 首先按process_id组织flows
    for process in process_batch:
        doc = process["_source"]
        process_flows[doc["process_id"]].append(doc)
    
    # 然后按name第一部分分组
    for process_id, flows in process_flows.items():
        if flows:  # 确保flows不为空
            first_part = flows[0]["process_name"].split("|")[0].strip()
            name_groups[first_part].append((process_id, flows))
    
    # 处理每个组
    for group in name_groups.values():
        for i in range(len(group)):
            for j in range(i + 1, len(group)):
                pid1, flows1 = group[i]
                pid2, flows2 = group[j]
                
                if is_proportionally_scaled(flows1, flows2):
                    to_remove.add(pid2)
    
    # 写入不在to_remove中的process
    actions = []
    for process in process_batch:
        if process["_source"]["process_id"] not in to_remove:
            actions.append({
                "_index": target_index,
                "_source": process["_source"]
            })
    
    if actions:
        helpers.bulk(es, actions)

# 主流程
if __name__ == "__main__":
    total_docs = fetch_total_doc_count()
    batch_size = 10000
    processed_docs = 0
    process_batch = []

    logger.info(f"开始筛选流程，总文档数: {total_docs}")

    for process in fetch_processes_by_batch(batch_size=batch_size):
        process_batch.append(process)
        if len(process_batch) >= batch_size:
            filter_and_write_batch(process_batch)
            processed_docs += len(process_batch)
            process_batch = []
            progress = (processed_docs / total_docs) * 100
            logger.info(f"已处理文档数: {processed_docs}/{total_docs} ({progress:.2f}%)")

    # 处理剩余批次
    if process_batch:
        filter_and_write_batch(process_batch)
        processed_docs += len(process_batch)
        progress = (processed_docs / total_docs) * 100
        logger.info(f"已处理文档数: {processed_docs}/{total_docs} ({progress:.2f}%)")

    logger.info(f"筛选完成，已将唯一流程写入索引 {target_index}")
