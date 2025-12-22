from elasticsearch import Elasticsearch, helpers
import os

# 配置 Elasticsearch 连接
es = Elasticsearch(
    hosts=["http://39.105.216.221:9200/"],
    basic_auth=(os.getenv("USERNAME"), os.getenv("PASSWORD")),
)

# 定义索引名称和新字段名称
index_name = "filtereduniqueprocess"
sort_field = "sort"

# 为每个文档添加排序字段值
def add_sort_value():
    # 初始化 scroll 查询获取所有文档
    query = {"query": {"match_all": {}}}
    response = es.search(index=index_name, body=query, scroll="5m", size=1000)
    scroll_id = response['_scroll_id']
    
    # 初始化计数器
    count = 1
    actions = []
    
    while response['hits']['hits']:
        for doc in response['hits']['hits']:
            # 为每个文档生成更新操作，将 sort 字段设为计数器的值
            action = {
                "_op_type": "update",
                "_index": index_name,
                "_id": doc["_id"],
                "doc": {sort_field: count}
            }
            actions.append(action)
            count += 1
            
            # 批量提交每 1000 条更新操作
            if len(actions) == 1000:
                helpers.bulk(es, actions)
                actions.clear()
        
        # 获取下一批文档
        response = es.scroll(scroll_id=scroll_id, scroll="5m")
        scroll_id = response['_scroll_id']
    
    # 提交剩余的更新操作
    if actions:
        helpers.bulk(es, actions)
    
    # 清除 scroll context
    es.clear_scroll(scroll_id=scroll_id)
    print("All documents updated with sort values.")

# 执行更新
add_sort_value()
