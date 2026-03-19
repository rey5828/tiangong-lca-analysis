#!/usr/bin/env python3
"""Stratified random sampling for carbon-pollution pair records.

This script scans all process JSON files under
output/agent_results/individual_jsons/openai-mirror_gpt-oss-120b, assigns each
record to one of 9 strata defined by:

1. qualitative_relationship: Positive / Negative / Neutral
2. confidence: High / Medium / Low

Records with missing or invalid confidence are treated as Low.

Sampling is performed without replacement and is reproducible via --seed.
Each stratum is written to a separate JSON file in the output directory.
Exported objects preserve the original analysis object, add process_id and
flow_combo, and remove the confidence field to avoid review bias.
"""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT_DIR = ROOT / "output" / "agent_results" / "individual_jsons" / "openai-mirror_gpt-oss-120b"
DEFAULT_OUTPUT_DIR = ROOT / "output" / "agent_results" / "stratified_samples" / "openai-mirror_gpt-oss-120b"

VALID_RELATIONSHIPS = {"Positive", "Negative", "Neutral"}
VALID_CONFIDENCE = {"High", "Medium", "Low"}

SAMPLE_SIZES = {
    ("Positive", "High"): 381,
    ("Positive", "Medium"): 375,
    ("Positive", "Low"): 171,
    ("Negative", "High"): 310,
    ("Negative", "Medium"): 330,
    ("Negative", "Low"): 111,
    ("Neutral", "High"): 383,
    ("Neutral", "Medium"): 377,
    ("Neutral", "Low"): 264,
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=DEFAULT_INPUT_DIR,
        help="Directory containing process JSON files.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Directory for per-stratum sampled JSON files.",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed for reproducible sampling.",
    )
    return parser.parse_args()


def iter_process_files(input_dir: Path) -> list[Path]:
    return sorted(input_dir.glob("*.json"))


def normalize_confidence(value: Any) -> str:
    if isinstance(value, str) and value in VALID_CONFIDENCE:
        return value
    return "Low"


def collect_strata(input_dir: Path) -> dict[tuple[str, str], list[dict[str, Any]]]:
    strata = {key: [] for key in SAMPLE_SIZES}

    for json_path in iter_process_files(input_dir):
        try:
            payload = json.loads(json_path.read_text(encoding="utf-8"))
        except Exception:
            continue

        if not isinstance(payload, dict) or len(payload) != 1:
            continue

        process_id = next(iter(payload))
        flow_entries = payload[process_id]
        if not isinstance(flow_entries, list):
            continue

        for flow_entry in flow_entries:
            if not isinstance(flow_entry, dict):
                continue

            flow_combo = flow_entry.get("flow_combo")
            ghg_entries = flow_entry.get("individual_ghg_analyses", [])
            if not isinstance(ghg_entries, list):
                continue

            for ghg_entry in ghg_entries:
                if not isinstance(ghg_entry, dict):
                    continue

                relationship = ghg_entry.get("qualitative_relationship")
                if relationship not in VALID_RELATIONSHIPS:
                    continue

                confidence = normalize_confidence(ghg_entry.get("confidence"))
                stratum_key = (relationship, confidence)
                if stratum_key not in strata:
                    continue

                sampled_object = dict(ghg_entry)
                sampled_object.pop("confidence", None)
                sampled_object["flow_combo"] = flow_combo
                sampled_object["process_id"] = process_id

                strata[stratum_key].append(sampled_object)

    return strata


def sample_strata(
    strata: dict[tuple[str, str], list[dict[str, Any]]],
    seed: int,
) -> dict[tuple[str, str], list[dict[str, Any]]]:
    rng = random.Random(seed)
    sampled = {}

    for stratum_key, sample_size in SAMPLE_SIZES.items():
        population = strata[stratum_key]
        if len(population) < sample_size:
            relationship, confidence = stratum_key
            raise ValueError(
                f"Stratum {relationship}|{confidence} has only {len(population)} records, "
                f"but {sample_size} samples were requested."
            )
        sampled[stratum_key] = rng.sample(population, sample_size)

    return sampled


def write_outputs(output_dir: Path, sampled: dict[tuple[str, str], list[dict[str, Any]]]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)

    for (relationship, confidence), records in sampled.items():
        output_path = output_dir / f"{relationship}_{confidence}.json"
        output_path.write_text(
            json.dumps(records, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )


def main() -> None:
    args = parse_args()
    strata = collect_strata(args.input_dir)
    sampled = sample_strata(strata, args.seed)
    write_outputs(args.output_dir, sampled)

    print(f"Input directory: {args.input_dir}")
    print(f"Output directory: {args.output_dir}")
    print(f"Random seed: {args.seed}")
    for relationship, confidence in SAMPLE_SIZES:
        available = len(strata[(relationship, confidence)])
        requested = SAMPLE_SIZES[(relationship, confidence)]
        print(
            f"{relationship}|{confidence}: sampled {requested} from {available} available records"
        )


if __name__ == "__main__":
    main()
