from elasticsearch import Elasticsearch
import pandas as pd
import os

es = Elasticsearch(
    hosts=["http://39.105.216.221:9200/"],
    basic_auth=(os.getenv("USERNAME"), os.getenv("PASSWORD")),
)
# 定义索引名称
index_name = 'processeswithghg_index2'

# 查询所有文档
query = {
    "query": {
        "match_all": {}
    }
}

# 使用scroll API获取所有文档
scroll = es.search(index=index_name, body=query, scroll='2m', size=1000)
scroll_id = scroll['_scroll_id']
hits = scroll['hits']['hits']

# 存储所有文档
all_hits = []
all_hits.extend(hits)

while len(hits) > 0:
    scroll = es.scroll(scroll_id=scroll_id, scroll='2m')
    hits = scroll['hits']['hits']
    all_hits.extend(hits)

# 将文档转换为DataFrame
df = pd.DataFrame([hit['_source'] for hit in all_hits])

# 导出为CSV文件
csv_file_path = r"/mnt/d/json/output.csv"
df.to_csv(csv_file_path, index=False)

# 导出为Excel文件
excel_file_path = r"/mnt/d/json/output.xlsx"
df.to_excel(excel_file_path, index=False)

print(f"Data exported to {csv_file_path} and {excel_file_path}")
