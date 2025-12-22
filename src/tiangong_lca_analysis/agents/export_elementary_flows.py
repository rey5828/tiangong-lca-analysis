"""Export output elementary flows and verify name/category uniqueness."""

import json
import os
from collections import defaultdict
from pathlib import Path

from elasticsearch import Elasticsearch, helpers


# Reuse the Elasticsearch configuration from extract_data.py
es = Elasticsearch(
    hosts=["http://39.105.216.221:9200/"],
    basic_auth=(os.getenv("USERNAME"), os.getenv("PASSWORD")),
)

SOURCE_INDEX = "processwithghg_dedup2"
OUTPUT_PATH = Path("data/jsons/map_elementary_flows.json")


def normalize_category(category):
    """Convert flow_category into a JSON-serializable, comparable form."""
    if category is None:
        return None
    if isinstance(category, (list, tuple)):
        return list(category)
    return category


def combo_key(flow_name, flow_category):
    """Generate a hashable key for a flow_name/flow_category pair."""
    category = flow_category if not isinstance(flow_category, list) else tuple(flow_category)
    return flow_name, category


def serialize_category(category):
    if isinstance(category, tuple):
        return list(category)
    return category


def fetch_flows():
    query = {
        "query": {
            "bool": {
                "must": [
                    {"term": {"flow_direction": "output"}},
                    {"term": {"flow_type": "ELEMENTARY_FLOW"}},
                ]
            }
        }
    }

    scroll = helpers.scan(
        client=es,
        index=SOURCE_INDEX,
        query=query,
        _source=["flow_id", "flow_name", "flow_category"],
        size=1000,
    )

    flows_by_id = {}
    combo_to_ids = defaultdict(set)
    flow_id_to_combos = defaultdict(set)

    total_docs = 0
    for doc in scroll:
        total_docs += 1
        src = doc.get("_source", {})
        flow_id = src.get("flow_id")
        flow_name = src.get("flow_name")
        flow_category = normalize_category(src.get("flow_category"))

        if not flow_id or flow_name is None:
            continue

        flows_by_id.setdefault(
            flow_id,
            {
                "flow_id": flow_id,
                "flow_name": flow_name,
                "flow_category": flow_category,
            },
        )

        key = combo_key(flow_name, flow_category)
        combo_to_ids[key].add(flow_id)
        flow_id_to_combos[flow_id].add(key)

    return flows_by_id, combo_to_ids, flow_id_to_combos, total_docs


def build_uniqueness_report(combo_to_ids, flow_id_to_combos):
    combo_conflicts = []
    for (name, category), ids in combo_to_ids.items():
        if len(ids) > 1:
            combo_conflicts.append(
                {
                    "flow_name": name,
                    "flow_category": serialize_category(category),
                    "flow_ids": sorted(ids),
                }
            )

    flow_id_conflicts = []
    for flow_id, combos in flow_id_to_combos.items():
        if len(combos) > 1:
            combo_descriptions = []
            for combo in combos:
                combo_descriptions.append(
                    {
                        "flow_name": combo[0],
                        "flow_category": serialize_category(combo[1]),
                    }
                )
            flow_id_conflicts.append(
                {
                    "flow_id": flow_id,
                    "flow_name_category_pairs": combo_descriptions,
                }
            )

    return {
        "combination_unique_to_flow_id": len(combo_conflicts) == 0,
        "flow_id_unique_to_combination": len(flow_id_conflicts) == 0,
        "combination_conflicts": combo_conflicts,
        "flow_id_conflicts": flow_id_conflicts,
    }


def main():
    flows_by_id, combo_to_ids, flow_id_to_combos, total_docs = fetch_flows()
    uniqueness_report = build_uniqueness_report(combo_to_ids, flow_id_to_combos)

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    sorted_flows = sorted(flows_by_id.values(), key=lambda item: item["flow_id"])

    result = {
        "total_documents_scanned": total_docs,
        "unique_flows": len(sorted_flows),
        "flows": sorted_flows,
        "uniqueness_report": uniqueness_report,
    }

    with OUTPUT_PATH.open("w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)

    if uniqueness_report["combination_unique_to_flow_id"]:
        print("Flow name/category combinations map uniquely to flow_id.")
    else:
        print(
            "Found flow name/category combinations that map to multiple flow_ids."
        )
    print(f"Wrote {len(sorted_flows)} flows to {OUTPUT_PATH}.")


if __name__ == "__main__":
    main()
