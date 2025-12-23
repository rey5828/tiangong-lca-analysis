"""
Find process IDs present in `data/jsons/process_list.json` but missing in the
generated outputs under
`output/agent_results/individual_jsons/openai-mirror_gpt-oss-120b/`.
"""

import json
from pathlib import Path


PROCESS_LIST_PATH = Path("data/jsons/process_list.json")
OUTPUT_DIR = Path("output/agent_results/individual_jsons/openai-mirror_gpt-oss-120b")
RESULT_PATH = Path("output/agent_results/missing_process_ids.json")


def load_process_ids(path: Path) -> set[str]:
    data = json.load(path.open("r", encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(f"Expected a list of process IDs in {path}")
    return {str(item) for item in data if item}


def existing_ids(directory: Path) -> set[str]:
    return {p.stem for p in directory.glob("*.json") if p.is_file()}


def main() -> None:
    process_ids = load_process_ids(PROCESS_LIST_PATH)
    generated_ids = existing_ids(OUTPUT_DIR)

    missing_ids = sorted(process_ids - generated_ids)
    RESULT_PATH.parent.mkdir(parents=True, exist_ok=True)
    RESULT_PATH.write_text(json.dumps(missing_ids, indent=2), encoding="utf-8")

    print(f"Wrote {len(missing_ids)} missing IDs to {RESULT_PATH}")


if __name__ == "__main__":
    main()
