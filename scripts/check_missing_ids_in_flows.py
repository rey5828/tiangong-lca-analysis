"""
Identify which IDs listed as missing are actually present in
`data/jsons/flows_to_analyze_combo.json`.
"""

import json
from pathlib import Path


MISSING_IDS_PATH = Path("output/agent_results/missing_process_ids.json")
FLOWS_PATH = Path("data/jsons/flows_to_analyze_combo.json")
RESULT_PATH = Path("output/agent_results/missing_ids_present_in_flows.json")


def load_ids(path: Path) -> list[str]:
    data = json.load(path.open("r", encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(f"Expected a list in {path}")
    return [str(item) for item in data if item]


def load_flow_ids(path: Path) -> set[str]:
    data = json.load(path.open("r", encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Expected a mapping in {path}")
    return set(data.keys())


def main() -> None:
    missing_ids = load_ids(MISSING_IDS_PATH)
    flow_ids = load_flow_ids(FLOWS_PATH)

    present_ids = [pid for pid in missing_ids if pid in flow_ids]

    RESULT_PATH.parent.mkdir(parents=True, exist_ok=True)
    RESULT_PATH.write_text(json.dumps(present_ids, indent=2), encoding="utf-8")

    print(f"Wrote {len(present_ids)} IDs present in flows to {RESULT_PATH}")


if __name__ == "__main__":
    main()
