import argparse
import concurrent.futures
import json
import os
import random
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path


# Change this path when you want to run a different sample JSON.
DEFAULT_SAMPLE_JSON_PATH = Path("output/agent_results/stratified_samples/Positive_Medium.json")
PROCESS_DIR = Path("data/process_compressed")
OUTPUT_DIR = Path("output/agent_results/verified_stratified_samples/results")
MODEL_NAME = "gpt-5.4"
DEFAULT_MODELHUB_BASE_URL = os.getenv("MODELHUB_BASE_URL", "https://modelhub.ailemac.com/v1").rstrip("/")
MODELHUB_CHAT_URL = os.getenv("MODELHUB_CHAT_URL", f"{DEFAULT_MODELHUB_BASE_URL}/chat/completions")


FINAL_SCHEMA = {
    "name": "submit_final_analysis",
    "description": "Submit the final mechanistic re-judgment results for the current batch.",
    "parameters": {
        "type": "object",
        "properties": {
            "flow_analyses": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "process_id": {"type": "string"},
                        "flow_combo": {"type": "string"},
                        "individual_ghg_analyses": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "ghg_combo": {"type": "string"},
                                    "mechanism_archetype": {
                                        "type": "string",
                                        "enum": ["Shared Causal Basis", "Control Trade-off", "Distinct Mechanisms", "Indeterminate"],
                                    },
                                    "qualitative_relationship": {
                                        "type": "string",
                                        "enum": ["Positive", "Negative", "Neutral"],
                                    },
                                    "qualitative_reasoning": {
                                        "type": "string",
                                        "description": "1-3 sentence mechanism-focused explanation based on the provided context and standard technical knowledge about the named unit process.",
                                    },
                                    "evidence_sufficiency": {
                                        "type": "string",
                                        "enum": ["sufficient", "insufficient", "Limited"],
                                    },
                                    "confidence": {
                                        "type": "string",
                                        "enum": ["High", "Medium", "Low"],
                                    },
                                    "evidence": {
                                        "type": "array",
                                        "items": {
                                            "type": "object",
                                            "properties": {
                                                "source_path": {"type": "string"},
                                                "quote": {"type": "string"},
                                            },
                                            "required": ["source_path", "quote"],
                                        },
                                        "maxItems": 2,
                                    },
                                },
                                "required": [
                                    "ghg_combo",
                                    "mechanism_archetype",
                                    "qualitative_relationship",
                                    "qualitative_reasoning",
                                    "evidence_sufficiency",
                                    "confidence",
                                ],
                            },
                        },
                    },
                    "required": ["process_id", "flow_combo", "individual_ghg_analyses"],
                },
            }
        },
        "required": ["flow_analyses"],
    },
}


CORE_PROMPT = """
# Role
You are an LCA mechanistic reviewer. For each pollutant-GHG pair within one fixed unit process, determine whether the relationship is Positive, Negative, or Neutral.
# Goal
Judge the relationship mechanistically using:
1. the provided Context Data, and
2. standard technical knowledge about the named unit process.
You may infer standard in-process emission mechanisms that are well established for the described process, but you must not invent extra unit operations, control technologies, or boundary expansions.
# Fixed boundary
Keep fixed:
- the same unit process,
- the same functional unit,
- the same operating context and throughput.
Do NOT infer:
- scenario changes,
- optimization or operational improvement,
- demand or scale effects,
- upstream/downstream shifts,
- unspecified abatement devices or energy penalties,
- plant modifications not indicated in the context.
# Relationship definitions
Assign exactly one qualitative_relationship:
## 1. Positive
Use Positive when the pollutant and GHG share the same in-process causal basis.
This applies if one of the following holds:
- the same physico-chemical formation pathway,
- the same release mechanism,
- the same emitted process stream / exhaust stream / fugitive stream,
- the same reaction network producing both as coproducts/byproducts,
- the same clearly identified source operation with direct co-generation, which means a specific emission-generating source within the unit process from which both emissions are directly released. This is stronger than merely being in the same activity, equipment, or stage.
This shared causal basis may be explicitly stated in the context or strongly inferable from standard technical knowledge about the named unit process. Any one Positive condition is sufficient. If any Positive condition is satisfied, do not assign Neutral merely because the pollutant and GHG differ in detailed formation chemistry or differ in micro-level formation pathways.
Do NOT use Positive based only on:
- same operational activity,
- same equipment,
- same stage,
- same fuel-consuming event,
- generic shared dependence on temperature, residence time, oxygen level, efficiency, or throughput,
unless these are clearly part of the same formation or release mechanism for both emissions.
## 2. Negative
Use Negative only when the context supports a clear opposing relationship or transfer mechanism within the same unit process.
At least one of the following must apply:
- an explicit inverse control relation,
- explicit pollution transfer / phase transfer,
- explicitly stated competing reaction pathways with substitution between the pollutant and GHG,
- explicitly stated abatement burden: extra fuel, reagent, energy, or process steps introduced to control one emission and thereby increasing the other.
Do NOT use Negative for normal operation-related fuel use, electricity use, or generic statements such as “pollution control usually consumes energy.”
Negative requires a specific in-process trade-off mechanism grounded in the context or a standard, well-established interpretation of the described process.
## 3. Neutral
Use Neutral when the pair does not meet the Positive or Negative criteria:
- the emissions arise from separate mechanisms or separate sub-processes within the unit process,
- or any coupling is too speculative even with standard process knowledge.
Different formation pathways alone are not sufficient for Neutral if another Positive condition is satisfied.
# Mechanism type
Assign exactly one mechanism_type:
- Shared Causal Basis
- Control Trade-off
- Distinct Mechanisms
- Indeterminate
Use:
- Shared Causal Basis for Positive,
- Control Trade-off for Negative,
- Distinct Mechanisms for Neutral,
- Indeterminate for Neutral.
# Key instructions
1. Focus on causal mechanism, not mere co-occurrence.
2. Do not treat shared equipment, location, stage, or general activity as sufficient evidence.
3. Do not over-penalize sparse wording: if the named process strongly implies a standard mechanism, you may use that knowledge.
4. Do not overreach: if the judgment would require adding an unmentioned device, pathway, or boundary expansion, do not infer it.
5. Still assign a relationship even when textual evidence is limited; then separately rate evidence_sufficiency and confidence.
# Recommended reasoning
For each pair:
1. Identify the specific source operation or sub-process described.
2. Infer the most plausible pollutant-generation mechanism within the fixed process.
3. Infer the most plausible GHG-generation mechanism within the fixed process.
4. Determine whether they share:
   - a shared causal basis,
   - a control trade-off,
   - distinct mechanisms,
   - or indeterminate.
5. Assign:
   - qualitative_relationship,
   - mechanism_type,
   - qualitative_reasoning,
   - evidence,
   - evidence_sufficiency,
   - confidence.
# Evidence sufficiency
- Sufficient: the context directly provides enough process detail to support the judgment.
- Limited: the context is brief, but the judgment is still supported by standard process knowledge.
- Insufficient: the context provides little direct support and the judgment remains weakly grounded.
# Confidence
- High: mechanism and direction are clear and technically stable.
- Medium: the best judgment is plausible but somewhat ambiguous.
- Low: mechanism attribution is uncertain.
# Output requirements
For each pair:
- qualitative_reasoning: 1-3 sentences, concise and mechanism-focused
- evidence: up to 2 short snippets from the provided context
- Return only valid tool-call JSON arguments matching the schema
""".strip()


GENERIC_INPUT_KEYWORDS = [
    "electricity",
    "heat",
    "steam",
    "fuel",
    "gas",
    "diesel",
    "petrol",
    "gasoline",
    "oil",
    "coal",
    "coke",
    "lignite",
    "char",
    "biogas",
    "biomass",
    "wood",
    "natural gas",
    "material",
    "chemical",
    "reagent",
    "catalyst",
    "solvent",
    "auxiliary",
    "additive",
    "treatment",
    "lime",
    "caustic",
    "ammonia",
    "urea",
    "acid",
    "water",
    "oxygen",
    "air",
]

CARBON_KEYWORDS = [
    "carbon",
    "carbon dioxide",
    "co2",
    "methane",
    "ch4",
    "natural gas",
    "diesel",
    "gasoline",
    "petrol",
    "fuel oil",
    "coal",
    "coke",
    "lignite",
    "biogas",
    "biomass",
    "ethanol",
    "methanol",
]

NITROGEN_KEYWORDS = [
    "nitrogen",
    "ammonia",
    "ammonium",
    "urea",
    "nitrate",
    "nitrite",
    "nitric",
    "nox",
    "n2o",
    "fertiliser",
    "fertilizer",
]

SULFUR_KEYWORDS = [
    "sulfur",
    "sulphur",
    "sulfate",
    "sulphate",
    "sulfide",
    "sulphide",
    "sulfuric",
    "sulphuric",
    "gypsum",
    "so2",
]

VOC_KEYWORDS = [
    "voc",
    "solvent",
    "organic",
    "hydrocarbon",
    "benzene",
    "toluene",
    "xylene",
    "acetone",
    "ethyl acetate",
    "methanol",
    "ethanol",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Blind re-judgment runner for stratified pollutant-GHG samples.")
    parser.add_argument("--sample-json", default=str(DEFAULT_SAMPLE_JSON_PATH), help="Path to one sampled JSON file.")
    parser.add_argument("--seed", type=int, default=42, help="Random seed for trial mode.")
    parser.add_argument("--limit-groups", type=int, default=0, help="How many grouped flow batches to run. Use 0 or negative for all groups.")
    parser.add_argument("--max-workers", type=int, default=4, help="How many groups to run in parallel.")
    parser.add_argument("--resume-run-dir", help="Existing run directory to resume from. Completed groups in all_groups.jsonl will be skipped.")
    parser.add_argument("--save-group-files", action="store_true", help="Also save individual group_XXX.json files.")
    parser.add_argument("--dry-run", action="store_true", help="Skip LLM calls and save prepared inputs only.")
    return parser.parse_args()


def load_env_value(key: str, env_path: Path = Path(".env")) -> str:
    value = os.getenv(key)
    if value:
        return value.strip()

    if not env_path.exists():
        return ""

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        current_key, current_value = line.split("=", 1)
        if current_key.strip() == key:
            return current_value.strip()
    return ""


def load_json(path: Path):
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def dump_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)


def load_completed_indices(jsonl_path: Path) -> set[int]:
    if not jsonl_path.exists():
        return set()

    completed = set()
    with jsonl_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            index = record.get("index")
            if isinstance(index, int):
                completed.add(index)
    return completed


def build_summary_results_from_jsonl(jsonl_path: Path, save_group_files: bool, run_dir: Path) -> list[dict]:
    results = []
    if not jsonl_path.exists():
        return results

    with jsonl_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue

            group = record.get("group") or {}
            result_summary = {
                "index": record.get("index"),
                "process_id": group.get("process_id"),
                "flow_combo": group.get("flow_combo"),
                "ghg_combos": group.get("ghg_combos"),
                "llm_result": record.get("llm_result"),
                "dry_run": record.get("dry_run", False),
            }

            if save_group_files:
                group_file = run_dir / f"group_{record.get('index', 0):03d}.json"
                if group_file.exists():
                    result_summary["result_file"] = str(group_file)

            results.append(result_summary)

    return sorted(results, key=lambda item: item.get("index") or 0)


def split_flow_combo(flow_combo: str) -> tuple[str, str]:
    if "|" not in flow_combo:
        return flow_combo.strip(), ""
    left, right = flow_combo.split("|", 1)
    return left.strip(), right.strip()


def normalize_text(value: str) -> str:
    return " ".join((value or "").strip().lower().split())


def compact_text(value):
    if not isinstance(value, str):
        return value
    return " ".join(value.split())


def build_groups(records: list[dict]) -> list[dict]:
    grouped: dict[tuple[str, str], dict] = {}
    for record in records:
        key = (record["process_id"], record["flow_combo"])
        if key not in grouped:
            grouped[key] = {
                "process_id": record["process_id"],
                "flow_combo": record["flow_combo"],
                "ghg_combos": [],
                "original_records": [],
            }
        grouped[key]["ghg_combos"].append(record["ghg_combo"])
        grouped[key]["original_records"].append(record)

    groups = []
    for item in grouped.values():
        item["ghg_combos"] = sorted(set(item["ghg_combos"]))
        groups.append(item)

    groups.sort(key=lambda item: (item["process_id"], item["flow_combo"]))
    return groups


def is_target_exchange(exchange: dict, target_name: str, target_category: str) -> bool:
    flow = exchange.get("flow") or {}
    flow_name = normalize_text(flow.get("name", ""))
    flow_category = normalize_text(flow.get("category") or flow.get("flowType") or "")
    return flow_name == normalize_text(target_name) and flow_category == normalize_text(target_category)


def keyword_hit(text: str, keywords: list[str]) -> bool:
    lowered = normalize_text(text)
    return any(keyword in lowered for keyword in keywords)


def target_mechanism_keywords(target_names: list[str]) -> dict[str, list[str]]:
    combined = normalize_text(" ".join(target_names))
    mapping = {}

    if any(token in combined for token in ["carbon dioxide", "co2", "methane", "ch4", "carbon monoxide"]):
        mapping["carbon_related"] = CARBON_KEYWORDS

    if any(token in combined for token in ["dinitrogen monoxide", "nitrous oxide", "n2o", "ammonia", "nh3", "nitrogen", "nox"]):
        mapping["nitrogen_related"] = NITROGEN_KEYWORDS

    if any(token in combined for token in ["sulfur dioxide", "sulphur dioxide", "so2", "sulfate", "sulphate", "sulfur", "sulphur"]):
        mapping["sulfur_related"] = SULFUR_KEYWORDS

    if any(token in combined for token in ["voc", "volatile organic", "hydrocarbon", "solvent"]):
        mapping["voc_related"] = VOC_KEYWORDS

    return mapping


def score_exchange(exchange: dict, exact_targets: list[tuple[str, str]], mechanism_map: dict[str, list[str]]) -> tuple[int, list[str]]:
    flow = exchange.get("flow") or {}
    flow_name = flow.get("name", "")
    flow_category = flow.get("category") or flow.get("flowType") or ""
    combined = f"{flow_name} {flow_category}"
    reasons = []
    score = 0

    for target_name, target_category in exact_targets:
        if is_target_exchange(exchange, target_name, target_category):
            reasons.append("target_flow")
            score += 10_000
            break

    is_input = bool(exchange.get("isInput"))
    amount = exchange.get("amount")
    amount_value = amount if isinstance(amount, (int, float)) else 0

    if is_input:
        reasons.append("input_exchange")
        score += 220

    if amount_value > 0:
        reasons.append("positive_amount")
        score += 80

    if keyword_hit(combined, GENERIC_INPUT_KEYWORDS):
        reasons.append("generic_control_or_input")
        score += 150

    if keyword_hit(flow_category, ["product_flow", "technosphere", "material", "energy", "resource", "resource in ground", "resource in water"]):
        reasons.append("relevant_flow_category")
        score += 120

    if not is_input and amount_value > 0 and keyword_hit(flow_category, ["product_flow"]):
        reasons.append("reference_product")
        score += 60

    for label, keywords in mechanism_map.items():
        if keyword_hit(combined, keywords):
            reasons.append(label)
            score += 180

    return score, reasons


def slim_process_context(process_data: dict, group: dict, max_related_exchanges: int = 36) -> dict:
    pollutant_name, pollutant_category = split_flow_combo(group["flow_combo"])
    ghg_targets = [split_flow_combo(item) for item in group["ghg_combos"]]
    exact_targets = [(pollutant_name, pollutant_category), *ghg_targets]
    mechanism_map = target_mechanism_keywords([pollutant_name, *[name for name, _ in ghg_targets]])

    retained = []
    for index, exchange in enumerate(process_data.get("exchanges", [])):
        score, reasons = score_exchange(exchange, exact_targets, mechanism_map)
        if score <= 0:
            continue

        retained.append(
            {
                "source_path": f"process.exchanges[{index}]",
                "isInput": exchange.get("isInput"),
                "amount": exchange.get("amount"),
                "unit": (exchange.get("unit") or {}).get("name"),
                "flow": {
                    "name": compact_text((exchange.get("flow") or {}).get("name")),
                    "category": compact_text((exchange.get("flow") or {}).get("category")),
                    "flowType": compact_text((exchange.get("flow") or {}).get("flowType")),
                },
                "_retention_score": score,
                "_retention_reasons": reasons,
            }
        )

    retained.sort(key=lambda item: (-item["_retention_score"], item["source_path"]))
    hard_kept = [item for item in retained if "target_flow" in item["_retention_reasons"]]
    optional = [item for item in retained if "target_flow" not in item["_retention_reasons"]]
    selected = []
    for item in hard_kept + optional[:max_related_exchanges]:
        selected.append(
            {
                "source_path": item["source_path"],
                "isInput": item["isInput"],
                "amount": item["amount"],
                "unit": item["unit"],
                "flow": item["flow"],
            }
        )

    return {
        "source_path": "process",
        "name": compact_text(process_data.get("name")),
        "description": compact_text(process_data.get("description")),
        "processDocumentation": {
            "technologyDescription": compact_text((process_data.get("processDocumentation") or {}).get("technologyDescription"))
        },
        "target_batch": {
            "process_id": group["process_id"],
            "flow_combo": compact_text(group["flow_combo"]),
            "ghg_combos": [compact_text(item) for item in group["ghg_combos"]],
        },
        "selection_notes": {
            "total_exchange_count": len(process_data.get("exchanges", [])),
            "retained_exchange_count": len(selected),
            "mechanism_mapping_labels": sorted(mechanism_map),
        },
        "exchanges": selected,
    }


def build_messages(slim_context: dict) -> list[dict]:
    compact_context = json.dumps(slim_context, ensure_ascii=False, separators=(",", ":"))
    user_content = f"""{CORE_PROMPT}

# Context Data
{compact_context}

# Instruction
Analyze the current target batch only.
Call `submit_final_analysis` when done.
"""
    return [{"role": "user", "content": user_content}]


def call_modelhub(messages: list[dict], api_key: str) -> dict:
    payload = {
        "model": MODEL_NAME,
        "messages": messages,
        "tools": [{"type": "function", "function": FINAL_SCHEMA}],
        "tool_choice": {"type": "function", "function": {"name": FINAL_SCHEMA["name"]}},
    }

    request = urllib.request.Request(
        MODELHUB_CHAT_URL,
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "Mozilla/5.0",
        },
    )

    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        message = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"ModelHub request failed with status {error.code}: {message}") from error


def parse_model_response(response_json: dict) -> dict:
    choices = response_json.get("choices") or []
    if not choices:
        raise ValueError("Model response does not contain choices.")

    message = (choices[0] or {}).get("message") or {}
    tool_calls = message.get("tool_calls") or []
    if tool_calls:
        arguments = (((tool_calls[0] or {}).get("function") or {}).get("arguments")) or "{}"
        return json.loads(arguments)

    content = message.get("content")
    if isinstance(content, str):
        return json.loads(content)

    if isinstance(content, list):
        text_parts = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                text_parts.append(item.get("text", ""))
        if text_parts:
            return json.loads("".join(text_parts))

    raise ValueError("Could not parse tool-call JSON from model response.")


def run_group(group: dict, dry_run: bool, api_key: str) -> dict:
    process_path = PROCESS_DIR / f"{group['process_id']}.json"
    if not process_path.exists():
        raise FileNotFoundError(f"Missing process JSON: {process_path}")

    process_data = load_json(process_path)
    slim_context = slim_process_context(process_data, group)
    messages = build_messages(slim_context)

    result = {
        "group": {
            "process_id": group["process_id"],
            "flow_combo": group["flow_combo"],
            "ghg_combos": group["ghg_combos"],
        },
        "context": slim_context,
    }

    if dry_run:
        result["dry_run"] = True
        result["llm_result"] = None
        return result

    raw_response = call_modelhub(messages, api_key=api_key)
    parsed_response = parse_model_response(raw_response)
    result["raw_response"] = raw_response
    result["llm_result"] = parsed_response
    return result


def main() -> int:
    args = parse_args()
    random.seed(args.seed)

    sample_json_path = Path(args.sample_json)
    if not sample_json_path.exists():
        print(f"Sample JSON not found: {sample_json_path}", file=sys.stderr)
        return 1

    records = load_json(sample_json_path)
    if not isinstance(records, list) or not records:
        print(f"Sample JSON is empty or not a list: {sample_json_path}", file=sys.stderr)
        return 1

    groups = build_groups(records)
    if args.limit_groups and args.limit_groups > 0:
        selected_groups = random.sample(groups, k=min(args.limit_groups, len(groups)))
    else:
        selected_groups = groups

    api_key = load_env_value("MODELHUB_API_KEY")
    if not args.dry_run and not api_key:
        print("MODELHUB_API_KEY is missing.", file=sys.stderr)
        return 1

    if args.resume_run_dir:
        run_dir = Path(args.resume_run_dir)
        run_dir.mkdir(parents=True, exist_ok=True)
    else:
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        run_name = sample_json_path.stem
        run_dir = OUTPUT_DIR / f"{run_name}_{timestamp}"
        run_dir.mkdir(parents=True, exist_ok=True)

    all_groups_jsonl_path = run_dir / "all_groups.jsonl"
    completed_indices = load_completed_indices(all_groups_jsonl_path)

    summary = {
        "sample_json_path": str(sample_json_path),
        "selected_group_count": len(selected_groups),
        "dry_run": args.dry_run,
        "max_workers": args.max_workers,
        "resume_run_dir": str(run_dir) if args.resume_run_dir else None,
        "skipped_completed_groups": len(completed_indices),
        "save_group_files": args.save_group_files,
        "model_name": MODEL_NAME,
        "modelhub_chat_url": MODELHUB_CHAT_URL,
        "all_groups_jsonl": str(all_groups_jsonl_path),
        "results": [],
        "errors": [],
    }

    indexed_groups = list(enumerate(selected_groups, start=1))
    indexed_groups = [(index, group) for index, group in indexed_groups if index not in completed_indices]
    summary["remaining_group_count"] = len(indexed_groups)

    if not indexed_groups:
        summary["results"] = build_summary_results_from_jsonl(all_groups_jsonl_path, args.save_group_files, run_dir)
        dump_json(run_dir / "summary.json", summary)
        print(f"No remaining groups to run. Existing outputs kept in: {run_dir}")
        return 0

    max_workers = max(1, min(args.max_workers, len(indexed_groups) or 1))

    for index, group in indexed_groups:
        print(f"[queued {index}/{len(selected_groups)}] process={group['process_id']} flow={group['flow_combo']}")

    jsonl_mode = "a" if completed_indices else "w"
    with all_groups_jsonl_path.open(jsonl_mode, encoding="utf-8") as jsonl_handle:
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_job = {
                executor.submit(run_group, group, args.dry_run, api_key): (index, group)
                for index, group in indexed_groups
            }

            completed_results = []
            completed_errors = []

            for future in concurrent.futures.as_completed(future_to_job):
                index, group = future_to_job[future]
                try:
                    group_result = future.result()
                    jsonl_record = {
                        "index": index,
                        "group": group_result.get("group"),
                        "context": group_result.get("context"),
                        "raw_response": group_result.get("raw_response"),
                        "llm_result": group_result.get("llm_result"),
                        "dry_run": group_result.get("dry_run", False),
                    }
                    jsonl_handle.write(json.dumps(jsonl_record, ensure_ascii=False) + "\n")

                    result_summary = {
                        "index": index,
                        "process_id": group["process_id"],
                        "flow_combo": group["flow_combo"],
                        "ghg_combos": group["ghg_combos"],
                        "llm_result": group_result.get("llm_result"),
                        "dry_run": group_result.get("dry_run", False),
                    }

                    if args.save_group_files:
                        group_file = run_dir / f"group_{index:03d}.json"
                        dump_json(group_file, group_result)
                        result_summary["result_file"] = str(group_file)

                    completed_results.append(result_summary)
                    print(f"[done {index}/{len(selected_groups)}] process={group['process_id']} flow={group['flow_combo']}")
                except Exception as error:
                    completed_errors.append(
                        {
                            "index": index,
                            "process_id": group["process_id"],
                            "flow_combo": group["flow_combo"],
                            "ghg_combos": group["ghg_combos"],
                            "error": str(error),
                        }
                    )
                    print(f"[error {index}/{len(selected_groups)}] process={group['process_id']} flow={group['flow_combo']}: {error}", file=sys.stderr)

    summary["results"] = build_summary_results_from_jsonl(all_groups_jsonl_path, args.save_group_files, run_dir)
    summary["errors"] = sorted(completed_errors, key=lambda item: item["index"])

    dump_json(run_dir / "summary.json", summary)
    print(f"Saved run outputs to: {run_dir}")
    print(f"Completed groups: {len(summary['results'])}, errors: {len(summary['errors'])}")
    return 0 if not summary["errors"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
