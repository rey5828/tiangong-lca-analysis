#!/usr/bin/env python3
"""Identify processes with Shared Driver dominance across compartments."""

import json
from pathlib import Path

BASE_DIR = Path("output/agent_results/individual_jsons/openai-mirror_gpt-oss-120b")
OUTPUT_PATH = Path(
    "output/agent_results/openai-mirror_gpt-oss-120b_flagged_process_ids.json"
)
SHARED_DRIVER_LABEL = "Shared Driver"
WATER_SOIL = {"water", "soil"}


def extract_compartment(flow_combo: str) -> str | None:
    """Return the emission compartment for the pollutant flow, if present."""
    flow_lower = flow_combo.lower()
    if "emission to air" in flow_lower:
        return "air"
    if "emission to water" in flow_lower:
        return "water"
    if "emission to soil" in flow_lower:
        return "soil"
    return None


def process_file(path: Path) -> bool:
    """Return True if the process meets either Shared Driver condition."""
    with path.open() as f:
        payload = json.load(f)

    relationships_by_flow = next(iter(payload.values()), [])
    total_relationships = 0
    shared_driver_total = 0
    water_soil_total = 0
    water_soil_shared = 0

    for flow_entry in relationships_by_flow:
        compartment = extract_compartment(flow_entry.get("flow_combo", ""))
        analyses = flow_entry.get("individual_ghg_analyses") or []
        for analysis in analyses:
            total_relationships += 1
            if compartment in WATER_SOIL:
                water_soil_total += 1
            if analysis.get("mechanism_archetype") == SHARED_DRIVER_LABEL:
                shared_driver_total += 1
                if compartment in WATER_SOIL:
                    water_soil_shared += 1

    shared_driver_ratio = (
        shared_driver_total / total_relationships if total_relationships else 0
    )
    water_soil_shared_driver_ratio = (
        water_soil_shared / water_soil_total if water_soil_total else 0
    )

    condition_shared_driver = shared_driver_ratio > 0.5
    condition_water_soil = water_soil_shared_driver_ratio > 0.20
    return condition_shared_driver or condition_water_soil


def main() -> None:
    flagged: list[str] = []

    for path in sorted(BASE_DIR.glob("*.json")):
        if process_file(path):
            flagged.append(path.stem)

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_PATH.open("w") as f:
        json.dump(flagged, f, indent=2)

    print(json.dumps(flagged, indent=2))


if __name__ == "__main__":
    main()
