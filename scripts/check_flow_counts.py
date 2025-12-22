"""
Check flow counts for generated JSON outputs.

For each JSON file in `output/agent_results/individual_jsons/openai-mirror_gpt-oss-120b/`,
compare the number of `flow_combo` entries with the expected count from
`data/jsons/flows_to_analyze_combo.json`. Print any process IDs whose counts
do not match or are missing from the reference.
"""

import json
from pathlib import Path


OUTPUT_DIR = Path("output/agent_results/individual_jsons/openai-mirror_gpt-oss-120b")
REFERENCE_PATH = Path("data/jsons/flows_to_analyze_combo.json")


def load_reference() -> dict:
    with REFERENCE_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


def load_generated(path: Path) -> tuple[str, list]:
    data = json.load(path.open("r", encoding="utf-8"))
    if not isinstance(data, dict) or not data:
        return "", []
    # Each file is expected to have a single process_id root key
    pid, flows = next(iter(data.items()))
    return pid, flows if isinstance(flows, list) else []


def main() -> None:
    ref = load_reference()
    mismatches = []
    missing_flow_combo = []

    for file_path in sorted(OUTPUT_DIR.glob("*.json")):
        pid, flows = load_generated(file_path)
        if not pid:
            print(f"[WARN] Skip malformed file: {file_path}")
            continue

        expected = ref.get(pid)
        if expected is None:
            mismatches.append((pid, len(flows), "missing_in_reference"))
            continue

        # Count only entries that actually carry flow_combo
        actual_count = sum(1 for item in flows if isinstance(item, dict) and "flow_combo" in item)
        expected_count = len(expected)

        if actual_count == 0:
            missing_flow_combo.append(pid)

        if expected_count != actual_count:
            mismatches.append((pid, actual_count, expected_count))

    if not mismatches:
        print("All files match expected flow counts.")
    else:
        print("Count mismatches (pid, actual, expected):")
        for pid, actual, expected in mismatches:
            print(f"{pid}\t{actual}\t{expected}")

    if missing_flow_combo:
        print("\nFiles with zero flow_combo entries:")
        for pid in missing_flow_combo:
            print(pid)


if __name__ == "__main__":
    main()
