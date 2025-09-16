from elasticsearch import Elasticsearch, helpers
import os
from collections import defaultdict
import numpy as np
from typing import Dict, List, Set

# Elasticsearch connection
es = Elasticsearch(
    hosts=["http://39.105.216.221:9200/"],
    basic_auth=(os.getenv("USERNAME"), os.getenv("PASSWORD")),
)

INDEX_NAME = "processwithghg_dedup2"
BATCH_SIZE = 2000
SCROLL_TIME = "2m"
RATIO_THRESHOLD = 1e-6

def get_process_documents():
    query = {
        "_source": ["process_name", "process_id", "flow_id", "ratio"],
        "query": {"match_all": {}}
    }
    
    response = es.search(
        index=INDEX_NAME,
        body=query,
        scroll=SCROLL_TIME,
        size=BATCH_SIZE
    )
    
    scroll_id = response['_scroll_id']
    hits = response['hits']['hits']
    
    while hits:
        for hit in hits:
            yield hit['_source']
            
        response = es.scroll(scroll_id=scroll_id, scroll=SCROLL_TIME)
        hits = response['hits']['hits']

def are_ratios_equal(ratios1: List[float], ratios2: List[float]) -> bool:
    if len(ratios1) != len(ratios2):
        return False
    return np.std(np.array(ratios1) - np.array(ratios2)) < RATIO_THRESHOLD

def process_duplicates():
    # Group by process name first part
    name_groups = defaultdict(lambda: defaultdict(list))
    
    print("Reading documents and grouping...")
    for doc in get_process_documents():
        process_name = doc.get('process_name', '')
        first_part = process_name.split('|')[0].strip()
        process_id = doc.get('process_id')
        flow_id = doc.get('flow_id')
        ratio = doc.get('ratio', 0)
        
        if process_id and first_part and flow_id is not None:
            name_groups[first_part][process_id].append({
                'flow_id': flow_id,
                'ratio': ratio
            })
    
    duplicates = set()
    print("Detecting duplicates...")
    
    # Compare processes within name groups only
    for name, processes in name_groups.items():
        process_ids = list(processes.keys())
        
        if len(process_ids) < 2:
            continue
            
        for i, pid1 in enumerate(process_ids):
            if pid1 in duplicates:
                continue
                
            flows1 = defaultdict(list)
            for flow in processes[pid1]:
                flows1[flow['flow_id']].append(flow['ratio'])
            
            for pid2 in process_ids[i+1:]:
                if pid2 in duplicates:
                    continue
                    
                flows2 = defaultdict(list)
                for flow in processes[pid2]:
                    flows2[flow['flow_id']].append(flow['ratio'])
                
                # Check if they have the same flow_ids
                if set(flows1.keys()) == set(flows2.keys()):
                    # Check ratios for each flow_id
                    is_duplicate = True
                    for flow_id in flows1:
                        if not are_ratios_equal(flows1[flow_id], flows2[flow_id]):
                            is_duplicate = False
                            break
                    
                    if is_duplicate:
                        duplicates.add(pid2)
    
    print(f"Found {len(duplicates)} duplicate processes")
    return duplicates

def delete_duplicates(duplicates: Set[str]):
    if not duplicates:
        return
        
    print("Deleting duplicate processes...")
    query = {
        "query": {
            "terms": {
                "process_id": list(duplicates)
            }
        }
    }
    
    es.delete_by_query(
        index=INDEX_NAME,
        body=query,
        refresh=True
    )
    print("Deletion completed")

if __name__ == "__main__":
    try:
        duplicates = process_duplicates()
        delete_duplicates(duplicates)
    except Exception as e:
        print(f"Error: {str(e)}")