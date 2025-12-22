from elasticsearch import Elasticsearch
from collections import defaultdict
import os

def compare_process_counts(es_client, process_index, filtered_index):
    """
    Compare document counts for each process_id between two indices
    
    Args:
        es_client: Elasticsearch client instance
        process_index: Name of the original process index
        filtered_index: Name of the filtered process index
    
    Returns:
        dict: Mismatched process_ids with their counts in both indices
    """
    
    # Get process_id counts from filtered index
    filtered_agg = {
        "size": 0,
        "aggs": {
            "process_counts": {
                "terms": {
                    "field": "process_id",
                    "size": 5000  # Adjust size as needed
                }
            }
        }
    }
    
    filtered_response = es_client.search(
        index=filtered_index,
        body=filtered_agg
    )
    
    # Store filtered index counts
    filtered_counts = {}
    for bucket in filtered_response['aggregations']['process_counts']['buckets']:
        filtered_counts[bucket['key']] = bucket['doc_count']
    
    # Compare with original index
    mismatches = {}
    
    for process_id, filtered_count in filtered_counts.items():
        # Query original index for this process_id
        original_query = {
            "query": {
                "term": {
                    "process_id": process_id
                }
            }
        }
        
        original_count = es_client.count(
            index=process_index,
            body=original_query
        )['count']
        
        # Check if counts match
        if original_count != filtered_count:
            mismatches[process_id] = {
                'original_index_count': original_count,
                'filtered_index_count': filtered_count
            }
    
    return mismatches

def main():
    
    es = Elasticsearch(
    hosts=["http://39.105.216.221:9200/"],
    basic_auth=(os.getenv("USERNAME"), os.getenv("PASSWORD")),
)

    
    # 定义索引名称
    process_index = 'processwithghg_dedup2'
    filtered_index = 'processwithghg_dedup3'
    
    try:
        # 执行比较
        mismatches = compare_process_counts(es, process_index, filtered_index)
        
        # 输出结果
        if not mismatches:
            print("所有 process_id 的文档数量都匹配！")
        else:
            print("\n不匹配的 process_id 及其文档数量:")
            print("-" * 60)
            print(f"{'Process ID':<20} {'Original Count':<15} {'Filtered Count':<15}")
            print("-" * 60)
            
            for process_id, counts in mismatches.items():
                print(f"{process_id:<20} {counts['original_index_count']:<15} {counts['filtered_index_count']:<15}")
                
            print(f"\n总共发现 {len(mismatches)} 个不匹配的 process_id")
            
    except Exception as e:
        print(f"发生错误: {str(e)}")
    
if __name__ == "__main__":
    main()