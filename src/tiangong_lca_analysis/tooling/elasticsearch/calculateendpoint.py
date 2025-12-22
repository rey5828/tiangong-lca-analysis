import csv
import json
from elasticsearch import Elasticsearch, helpers
import os

es = Elasticsearch(
    hosts=["http://39.105.216.221:9200/"],
    basic_auth=(os.getenv("USERNAME"), os.getenv("PASSWORD")),
)

# CSV 文件路径
csv_file_path = r"/mnt/d/json/extracted_flows/merged_flows.csv"

# 索引名称
index_name = "processwithghg_dedup2"

# Add mapping for new fields
mapping_body = {
    "properties": {
        "human_health": {
            "type": "double"
        },
        "eco_quality": {
            "type": "double"
        },
        "resources": {
            "type": "double"
        }
    }
}

try:
    # Update index mapping
    response = es.indices.put_mapping(
        index=index_name,
        body=mapping_body
    )
    
    if response.get('acknowledged'):
        print(f"Successfully added fields to index {index_name}")
    else:
        print("Failed to update mapping")
        
except Exception as e:
    print(f"Error updating mapping: {str(e)}")

# 批量大小
batch_size = 1000
scroll_time = "2m"

def convert_csv_to_json(csv_file, json_file):
    data = []
    with open(csv_file, mode='r', encoding='utf-8') as file:
        reader = csv.DictReader(file)
        for row in reader:
            data.append({
                'flow_id': row['flow_id'],
                'human_health': row['Total human health no LT'] or 0,
                'eco_quality': row['Total ecosystem quality no LT'] or 0,
                'resources': row['Total natural resources no LT'] or 0
            })
    
    with open(json_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

# Convert CSV to JSON
json_file_path = csv_file_path.replace('.csv', '.json')
convert_csv_to_json(csv_file_path, json_file_path)

def read_json_mapping(json_file):
    csv_mapping = {}
    with open(json_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
        for row in data:
            csv_mapping[row['flow_id']] = {
                'human_health': float(row['human_health']),
                'eco_quality': float(row['eco_quality']),
                'resources': float(row['resources'])
            }
    return csv_mapping

# 更新 Elasticsearch 索引
def update_elasticsearch(index_name, csv_mapping):
    # 使用滚动 API 搜索所有文档
    query = {"query": {"match_all": {}}}
    results = es.search(index=index_name, body=query, scroll=scroll_time, size=batch_size)

    # 获取初始 scroll_id 和搜索结果
    scroll_id = results['_scroll_id']
    hits = results['hits']['hits']

    while hits:
        actions = []

        for hit in hits:
            doc_id = hit['_id']
            source = hit['_source']
            flow_id = source.get('flow_id')
            ratio = source.get('ratio', 1)

            # 查找 CSV 中的 flow_id 并计算值
            if flow_id in csv_mapping:
                csv_data = csv_mapping[flow_id]
                human_health = ratio * csv_data['human_health']
                eco_quality = ratio * csv_data['eco_quality']
                resources = ratio * csv_data['resources']
            else:
                human_health = eco_quality = resources = 0

            # 准备更新操作
            action = {
                '_op_type': 'update',
                '_index': index_name,
                '_id': doc_id,
                'doc': {
                    'human_health': human_health,
                    'eco_quality': eco_quality,
                    'resources': resources
                }
            }
            actions.append(action)

        # 批量更新 Elasticsearch
        if actions:
            helpers.bulk(es, actions)

        # 获取下一批结果
        results = es.scroll(scroll_id=scroll_id, scroll=scroll_time)
        hits = results['hits']['hits']

# Read JSON and create mapping
csv_mapping = read_json_mapping(json_file_path)

# Update Elasticsearch
update_elasticsearch(index_name, csv_mapping)

print("更新完成。")
