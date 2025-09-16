from elasticsearch import Elasticsearch, helpers
import json
import os

# Elasticsearch connection configuration
es = Elasticsearch(
    hosts=["http://39.105.216.221:9200/"],
    basic_auth=(os.getenv("USERNAME"), os.getenv("PASSWORD")),
)

SOURCE_INDEX = 'processwithghg_dedup2'
PROCESS_IDS_OUTPUT = 'output_elementary_process_ids.json'
FLOWS_TO_ANALYZE_OUTPUT = 'flows_to_analyze_list.json'

# Query to filter documents
query = {
    'query': {
        'bool': {
            'must': [
                {'term': {'flow_direction': 'output'}},
                {'term': {'flow_type': 'ELEMENTARY_FLOW'}},
                {'term': {'process_type': 'UNIT_PROCESS'}}
            ]
        }
    }
}

# Scroll through the filtered documents
scroll = helpers.scan(
    client=es,
    index=SOURCE_INDEX,
    query=query,
    _source=['process_id', 'flow_id', 'flow_name'],
    size=1000
)

# Collect unique process IDs and organize flows by process
unique_process_ids = set()
flows_by_process = {}

for doc in scroll:
    src = doc['_source']
    process_id = src['process_id']
    flow_id = src['flow_id']
    flow_name = src['flow_name']
    
    # Collect unique process IDs
    unique_process_ids.add(process_id)
    
    # Build the flows structure
    if process_id not in flows_by_process:
        flows_by_process[process_id] = []
        
    # Check if this flow is already added (prevent duplicates)
    flow_exists = False
    for flow in flows_by_process[process_id]:
        if flow['flow_id'] == flow_id:
            flow_exists = True
            break
            
    if not flow_exists:
        flows_by_process[process_id].append({
            'flow_name': flow_name,
            'flow_id': flow_id
        })

# Convert set to list for JSON serialization
process_ids_list = list(unique_process_ids)

# Write unique process IDs to JSON
with open(PROCESS_IDS_OUTPUT, 'w') as f:
    json.dump(process_ids_list, f, indent=2)
print(f"Wrote {len(process_ids_list)} unique process IDs to {PROCESS_IDS_OUTPUT}")

# Write flows to analyze list to JSON
with open(FLOWS_TO_ANALYZE_OUTPUT, 'w') as f:
    json.dump(flows_by_process, f, indent=2)
print(f"Wrote flows analysis data for {len(flows_by_process)} processes to {FLOWS_TO_ANALYZE_OUTPUT}")
