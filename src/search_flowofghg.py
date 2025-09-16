import pandas as pd
from elasticsearch import Elasticsearch, helpers
import os
import json

es = Elasticsearch(
    hosts=["http://39.105.216.221:9200/"],
    basic_auth=(os.getenv("USERNAME"), os.getenv("PASSWORD")),
)

process_mapping = {
    "mappings": {
        "properties": {
            "process_id": {"type": "keyword"},
            "process_name": {"type": "keyword"},
            "process_type": {"type": "keyword"},
            "process_category": {"type": "keyword"},
            "process_location": {"type": "keyword"},
            "flow_id": {"type": "keyword"},
            "flow_amount": {"type": "double"},
            "flow_unit": {"type": "keyword"},
            "flow_name": {"type": "keyword"},
            "flow_type": {"type": "keyword"},
            "flow_category": {"type": "keyword"},
            "flow_direction": {"type": "keyword"}
        }
    }
}


if not es.indices.exists(index="processeswithghg_index"):
    es.indices.create(index="processeswithghg_index", body=process_mapping)

# Configure index names
process_index2 = "process_index"  
new_index = "processeswithghg_index"   

# Step 1: Read CSV file to get flow IDs
csv_file_path = r"/mnt/d/json/extracted_ghgflows.csv" 
df = pd.read_csv(csv_file_path)
csv_ids = df['id'].tolist()  # Get all the flow IDs from the CSV file

# Scroll API parameters
scroll_time = "5m"  # Scroll window time
batch_size = 10000   # Number of documents to retrieve per batch

# Step 2: Define search query using the ids from the CSV file
def search_and_export_processes(es, csv_ids, source_index, target_index, batch_size=10000):
    query = {
        "_source": True,  # Export all fields
        "size": batch_size,
        "query": {
            "terms": {
                "flow_id": csv_ids  # Match flow_id in the index with CSV IDs
            }
        }
    }

    # Initialize Scroll API
    response = es.search(index=source_index, body=query, scroll=scroll_time)
    scroll_id = response['_scroll_id']
    matching_documents = response['hits']['hits']

    # Keep track of total documents
    total_documents = len(matching_documents)
    success_count = 0  # Initialize success_count

   

    # Scroll through remaining documents
    while len(response['hits']['hits']) > 0:
        actions = [
            {
                "_op_type": "index",  # Index operation
                "_index": target_index,  # New index
                "_source": doc["_source"]
            }
            for doc in response['hits']['hits']
        ]


        # Use bulk operation to index documents into new index
        success, _  = helpers.bulk(es, actions)
        success_count += success

        # Fetch next batch of documents and update scroll_id
        response = es.scroll(scroll_id=scroll_id, scroll=scroll_time)
        scroll_id = response['_scroll_id']
        matching_documents.extend(response['hits']['hits'])
        total_documents += len(response['hits']['hits'])

    # Clear scroll
    es.clear_scroll(scroll_id=scroll_id)

    print(f"Total documents exported to {target_index}: {total_documents}")
    print(f"Total documents successfully exported: {success_count}")

# Step 3: Handle large number of IDs (Elasticsearch's terms query limit is 65536)
chunk_size = 1000  # Chunk size for processing flow IDs

for i in range(0, len(csv_ids), chunk_size):
    chunk = csv_ids[i:i + chunk_size]  # Process in chunks
    search_and_export_processes(es, chunk, process_index2, new_index, batch_size)

print("All matching documents have been exported.")
