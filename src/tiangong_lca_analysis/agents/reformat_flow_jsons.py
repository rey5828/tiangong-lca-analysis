"""Rewrite GHG and flow lists using flow name/category combinations."""

import json
from collections import OrderedDict
from pathlib import Path
from typing import Dict, Iterable, List


BASE_DIR = Path(__file__).resolve().parents[3]
MAP_PATH = BASE_DIR / "data/jsons/map_elementary_flows.json"
GHG_PATH = BASE_DIR / "data/jsons/ghgs.json"
FLOWS_ANALYZE_PATH = BASE_DIR / "data/jsons/flows_list_analyze.json"
GHG_OUTPUT_PATH = BASE_DIR / "data/jsons/ghgs_combo.json"
FLOWS_OUTPUT_PATH = BASE_DIR / "data/jsons/flows_to_analyze_combo.json"


def load_flow_lookup() -> Dict[str, Dict[str, str]]:
    with MAP_PATH.open("r", encoding="utf-8") as f:
        mapping = json.load(f)
    lookup = {}
    for entry in mapping.get("flows", []):
        flow_id = entry.get("flow_id")
        if not flow_id:
            continue
        lookup[flow_id] = {
            "name": entry.get("flow_name", ""),
            "category": entry.get("flow_category", ""),
        }
    return lookup


def make_combo(name: str, category: str) -> str:
    name = name or ""
    category = category or ""
    return f"{name} | {category}".strip()


def unique_in_order(items: Iterable[str]) -> List[str]:
    seen = OrderedDict()
    for item in items:
        if item:
            seen.setdefault(item, None)
    return list(seen.keys())


def convert_ghgs(flow_lookup: Dict[str, Dict[str, str]]):
    with GHG_PATH.open("r", encoding="utf-8") as f:
        ghg_entries = json.load(f)

    combos = []
    missing_ids = []
    for entry in ghg_entries:
        flow_id = entry.get("id")
        flow_info = flow_lookup.get(flow_id)
        if not flow_info:
            missing_ids.append(flow_id)
            continue
        combos.append(make_combo(flow_info["name"], flow_info["category"]))

    ghg_output = unique_in_order(combos)

    with GHG_OUTPUT_PATH.open("w", encoding="utf-8") as f:
        json.dump(ghg_output, f, ensure_ascii=False, separators=(",", ":"))

    if missing_ids:
        print(f"[!] Missing {len(missing_ids)} GHG flow IDs in mapping (see ghg_missing_ids.json)")
        missing_path = BASE_DIR / "data/jsons/ghg_missing_ids.json"
        with missing_path.open("w", encoding="utf-8") as f:
            json.dump(unique_in_order(missing_ids), f, indent=2)


def convert_flows_list(flow_lookup: Dict[str, Dict[str, str]]):
    with FLOWS_ANALYZE_PATH.open("r", encoding="utf-8") as f:
        flows_map = json.load(f)

    converted = {}
    for process_id, flows in flows_map.items():
        combos = []
        for flow in flows:
            flow_id = flow.get("flow_id")
            flow_info = flow_lookup.get(flow_id)
            if not flow_info:
                continue
            combos.append(make_combo(flow_info["name"], flow_info["category"]))
        if combos:
            converted[process_id] = unique_in_order(combos)

    with FLOWS_OUTPUT_PATH.open("w", encoding="utf-8") as f:
        json.dump(converted, f, ensure_ascii=False, separators=(",", ":"))


def main():
    lookup = load_flow_lookup()
    convert_ghgs(lookup)
    convert_flows_list(lookup)
    print("[+] Wrote compressed flow combination JSON files.")


if __name__ == "__main__":
    main()
