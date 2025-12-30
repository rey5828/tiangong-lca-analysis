import json
from pathlib import Path

VALID_RELATIONSHIPS = {"Positive", "Negative", "Neutral"}
VALID_ARCHETYPES = {"Shared Driver", "Trade-off", "Trade‑off", "Efficiency Synergy", "Process Synergy", "Decoupled"}
VALID_CONFIDENCE = {"High", "Medium", "Low"}


def main() -> None:
    base_dir = Path("output/agent_results/individual_jsons/openai-mirror_gpt-oss-120b")
    output_path = Path("output/agent_results/invalid_field_records.json")

    invalid_processes = {}

    for json_path in sorted(base_dir.glob("*.json")):
        try:
            payload = json.loads(json_path.read_text(encoding="utf-8"))
        except Exception as exc:
            invalid_processes[json_path.stem] = [f"file_load_error: {exc}"]
            continue

        for process_id, analyses in payload.items():
            errors = []
            if not isinstance(analyses, list):
                errors.append("invalid_root: flow_analyses not list")
                invalid_processes[process_id] = errors
                continue

            for flow in analyses:
                if not isinstance(flow, dict):
                    errors.append("invalid_flow_entry: not dict")
                    continue
                ghg_list = flow.get("individual_ghg_analyses", [])
                if not isinstance(ghg_list, list):
                    errors.append("invalid_individual_ghg_analyses: not list")
                    continue

                for ghg in ghg_list:
                    if not isinstance(ghg, dict):
                        errors.append("invalid_ghg_entry: not dict")
                        continue

                    rel = ghg.get("qualitative_relationship")
                    mech = ghg.get("mechanism_archetype")
                    conf = ghg.get("confidence")

                    if rel not in VALID_RELATIONSHIPS:
                        errors.append(f"invalid_qualitative_relationship: {rel}")
                    if mech not in VALID_ARCHETYPES:
                        errors.append(f"invalid_mechanism_archetype: {mech}")
                    if conf not in VALID_CONFIDENCE:
                        errors.append(f"invalid_confidence: {conf}")

            if errors:
                invalid_processes[process_id] = errors

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(invalid_processes, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Checked files in {base_dir}")
    print(f"Invalid process count: {len(invalid_processes)}")
    print(f"Saved details to {output_path}")


if __name__ == "__main__":
    main()
