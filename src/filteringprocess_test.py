from elasticsearch import Elasticsearch, helpers
from collections import defaultdict
import numpy as np
from typing import List, Dict, Set, Generator, Tuple
import re
import logging
import time
import os

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

class ProcessDeduplicator:
    def __init__(self, es_client: Elasticsearch, index_name: str, batch_size: int = 5000):
        self.es = es_client
        self.index = index_name
        self.batch_size = batch_size

    def scroll_documents(self) -> Generator[dict, None, None]:
        """使用scroll API分批获取所有文档"""
        query = {
            "query": {
                "match_all": {}
            },
            "sort": ["_doc"]  # 使用_doc排序以提高性能
        }
        
        # 初始化scroll
        response = self.es.search(
            index=self.index,
            body=query,
            scroll='5m',  # scroll保持时间
            size=self.batch_size
        )
        
        # 获取第一批数据
        scroll_id = response['_scroll_id']
        hits = response['hits']['hits']
        
        while hits:
            for hit in hits:
                yield hit
            
            # 获取下一批数据
            response = self.es.scroll(
                scroll_id=scroll_id,
                scroll='5m'
            )
            scroll_id = response['_scroll_id']
            hits = response['hits']['hits']

    def process_batch(self, batch_docs: List[dict]) -> Dict[str, List[dict]]:
        """处理一批文档，按process_id分组"""
        process_flows = defaultdict(list)
        for hit in batch_docs:
            flow = hit['_source']
            flow['_id'] = hit['_id']
            process_flows[flow['process_id']].append(flow)
        return process_flows

    def get_process_fingerprint(self, flows: List[dict]) -> str:
        """生成process的指纹"""
        sorted_flows = sorted(flows, key=lambda x: (x['flow_id'], x['flow_name']))
        fingerprint_parts = []
        for flow in sorted_flows:
            flow_copy = flow.copy()
            flow_copy.pop('process_id', None)
            flow_copy.pop('process_location', None)
            flow_copy.pop('flow_amount', None)
            flow_copy.pop('_id', None)
            fingerprint_parts.append(str(flow_copy))
        return '|'.join(fingerprint_parts)

    def detect_scaling_processes(self, processes: Dict[str, List[dict]]) -> Set[str]:
        """检测比例缩放的processes"""
        name_groups = defaultdict(list)
        for process_id, flows in processes.items():
            if not flows:
                continue
            process_name = flows[0]['process_name']
            first_part = process_name.split('|')[0].strip()
            name_groups[first_part].append((process_id, flows))
        
        to_remove = set()
        for group in name_groups.values():
            if len(group) <= 1:
                continue
            
            for i in range(len(group)):
                for j in range(i + 1, len(group)):
                    process_id1, flows1 = group[i]
                    process_id2, flows2 = group[j]
                    
                    flows1_dict = {(f['flow_id'], f['flow_name']): f['flow_amount'] for f in flows1}
                    flows2_dict = {(f['flow_id'], f['flow_name']): f['flow_amount'] for f in flows2}
                    
                    if set(flows1_dict.keys()) == set(flows2_dict.keys()):
                        ratios = []
                        for key in flows1_dict:
                            if flows1_dict[key] != 0 and flows2_dict[key] != 0:
                                ratios.append(flows2_dict[key] / flows1_dict[key])
                        
                        if ratios and np.std(ratios) < 1e-4:
                            to_remove.add(process_id2)
        
        return to_remove

    def bulk_write(self, docs: List[dict], target_index: str):
        """批量写入文档到ES"""
        bulk_data = []
        for doc in docs:
            doc_copy = doc.copy()
            doc_copy.pop('_id', None)
            bulk_data.append({
                "_index": target_index,
                "_source": doc_copy
            })

        if bulk_data:
            try:
                helpers.bulk(self.es, bulk_data)
                logging.info(f"Successfully wrote {len(bulk_data)} documents to {target_index}")
            except Exception as e:
                logging.error(f"Error writing to Elasticsearch: {str(e)}")

    def deduplicate(self, new_index_name: str = None) -> None:
        """执行批量去重流程"""
        if new_index_name is None:
            new_index_name = f"{self.index}_dedup"

        # 确保新索引存在
        if not self.es.indices.exists(index=new_index_name):
            original_mapping = self.es.indices.get_mapping(index=self.index)
            self.es.indices.create(
                index=new_index_name,
                body={"mappings": original_mapping[self.index]['mappings']}
            )

        start_time = time.time()
        total_docs = 0
        processed_docs = 0
        unique_docs = 0

        # 获取总文档数
        total_docs = self.es.count(index=self.index)['count']
        logging.info(f"Total documents to process: {total_docs}")

        # 用于存储所有已见过的process指纹
        seen_fingerprints = {}
        
        # 批量处理文档
        current_batch = []
        for doc in self.scroll_documents():
            current_batch.append(doc)
            processed_docs += 1

            # 当达到批处理大小时处理当前批次
            if len(current_batch) >= self.batch_size:
                # 处理当前批次
                batch_processes = self.process_batch(current_batch)
                
                # 检查重复（基于location）
                unique_in_batch = {}
                for pid, flows in batch_processes.items():
                    fingerprint = self.get_process_fingerprint(flows)
                    if fingerprint not in seen_fingerprints:
                        seen_fingerprints[fingerprint] = pid
                        unique_in_batch[pid] = flows
                
                # 检查比例缩放重复
                scaling_duplicates = self.detect_scaling_processes(unique_in_batch)
                
                # 写入不重复的文档
                unique_flows = []
                for pid, flows in unique_in_batch.items():
                    if pid not in scaling_duplicates:
                        unique_flows.extend(flows)
                
                if unique_flows:
                    self.bulk_write(unique_flows, new_index_name)
                    unique_docs += len(unique_flows)
                
                # 清空当前批次
                current_batch = []
                
                # 输出进度
                progress = (processed_docs / total_docs) * 100
                elapsed_time = time.time() - start_time
                logging.info(f"Progress: {progress:.2f}% ({processed_docs}/{total_docs}) - "
                           f"Unique docs: {unique_docs} - "
                           f"Elapsed time: {elapsed_time:.2f}s")

        # 处理最后一个不完整的批次
        if current_batch:
            batch_processes = self.process_batch(current_batch)
            unique_in_batch = {}
            for pid, flows in batch_processes.items():
                fingerprint = self.get_process_fingerprint(flows)
                if fingerprint not in seen_fingerprints:
                    seen_fingerprints[fingerprint] = pid
                    unique_in_batch[pid] = flows
            
            scaling_duplicates = self.detect_scaling_processes(unique_in_batch)
            unique_flows = []
            for pid, flows in unique_in_batch.items():
                if pid not in scaling_duplicates:
                    unique_flows.extend(flows)
            
            if unique_flows:
                self.bulk_write(unique_flows, new_index_name)
                unique_docs += len(unique_flows)

        total_time = time.time() - start_time
        logging.info(f"Deduplication completed in {total_time:.2f}s")
        logging.info(f"Total processed documents: {processed_docs}")
        logging.info(f"Total unique documents: {unique_docs}")
        logging.info(f"Duplicate documents removed: {processed_docs - unique_docs}")

def main():
    # 配置Elasticsearch连接
    es = Elasticsearch(
        hosts=["http://39.105.216.221:9200/"],
        basic_auth=(os.getenv("USERNAME"), os.getenv("PASSWORD")),
    )
    
    index_name = "filteredprocesses_index"
    
    # 创建去重器实例，设置适当的批处理大小
    deduplicator = ProcessDeduplicator(es, index_name, batch_size=5000)
    
    # 执行去重
    deduplicator.deduplicate(new_index_name="processwithghg_dedup1")

if __name__ == "__main__":
    main()