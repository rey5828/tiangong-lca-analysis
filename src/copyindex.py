from elasticsearch import Elasticsearch, helpers
import os

es = Elasticsearch(
    hosts=["http://39.105.216.221:9200/"],
    basic_auth=(os.getenv("USERNAME"), os.getenv("PASSWORD")),
)

# 设置原始索引和目标索引名称
source_index = "filteredprocesses_index"
target_index = "processsdep_validation_index"

def copy_index_with_mapping(es, source_index, target_index, chunk_size=5000):
    # 1. 获取源索引的映射
    try:
        source_mapping = es.indices.get_mapping(index=source_index)
        
        # 2. 获取源索引的设置
        source_settings = es.indices.get_settings(index=source_index)
        
        # 提取实际映射和设置
        mapping = source_mapping[source_index]['mappings']
        settings = {
            'settings': {
                'number_of_shards': source_settings[source_index]['settings']['index']['number_of_shards'],
                'number_of_replicas': source_settings[source_index]['settings']['index']['number_of_replicas']
            }
        }
        
        # 3. 检查目标索引是否存在，如果存在则删除
        if es.indices.exists(index=target_index):
            es.indices.delete(index=target_index)
            print(f"Deleted existing index: {target_index}")
        
        # 4. 使用相同的映射和设置创建目标索引
        es.indices.create(
            index=target_index,
            body={**settings, 'mappings': mapping}
        )
        print(f"Created target index: {target_index} with matching mapping")
        
        # 5. 使用 scan 逐批读取数据
        res = helpers.scan(
            client=es,
            index=source_index,
            query={"query": {"match_all": {}}},
            scroll="5m"
        )

        # 创建批量操作列表
        actions = []
        for count, doc in enumerate(res, 1):
            # 构建批量写入操作，保留原始文档ID
            actions.append({
                "_op_type": "index",
                "_index": target_index,
                "_id": doc["_id"],  # 保持ID一致
                "_source": doc["_source"],
            })
            
            # 每 chunk_size 个文档写入一次
            if len(actions) >= chunk_size:
                helpers.bulk(es, actions)
                actions = []  # 清空批量操作列表
                print(f"{count} documents copied...")

        # 写入最后一批文档
        if actions:
            helpers.bulk(es, actions)

        print("Index copy completed with identical mapping.")
        
    except Exception as e:
        print(f"Error copying index: {str(e)}")

# 执行复制操作
copy_index_with_mapping(es, source_index, target_index)
