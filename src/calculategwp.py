import pandas as pd
from elasticsearch import Elasticsearch, helpers
import os

# 初始化Elasticsearch连接
es = Elasticsearch(
    hosts=["http://39.105.216.221:9200/"],
    basic_auth=(os.getenv("USERNAME"), os.getenv("PASSWORD")),
)

# Define the mapping with the new field
mapping = {
    "properties": {
        "gwp": {"type": "double"}
    }
}

# Update the index with the new mapping
index_name = "processeswithghg_index"
es.indices.put_mapping(index=index_name, body=mapping)

# 步骤 1：读取 CSV 文件，获取 id 和 value 列
csv_file_path = r"/mnt/d/json/extracted_ghgflows.csv"
df = pd.read_csv(csv_file_path)

# 将 CSV 数据转换为字典，方便查找
csv_data = dict(zip(df['id'], df['value']))

# 使用 Scroll API 参数设置
scroll_time = "2m"  # 滚动窗口时间
batch_size = 1000   # 每次获取的文档数量

# 步骤 2：定义查询，搜索与 CSV 文件中 id 匹配的 flow_id
def update_gwp_field(es, index_name, csv_data, scroll_time="2m", batch_size=1000):
    # 初始化 Scroll API 查询
    query = {
        "_source": ["flow_id", "flow_amount"],  # 只获取必要字段
        "size": batch_size,
        "query": {
            "terms": {
                "flow_id": list(csv_data.keys())  # 匹配 CSV 中的 id 列
            }
        }
    }
    
    # 开始 Scroll API 获取初始数据
    response = es.search(index=index_name, body=query, scroll=scroll_time)
    scroll_id = response['_scroll_id']
    hits = response['hits']['hits']
    
    while len(hits) > 0:
        actions = []
        for hit in hits:
            # 获取文档ID和flow_amount值
            doc_id = hit['_id']
            flow_id = hit['_source']['flow_id']
            flow_amount = hit['_source'].get('flow_amount')

            # 检查 flow_amount 是否存在
            if flow_amount is None:
                # 如果 flow_amount 不存在，将其设为 'NA' 并记录
                gwp_value = 'NA'
            else:
                # 如果 flow_amount 存在，执行乘法运算
                gwp_value = flow_amount * csv_data[flow_id]

            # 准备批量更新操作
            actions.append({
                "_op_type": "update",
                "_index": index_name,
                "_id": doc_id,
                "doc": {
                    "gwp": gwp_value
                }
            })

        # 批量更新
        if actions:
            helpers.bulk(es, actions)

        # 获取下一批文档
        response = es.scroll(scroll_id=scroll_id, scroll=scroll_time)
        hits = response['hits']['hits']

    # 清除 Scroll API
    es.clear_scroll(scroll_id=scroll_id)

    print("All matching documents have been updated.")

# 步骤 3：执行更新操作
update_gwp_field(es, index_name, csv_data)

print("All matching documents have been updated.")
