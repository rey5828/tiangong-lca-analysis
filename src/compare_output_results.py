import argparse
import json
from collections import OrderedDict
from pathlib import Path
from typing import Dict, Iterable, List, Tuple


DEFAULT_FILE_A = Path("data/for_check/vllm_536ef78c.json")
DEFAULT_FILE_B = Path("output/agent_results/individual_jsons/gpt-5-mini-2025-08-07/536ef78c-af9e-3efd-a995-1d43e5d3d3b8.json")
DEFAULT_OUTPUT = Path(
    "output/agent_results/comparisons/vllm_vs_mini_536ef78c.json"
)


Record = Dict[str, str]
Key = Tuple[str, str]


def load_flow_map(path: Path) -> "OrderedDict[Key, Record]":
    """Flatten the JSON structure into a map keyed by (flow_combo, ghg_combo)."""
    data = json.loads(path.read_text())

    if isinstance(data, list):
        flow_list = data
    elif isinstance(data, dict):
        if isinstance(data.get("flow_analyses"), list):
            flow_list = data["flow_analyses"]
        else:
            try:
                first_value = next(iter(data.values()))
            except StopIteration:
                flow_list = []
            else:
                if not isinstance(first_value, list):
                    raise ValueError(f"Unsupported dict structure in {path}")
                flow_list = first_value
    else:
        raise ValueError(f"Unsupported JSON root type in {path}: {type(data)}")

    mapping: "OrderedDict[Key, Record]" = OrderedDict()
    for flow in flow_list:
        flow_combo = flow["flow_combo"]
        for ghg in flow["individual_ghg_analyses"]:
            key = (flow_combo, ghg["ghg_combo"])
            mapping[key] = {
                "flow_combo": flow_combo,
                "ghg_combo": ghg["ghg_combo"],
                "qualitative_relationship": ghg["qualitative_relationship"],
                "mechanism_archetype": ghg.get("mechanism_archetype"),
                "qualitative_reasoning": ghg.get("qualitative_reasoning"),
                "confidence": ghg.get("confidence"),
            }
    return mapping


def build_diff(
    map_a: "OrderedDict[Key, Record]",
    map_b: "OrderedDict[Key, Record]",
    label_a: Path,
    label_b: Path,
) -> Dict[str, List[Dict[str, object]]]:
    shared_keys: Iterable[Key] = sorted(set(map_a) & set(map_b))
    qual_rel_diffs: List[Dict[str, object]] = []
    mech_diffs: List[Dict[str, object]] = []

    for key in shared_keys:
        obj_a = map_a[key]
        obj_b = map_b[key]
        rel_a = obj_a["qualitative_relationship"]
        rel_b = obj_b["qualitative_relationship"]

        if rel_a != rel_b:
            qual_rel_diffs.append(
                {
                    "flow_combo": key[0],
                    "ghg_combo": key[1],
                    str(label_a): obj_a,
                    str(label_b): obj_b,
                }
            )
        elif rel_a == "Positive" and rel_b == "Positive":
            if obj_a.get("mechanism_archetype") != obj_b.get("mechanism_archetype"):
                mech_diffs.append(
                    {
                        "flow_combo": key[0],
                        "ghg_combo": key[1],
                        str(label_a): obj_a,
                        str(label_b): obj_b,
                    }
                )

    return {
        "qualitative_relationship_mismatches": qual_rel_diffs,
        "mechanism_archetype_mismatches_when_positive": mech_diffs,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compare qualitative relationship/mechanism entries between two JSON files."
    )
    parser.add_argument(
        "--file-a",
        default=str(DEFAULT_FILE_A),
        help=f"First JSON file path (default: {DEFAULT_FILE_A})",
    )
    parser.add_argument(
        "--file-b",
        default=str(DEFAULT_FILE_B),
        help=f"Second JSON file path (default: {DEFAULT_FILE_B})",
    )
    parser.add_argument(
        "-o",
        "--output",
        default=str(DEFAULT_OUTPUT),
        help=(
            "Output JSON path. Set to '-' to print diff to stdout instead of writing a file "
            f"(default: {DEFAULT_OUTPUT})"
        ),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    path_a = Path(args.file_a).expanduser().resolve()
    path_b = Path(args.file_b).expanduser().resolve()

    map_a = load_flow_map(path_a)
    map_b = load_flow_map(path_b)
    diff = build_diff(map_a, map_b, path_a, path_b)

    diff_text = json.dumps(diff, indent=2)
    summary = (
        f"{len(diff['qualitative_relationship_mismatches'])} qualitative mismatches, "
        f"{len(diff['mechanism_archetype_mismatches_when_positive'])} "
        "positive mechanism mismatches"
    )

    if args.output == "-":
        print(diff_text)
        print(summary)
    else:
        out_path = Path(args.output).expanduser()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(diff_text)
        print(f"Wrote {out_path} ({summary}).")


if __name__ == "__main__":
    main()
