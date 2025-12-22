from elasticsearch import Elasticsearch, helpers
import os
from collections import defaultdict
import logging

logging.basicConfig(level=logging.INFO)

class ProcessFlowMerger:
    def __init__(self, es, source_index, batch_size=1000):
        self.es = es
        self.source_index = source_index
        self.batch_size = batch_size
        self.scroll_time = "2m"

    def create_index_with_mapping(self, target_index):
        """复制源索引的映射到目标索引"""
        try:
            # 1. 获取源索引的映射
            source_mapping = self.es.indices.get_mapping(index=self.source_index)
            
            # 2. 获取源索引的设置
            source_settings = self.es.indices.get_settings(index=self.source_index)
            
            # 提取实际映射和设置
            mapping = source_mapping[self.source_index]['mappings']
            settings = {
                'settings': {
                    'number_of_shards': source_settings[self.source_index]['settings']['index']['number_of_shards'],
                    'number_of_replicas': source_settings[self.source_index]['settings']['index']['number_of_replicas']
                }
            }
            
            # 3. 检查目标索引是否存在，如果存在则删除
            if self.es.indices.exists(index=target_index):
                self.es.indices.delete(index=target_index)
                logging.info(f"Deleted existing index: {target_index}")
            
            # 4. 使用相同的映射和设置创建目标索引
            self.es.indices.create(
                index=target_index,
                body={**settings, 'mappings': mapping}
            )
            logging.info(f"Created target index: {target_index} with identical mapping")
            
            return True
        except Exception as e:
            logging.error(f"Error creating index with mapping: {str(e)}")
            return False

    def scroll_documents(self):
        query = {"query": {"match_all": {}}}
        response = self.es.search(
            index=self.source_index,
            body=query,
            scroll=self.scroll_time,
            size=self.batch_size
        )
        
        scroll_id = response['_scroll_id']
        hits = response['hits']['hits']
        
        try:
            while hits:
                for hit in hits:
                    yield hit
                
                response = self.es.scroll(scroll_id=scroll_id, scroll=self.scroll_time)
                hits = response['hits']['hits']
        finally:
            # 清理scroll上下文
            try:
                self.es.clear_scroll(scroll_id=scroll_id)
            except:
                pass

    def process_batch(self, batch_docs):
        """处理一批文档，按process_id分组并合并flows"""
        process_flows = defaultdict(list)
        for hit in batch_docs:
            flow = hit['_source']
            flow['_id'] = hit['_id']
            process_flows[flow['process_id']].append(flow)
        
        # 对每个process内的flows进行合并
        merged_process_flows = {}
        for pid, flows in process_flows.items():
            merged_flows = self.merge_same_flows(flows)
            merged_process_flows[pid] = merged_flows
        
        return merged_process_flows

    def merge_same_flows(self, process_flows):
        """合并同一process中相同flow_id的流程"""
        flow_groups = defaultdict(list)
        for flow in process_flows:
            flow_groups[flow['flow_id']].append(flow)
        
        merged_flows = []
        for flow_id, group in flow_groups.items():
            if len(group) > 1:
                base_flow = group[0].copy()
                for additional_flow in group[1:]:
                    base_flow['flow_amount'] += additional_flow.get('flow_amount', 0)
                merged_flows.append(base_flow)
            else:
                merged_flows.append(group[0])
        
        return merged_flows

    def merge_and_write(self, target_index):
        """合并flows并写入新索引"""
        # 首先创建具有相同映射的目标索引
        if not self.create_index_with_mapping(target_index):
            logging.error("Failed to create target index with mapping. Aborting.")
            return
            
        processed_docs = 0
        current_batch = []
        
        for doc in self.scroll_documents():
            current_batch.append(doc)
            processed_docs += 1
            
            if len(current_batch) >= self.batch_size:
                merged_processes = self.process_batch(current_batch)
                self.write_to_index(merged_processes, target_index)
                current_batch = []
        
        # Process remaining documents
        if current_batch:
            merged_processes = self.process_batch(current_batch)
            self.write_to_index(merged_processes, target_index)
        
        logging.info(f"Total processed documents: {processed_docs}")

    def write_to_index(self, merged_processes, target_index):
        """将合并后的文档写入新索引"""
        actions = []
        for pid, flows in merged_processes.items():
            for flow in flows:
                # Remove _id field if present to avoid conflicts
                if '_id' in flow:
                    del flow['_id']
                action = {
                    '_index': target_index,
                    '_source': flow
                }
                actions.append(action)
        
        if actions:
            try:
                success, failed = helpers.bulk(
                    self.es, 
                    actions, 
                    raise_on_error=False,
                    stats_only=True
                )
                logging.info(f"Successfully indexed {success} documents")
                if failed:
                    logging.error(f"Failed to index {failed} documents")
            except Exception as e:
                logging.error(f"Error during bulk indexing: {str(e)}")
                # Retry with smaller batches if needed
                if len(actions) > 100:
                    mid = len(actions) // 2
                    temp1 = {}
                    temp2 = {}
                    for pid, flows in merged_processes.items():
                        mid_flows = len(flows) // 2
                        temp1[pid] = flows[:mid_flows]
                        temp2[pid] = flows[mid_flows:]
                    self.write_to_index(temp1, target_index)
                    self.write_to_index(temp2, target_index)

def main():
    es = Elasticsearch(
        hosts=["http://39.105.216.221:9200/"],
        basic_auth=(os.getenv("USERNAME"), os.getenv("PASSWORD")),
    )
    
    source_index = "processsdep_validation_index"
    target_index = "processsdep_validation_index1"
    
    merger = ProcessFlowMerger(es, source_index, batch_size=1000)
    merger.merge_and_write(target_index)

if __name__ == "__main__":
    main()