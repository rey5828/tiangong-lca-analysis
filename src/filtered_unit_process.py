from elasticsearch import Elasticsearch, helpers
import json
import os

# Elasticsearch 连接配置
es = Elasticsearch(
    hosts=["http://39.105.216.221:9200/"],
    basic_auth=(os.getenv("USERNAME"), os.getenv("PASSWORD")),
)

SOURCE_INDEX = 'processwithghg_dedup2'
TARGET_INDEX = 'process_unit'
OUTPUT_JSON = 'matching_process_pairs.json'

# Mapping definition for target index (same as provided)
mapping = {
    'mappings': {
        'properties': {
            'category': {'type': 'keyword'},
            'eco_quality': {'type': 'double'},
            'flow_amount': {'type': 'double'},
            'flow_category': {'type': 'keyword'},
            'flow_direction': {'type': 'keyword'},
            'flow_id': {'type': 'keyword'},
            'flow_name': {'type': 'keyword'},
            'flow_type': {'type': 'keyword'},
            'flow_unit': {'type': 'keyword'},
            'gwp': {'type': 'double'},
            'human_health': {'type': 'double'},
            'process_category': {'type': 'keyword'},
            'process_id': {'type': 'keyword'},
            'process_location': {'type': 'keyword'},
            'process_name': {'type': 'keyword'},
            'process_type': {'type': 'keyword'},
            'ratio': {'type': 'double'},
            'resources': {'type': 'double'}
        }
    }
}


# 1. Create target index
if es.indices.exists(index=TARGET_INDEX):
    es.indices.delete(index=TARGET_INDEX)
es.indices.create(index=TARGET_INDEX, body=mapping)

# 2. Scroll source index and filter docs
query = {
    'query': {
        'bool': {
            'must': [
                {'term': {'flow_type': 'ELEMENTARY_FLOW'}},
                {'term': {'process_type': 'UNIT_PROCESS'}}
            ]
        }
    }
}

scroll = helpers.scan(
    client=es,
    index=SOURCE_INDEX,
    query=query,
    _source=True,
    size=1000
)

actions = ({
    '_index': TARGET_INDEX,
    '_id': doc['_id'],
    '_source': doc['_source']
} for doc in scroll)
helpers.bulk(es, actions)

# 3. Aggregate by process_id: collect input and output flow_ids
process_flows = {}

scroll = helpers.scan(
    client=es,
    index=TARGET_INDEX,
    query={'query': {'match_all': {}}},
    _source=['process_id','process_name','process_category','gwp','flow_direction','flow_id'],
    size=1000
)
for doc in scroll:
    src = doc['_source']
    pid = src['process_id']
    d = process_flows.setdefault(pid, {
        'process_name': src['process_name'],
        'process_category': src['process_category'],
        'gwp': src['gwp'],
        'input': set(),
        'output': set()
    })
    if src['flow_direction'] == 'input':
        d['input'].add(src['flow_id'])
    elif src['flow_direction'] == 'output':
        d['output'].add(src['flow_id'])

# 4. Find matching groups: same sets of input and output lengths
signature_map = {}
for pid, info in process_flows.items():
    sig = (len(info['input']), len(info['output']))
    signature_map.setdefault(sig, []).append(pid)

# 5. Prepare JSON entries
output = []
for sig, pids in signature_map.items():
    if len(pids) > 1:
        x, y = sig
        entry = {
            'input_count': x,
            'output_count': y,
            'process_ids': pids,
            'process_names': [process_flows[p]['process_name'] for p in pids],
            'process_categories': [process_flows[p]['process_category'] for p in pids],
            'gwps': [process_flows[p]['gwp'] for p in pids]
        }
        output.append(entry)

# 6. Write to JSON file
with open(OUTPUT_JSON, 'w') as f:
    json.dump(output, f, indent=2)

print(f"Wrote {len(output)} matching groups to {OUTPUT_JSON}")

