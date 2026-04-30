import hashlib
import json
import logging
import threading
import urllib.error
import urllib.request
from typing import Any, Dict, List, Tuple

from . import config


FINAL_SCHEMA = {
    "name": "submit_final_analysis",
    "description": "Submit the final mechanistic results for the current batch.",
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
                                        "enum": [
                                            "Shared Causal Basis",
                                            "Control Trade-off",
                                            "Distinct Mechanisms",
                                            "Indeterminate",
                                        ],
                                    },
                                    "qualitative_relationship": {
                                        "type": "string",
                                        "enum": ["Positive", "Negative", "Neutral"],
                                    },
                                    "qualitative_reasoning": {
                                        "type": "string",
                                        "description": (
                                            "1-3 sentence mechanism-focused explanation based on the provided context and standard technical knowledge about the named unit process."
                                        ),
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
Do NOT use Negative for normal operation-related fuel use, electricity use, or generic statements such as "pollution control usually consumes energy."
Negative requires a specific in-process trade-off mechanism grounded in the context or a standard, well-established interpretation of the described process.
## 3. Neutral
Use Neutral when the pair does not meet the Positive or Negative criteria:
- the emissions arise from separate mechanisms or separate sub-processes within the unit process,
- or any coupling is too speculative even with standard process knowledge.
Different formation pathways alone are not sufficient for Neutral if another Positive condition is satisfied.
# Mechanism type
Assign exactly one mechanism_archetype:
- Shared Causal Basis
- Control Trade-off
- Distinct Mechanisms
- Indeterminate
Use:
- Shared Causal Basis for Positive,
- Control Trade-off for Negative,
- Distinct Mechanisms for Neutral when separate mechanisms are supported,
- Indeterminate for Neutral when the evidence is too thin to identify a mechanism confidently.
# Key instructions
1. Focus on causal mechanism, not mere co-occurrence.
2. Treat each pollutant-GHG pair independently. Do not reuse the mechanism inferred for one pair unless it is separately supported for the current pair.
3. Do not treat shared equipment, location, stage, or general activity as sufficient evidence.
4. Do not over-penalize sparse wording: if the named process strongly implies a standard mechanism, you may use that knowledge.
5. Do not overreach: if the judgment would require adding an unmentioned device, pathway, or boundary expansion, do not infer it.
6. Still assign a relationship even when textual evidence is limited; then separately rate evidence_sufficiency and confidence.
# Recommended reasoning
For each pair:
1. Identify the specific source operation or sub-process described.
2. Infer the most plausible pollutant-generation or release mechanism within the fixed process.
3. Infer the most plausible GHG-generation or release mechanism within the fixed process.
4. Determine whether they share:
   - a shared causal basis,
   - a control trade-off,
   - distinct mechanisms,
   - or an indeterminate basis.
5. Assign:
   - qualitative_relationship,
   - mechanism_archetype,
   - qualitative_reasoning,
   - evidence,
   - evidence_sufficiency,
   - confidence.
# Evidence sufficiency
- sufficient: the context directly provides enough process detail to support the judgment.
- Limited: the context is brief, but the judgment is still supported by standard process knowledge.
- insufficient: the context provides little direct support and the judgment remains weakly grounded.
# Confidence
- High: mechanism and direction are clear and technically stable.
- Medium: the best judgment is plausible but somewhat ambiguous.
- Low: mechanism attribution is uncertain.
# Output requirements
For each pair:
- qualitative_reasoning: 1-3 sentences, concise and mechanism-focused.
- evidence: up to 2 short snippets from the provided context, quoting only what is necessary.
- Return only valid tool-call JSON arguments matching the schema.
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

DRIVER_FLOWTYPE_KEYWORDS = ["product_flow", "technosphere", "material", "energy", "resource"]


def split_flow_combo(flow_combo: str) -> Tuple[str, str]:
    if " | " in flow_combo:
        left, right = flow_combo.split(" | ", 1)
    elif "|" in flow_combo:
        left, right = flow_combo.split("|", 1)
    else:
        return flow_combo.strip(), ""
    return left.strip(), right.strip()


def normalize_text(value: str) -> str:
    return " ".join((value or "").strip().lower().split())


def compact_text(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    return " ".join(value.split())


def keyword_hit(text: str, keywords: List[str]) -> bool:
    lowered = normalize_text(text)
    return any(keyword in lowered for keyword in keywords)


def target_mechanism_keywords(target_names: List[str]) -> Dict[str, List[str]]:
    combined = normalize_text(" ".join(target_names))
    mapping: Dict[str, List[str]] = {}

    if any(token in combined for token in ["carbon dioxide", "co2", "methane", "ch4", "carbon monoxide"]):
        mapping["carbon_related"] = CARBON_KEYWORDS
    if any(token in combined for token in ["dinitrogen monoxide", "nitrous oxide", "n2o", "ammonia", "nh3", "nitrogen", "nox"]):
        mapping["nitrogen_related"] = NITROGEN_KEYWORDS
    if any(token in combined for token in ["sulfur dioxide", "sulphur dioxide", "so2", "sulfate", "sulphate", "sulfur", "sulphur"]):
        mapping["sulfur_related"] = SULFUR_KEYWORDS
    if any(token in combined for token in ["voc", "volatile organic", "hydrocarbon", "solvent"]):
        mapping["voc_related"] = VOC_KEYWORDS
    return mapping


def flow_category(exchange: Dict[str, Any]) -> str:
    flow = exchange.get("flow") or {}
    return str(flow.get("category") or flow.get("flowType") or "")


def is_target_exchange(exchange: Dict[str, Any], target_name: str, target_category: str) -> bool:
    flow = exchange.get("flow") or {}
    flow_name = normalize_text(flow.get("name", ""))
    exchange_category = normalize_text(flow.get("category") or flow.get("flowType") or "")
    return flow_name == normalize_text(target_name) and exchange_category == normalize_text(target_category)


def exchange_snapshot(index: int, exchange: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "source_path": f"process.exchanges[{index}]",
        "isInput": exchange.get("isInput"),
        "amount": exchange.get("amount"),
        "unit": (exchange.get("unit") or {}).get("name"),
        "flow": {
            "name": compact_text((exchange.get("flow") or {}).get("name")),
            "category": compact_text((exchange.get("flow") or {}).get("category")),
            "flowType": compact_text((exchange.get("flow") or {}).get("flowType")),
        },
    }


def score_exchange(exchange: Dict[str, Any], mechanism_map: Dict[str, List[str]]) -> Tuple[int, List[str]]:
    flow = exchange.get("flow") or {}
    combined = f"{flow.get('name', '')} {flow.get('category') or flow.get('flowType') or ''}"
    reasons: List[str] = []
    score = 0
    is_input = bool(exchange.get("isInput"))
    amount = exchange.get("amount")
    amount_value = amount if isinstance(amount, (int, float)) else 0
    category = normalize_text(flow_category(exchange))

    if is_input:
        score += 220
        reasons.append("input_exchange")
    if amount_value > 0:
        score += 80
        reasons.append("positive_amount")
    if keyword_hit(combined, GENERIC_INPUT_KEYWORDS):
        score += 180
        reasons.append("generic_driver_keyword")
    if any(keyword in category for keyword in DRIVER_FLOWTYPE_KEYWORDS):
        score += 120
        reasons.append("driver_flow_category")
    if not is_input and amount_value > 0 and "product_flow" in category:
        score += 60
        reasons.append("reference_product")
    for label, keywords in mechanism_map.items():
        if keyword_hit(combined, keywords):
            score += 180
            reasons.append(label)

    return score, reasons


class LCAAnalystAgent:
    _client_lock = threading.Lock()
    _clients: List[str] = []
    _client_index = 0
    _request_semaphore = threading.BoundedSemaphore(config.MAX_IN_FLIGHT_MODEL_REQUESTS)

    def __init__(self, model_name: str):
        self.model_name = model_name
        self._ensure_clients()

    @classmethod
    def _ensure_clients(cls) -> None:
        with cls._client_lock:
            if cls._clients:
                return
            cls._clients = list(config.MODELHUB_BASE_URLS)

    @classmethod
    def _client_order(cls, route_key: str | None = None) -> List[str]:
        if not cls._clients:
            return []

        if route_key:
            digest = hashlib.sha256(route_key.encode("utf-8")).hexdigest()
            start_index = int(digest, 16) % len(cls._clients)
            return cls._clients[start_index:] + cls._clients[:start_index]

        with cls._client_lock:
            start_index = cls._client_index % len(cls._clients)
            cls._client_index += 1
        return cls._clients[start_index:] + cls._clients[:start_index]

    def _build_tools(self) -> List[Dict[str, Any]]:
        return [{"type": "function", "function": FINAL_SCHEMA}]

    def _chat(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        route_key: str | None = None,
    ) -> Dict[str, Any]:
        last_error: Exception | None = None
        payload = {
            "model": self.model_name,
            "messages": messages,
            "tools": tools,
            "tool_choice": {
                "type": "function",
                "function": {"name": FINAL_SCHEMA["name"]},
            },
            "temperature": config.MODEL_TEMPERATURE,
        }

        with type(self)._request_semaphore:
            for base_url in self._client_order(route_key=route_key):
                request = urllib.request.Request(
                    f"{base_url}/chat/completions",
                    data=json.dumps(payload).encode("utf-8"),
                    method="POST",
                    headers={
                        "Authorization": f"Bearer {config.MODELHUB_API_KEY}",
                        "Content-Type": "application/json",
                        "Accept": "application/json",
                        "User-Agent": "Mozilla/5.0",
                    },
                )
                try:
                    with urllib.request.urlopen(request, timeout=config.MODEL_TIMEOUT_SECONDS) as response:
                        return json.loads(response.read().decode("utf-8"))
                except urllib.error.HTTPError as exc:
                    body = exc.read().decode("utf-8", errors="replace")
                    last_error = RuntimeError(
                        f"HTTP {exc.code} from {base_url}/chat/completions: {body}"
                    )
                    logging.warning("Model request failed via %s: %s", base_url, last_error)
                except Exception as exc:
                    last_error = exc
                    logging.warning("Model request failed via %s: %s", base_url, exc)
        if last_error is None:
            raise RuntimeError("No model clients are configured.")
        raise last_error

    def _parse_response(self, response: Dict[str, Any]) -> Dict[str, Any]:
        choices = response.get("choices") or []
        if not choices:
            raise ValueError("Model response does not contain choices.")

        message = (choices[0] or {}).get("message") or {}
        tool_calls = message.get("tool_calls") or []
        if tool_calls:
            for tool_call in tool_calls:
                function = tool_call.get("function") or {}
                if function.get("name") != FINAL_SCHEMA["name"]:
                    continue
                return json.loads(function.get("arguments") or "{}")

        content = message.get("content")
        if isinstance(content, str) and content:
            return json.loads(content)
        if isinstance(content, list):
            text_parts = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    text_parts.append(item.get("text", ""))
            if text_parts:
                return json.loads("".join(text_parts))
        raise ValueError("Could not parse tool-call JSON from model response.")

    def build_slim_context(
        self,
        process_id: str,
        process_data: Dict[str, Any],
        flow_info: Dict[str, str],
        ghg_chunk: List[str],
        max_driver_exchanges: int = 16,
        max_supporting_exchanges: int = 8,
    ) -> Dict[str, Any]:
        pollutant_name, pollutant_category = split_flow_combo(flow_info["flow_combo"])
        ghg_targets = [split_flow_combo(item) for item in ghg_chunk]
        mechanism_map = target_mechanism_keywords(
            [pollutant_name, *[name for name, _ in ghg_targets]]
        )

        pollutant_target_exchanges: List[Dict[str, Any]] = []
        ghg_target_exchanges: List[Dict[str, Any]] = []
        driver_candidates: List[Tuple[int, Dict[str, Any]]] = []
        supporting_candidates: List[Tuple[int, Dict[str, Any]]] = []

        for index, exchange in enumerate(process_data.get("exchanges", [])):
            snapshot = exchange_snapshot(index, exchange)

            if is_target_exchange(exchange, pollutant_name, pollutant_category):
                pollutant_target_exchanges.append(snapshot)
                continue

            if any(is_target_exchange(exchange, name, category) for name, category in ghg_targets):
                ghg_target_exchanges.append(snapshot)
                continue

            score, reasons = score_exchange(exchange, mechanism_map)
            if score <= 0:
                continue

            flow_text = f"{snapshot['flow']['name']} {snapshot['flow']['category']} {snapshot['flow']['flowType']}"
            flow_type_text = normalize_text(snapshot["flow"]["flowType"] or snapshot["flow"]["category"] or "")
            is_driver_candidate = bool(snapshot["isInput"]) and (
                keyword_hit(flow_text, GENERIC_INPUT_KEYWORDS)
                or any(keyword in flow_type_text for keyword in DRIVER_FLOWTYPE_KEYWORDS)
                or any(reason.endswith("_related") for reason in reasons)
            )

            candidate = (score, snapshot)
            if is_driver_candidate:
                driver_candidates.append(candidate)
            else:
                supporting_candidates.append(candidate)

        driver_candidates.sort(key=lambda item: (-item[0], item[1]["source_path"]))
        supporting_candidates.sort(key=lambda item: (-item[0], item[1]["source_path"]))

        return {
            "source_path": "process",
            "name": compact_text(process_data.get("name")),
            "description": compact_text(process_data.get("description")),
            "processDocumentation": {
                "technologyDescription": compact_text(
                    (process_data.get("processDocumentation") or {}).get("technologyDescription")
                )
            },
            "target_batch": {
                "process_id": process_id,
                "flow_combo": compact_text(flow_info["flow_combo"]),
                "ghg_combos": [compact_text(item) for item in ghg_chunk],
            },
            "selection_notes": {
                "total_exchange_count": len(process_data.get("exchanges", [])),
                "pollutant_target_exchange_count": len(pollutant_target_exchanges),
                "ghg_target_exchange_count": len(ghg_target_exchanges),
                "driver_exchange_count": min(len(driver_candidates), max_driver_exchanges),
                "supporting_exchange_count": min(len(supporting_candidates), max_supporting_exchanges),
                "mechanism_mapping_labels": sorted(mechanism_map),
            },
            "pollutant_target_exchanges": pollutant_target_exchanges,
            "ghg_target_exchanges": ghg_target_exchanges,
            "driver_exchanges": [item[1] for item in driver_candidates[:max_driver_exchanges]],
            "supporting_exchanges": [item[1] for item in supporting_candidates[:max_supporting_exchanges]],
        }

    def build_messages(self, slim_context: Dict[str, Any]) -> List[Dict[str, Any]]:
        compact_context = json.dumps(
            slim_context,
            ensure_ascii=False,
            separators=(",", ":"),
        )
        user_content = f"""{CORE_PROMPT}

# Context Data
{compact_context}

# Instruction
Analyze the current target batch only.
Return the result by calling `submit_final_analysis`.
"""
        return [{"role": "user", "content": user_content}]

    def analyze_flow_chunk(
        self,
        process_id: str,
        process_data: Dict[str, Any],
        flow_info: Dict[str, str],
        ghg_chunk: List[str],
    ) -> Dict[str, Any]:
        slim_context = self.build_slim_context(process_id, process_data, flow_info, ghg_chunk)
        messages = self.build_messages(slim_context)
        response = self._chat(
            messages=messages,
            tools=self._build_tools(),
            route_key=process_id,
        )
        parsed = self._parse_response(response)
        flow_analyses = parsed.get("flow_analyses") or []

        requested_ghgs = set(ghg_chunk)
        requested_flow_combo = flow_info["flow_combo"]

        for flow_analysis in flow_analyses:
            if flow_analysis.get("flow_combo") != requested_flow_combo:
                continue
            filtered_ghgs = [
                analysis
                for analysis in flow_analysis.get("individual_ghg_analyses") or []
                if analysis.get("ghg_combo") in requested_ghgs
            ]
            return {
                "process_id": flow_analysis.get("process_id") or process_id,
                "flow_combo": requested_flow_combo,
                "individual_ghg_analyses": filtered_ghgs,
            }

        return {
            "process_id": process_id,
            "flow_combo": requested_flow_combo,
            "individual_ghg_analyses": [],
        }
