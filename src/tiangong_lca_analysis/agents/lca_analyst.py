import json
import logging
import os
from typing import Any, Dict, List

from openai import OpenAI

# 使用相对导入从同一目录导入config
from . import config  # 导入配置以获取基础地址


class LCAAnalystAgent:
    """
    自主迭代式 LCA 分析智能体，利用 tool calling + 迭代循环进行碳污关系分析。
    """
    def __init__(self, model_name: str):
        self.model_name = model_name

        # 1. 初始化 OpenAI Client（指向本地 vLLM 服务，不再需要 API Key）
        request_timeout = float(os.getenv("LCA_REQUEST_TIMEOUT", "300"))
        self.client = OpenAI(
            api_key="EMPTY",
            base_url=config.VLLM_BASE_URL,
            timeout=request_timeout,
        )

        # 控制每次请求的 flow 数量，避免 prompt 过大导致超时
        self.batch_size = max(1, int(os.getenv("LCA_BATCH_SIZE", "3")))

        print(f"[*] LCA Agent initialized with model: {self.model_name} (local vLLM endpoint).")
        print(f"    [-] Using batch size = {self.batch_size}, timeout = {request_timeout}s.")

    def _define_final_schema(self):
        """
        定义最终提交工具的 JSON Schema。
        """
        return {
            "name": "submit_final_analysis",
            "description": "Submit the final analysis for the current batch of flows.",
            "parameters": {
                "type": "object",
                "properties": {
                    "flow_analyses": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "flow_combo": {"type": "string", "description": "The exact flow identifier provided in input."},
                                "individual_ghg_analyses": {
                                    "type": "array",
                                    "items": {
                                        "type": "object",
                                        "properties": {
                                            "ghg_combo": {"type": "string"},
                                            "qualitative_relationship": {"type": "string", "enum": ["Positive", "Negative", "Neutral"]},
                                            "qualitative_reasoning": {"type": "string", "description": "Brief explanation based on the Mechanism Archetypes."},
                                            "mechanism_archetype": {
                                                "type": "string", 
                                                "enum": ["Shared Driver", "Trade-off", "Efficiency Synergy", "Decoupled"],
                                                "description": "The logic category used."
                                            },
                                            "confidence": {"type": "string", "enum": ["High", "Medium", "Low"]}
                                        },
                                        "required": ["ghg_combo", "qualitative_relationship", "qualitative_reasoning", "mechanism_archetype"]
                                    }
                                }
                            },
                            "required": ["flow_combo", "individual_ghg_analyses"]
                        }
                    }
                },
                "required": ["flow_analyses"]
            }
        }

    def _build_tools(self) -> List[Dict[str, Any]]:
        final_tool_schema = self._define_final_schema()
        return [{"type": "function", "function": final_tool_schema}]

    def _chat(self, messages: List[Dict[str, Any]], tools: List[Dict[str, Any]]) -> Any:
        return self.client.chat.completions.create(
            model=self.model_name,
            messages=messages,
            tools=tools,
            tool_choice="auto",
        )

    def _build_batch_context(
        self,
        process_data: Dict[str, Any],
        exchange_map: Dict[str, List[Dict[str, Any]]],
        batch_flows: List[Dict[str, Any]],
        relevant_ghgs: List[str],
    ) -> str:
        """
        根据当前批次筛选出紧凑的上下文，避免把整个 process JSON 都塞进 prompt。
        """
        combos = {flow.get("flow_combo") for flow in batch_flows}
        combos.update(relevant_ghgs or [])

        exchange_snippets: List[Dict[str, Any]] = []
        for combo in sorted(combo for combo in combos if combo):
            entries = exchange_map.get(combo)
            if entries:
                for entry in entries:
                    exchange_snippets.append(
                        {
                            "flow_combo": combo,
                            "is_input": entry.get("is_input"),
                            "amount": entry.get("amount"),
                            "unit": entry.get("unit"),
                            "flow_type": entry.get("flow_type"),
                        }
                    )
            else:
                exchange_snippets.append(
                    {
                        "flow_combo": combo,
                        "note": "not present in process exchanges",
                    }
                )

        context_payload = {
            "process_name": process_data.get("name"),
            "description": process_data.get("description", ""),
            "technology": process_data.get("processDocumentation", {}).get("technologyDescription", ""),
            "batch_exchanges": exchange_snippets,
        }

        return json.dumps(context_payload, ensure_ascii=False, indent=2)

    def _run_batch_analysis(self, process_context: str, batch_flows: List[Dict], ghg_list_str: str, max_iterations: int = 5) -> List[Dict]:
        """
        运行单个批次的分析（单轮对话，不再迭代）。
        """
        tools = self._build_tools()

        core_prompt = """
# Goal
Determine the mechanistic relationship between specific Pollutants and each Greenhouse Gase (GHG) within a given fixed unit process.

# The Mechanism Framework (Archetypes)
When analyzing the relationship, you MUST map it to one of these 4 archetypes:
1. Shared Driver (Positive): Both originate from the same explicitly-modeled sub-processes (e.g., the same chemical reaction, or the same physical unit operation event), or fuel source, or explicitly modeled energy flow (e.g., Combustion generates CO2 and releases Mercury from coal).
2. Trade-off (Negative): Abatement of the pollutant consumes energy/chemicals, generating GHGs (e.g., Scrubber removes SO2 but uses electricity -> Indirect CO2).
3. Process Synergy (Positive): A specific underlying process parameter within the unit process (e.g., combustion temperature, reaction pressure) directly constitutes the formation mechanism for BOTH flows. Do NOT assume hypothetical operational or behavioral improvements.
4. Decoupled (Neutral): The pollutant and GHG originate from mechanistically independent sub-processes, with no shared reaction, control parameter, or energy-based coupling (e.g., Noise vs Combustion CO2).

# Step-by-step instruction
You must follow this sequence internally for EACH flow:
1. Process Decomposition: Break the technology description into unit operations (e.g., combustion, Reaction, Separation).
2. Source Mapping: Pinpoint exactly which unit operation generates the Pollutant and which generates the GHG. 
3. Coupling Analysis: Use the Archetypes above to determine how they interact with a fixed functional unit and fixed emission intensities. Never classify relationships purely by throughput or scale effects. Never infer relationships based on hypothetical optimizations, management measures, or scenario changes.
"""

        # 2. 构造 User Input（将全部提示合并到 user 消息中）
        batch_flows_str = json.dumps(batch_flows, indent=2)
        user_msg_content = f"""{core_prompt.strip()}

# Context Data
{process_context}

# Target GHGs
{ghg_list_str}

# Target Output Flows (Batch)
{batch_flows_str}

# Instruction
Analyze the relationship between the Target Flows and GHGs. 
Call `submit_final_analysis` when done.
"""
        messages: List[Dict[str, Any]] = [
            {"role": "user", "content": user_msg_content},
        ]

        # 单轮对话：模型要么调用工具，要么直接给出 JSON
        try:
            response = self._chat(messages=messages, tools=tools)
            assistant_msg = response.choices[0].message

            if assistant_msg.tool_calls:
                for tool_call in assistant_msg.tool_calls:
                    tool_name = tool_call.function.name
                    try:
                        tool_args = json.loads(tool_call.function.arguments or "{}")
                    except json.JSONDecodeError:
                        tool_args = {}

                    if tool_name == "submit_final_analysis":
                        print("    [Result] Batch analysis submitted.")
                        if isinstance(tool_args, dict):
                            return tool_args.get("flow_analyses", []) or []
                        return []

            # 如果模型没有使用工具，尝试从文本解析 JSON
            content = assistant_msg.content or ""
            if content:
                try:
                    parsed = json.loads(content)
                    if isinstance(parsed, dict):
                        return parsed.get("flow_analyses", []) or []
                except json.JSONDecodeError:
                    logging.warning("Assistant response was not valid JSON; returning empty result.")
            return []

        except Exception as e:
            logging.error(f"Error during batch analysis: {e}")
            return []

    def analyze_process(
        self,
        process_id: str,
        process_data: Dict[str, Any],
        exchange_map: Dict[str, List[Dict[str, Any]]],
        target_flows: List[Dict],
        ghg_list_str: str,
        relevant_ghgs: List[str],
    ) -> Dict:
        """
        主入口：处理数据，分批调用，合并结果。
        """
        print(f"[*] Starting Analysis for Process: {process_id}")
        
        # 1. 预处理 Context 
        # 将 Process Info 提取出来，避免在每个 Batch 里重复太长的无关信息
        # 这里直接使用传入的 content，假设调用者已经做好了瘦身
        
        # 2. 分批策略 - 默认 8 个 flow，避免 prompt 过大
        BATCH_SIZE = self.batch_size
        all_analyses = []
        
        total_batches = (len(target_flows) + BATCH_SIZE - 1) // BATCH_SIZE
        
        for i in range(0, len(target_flows), BATCH_SIZE):
            batch_id = (i // BATCH_SIZE) + 1
            batch_flows = target_flows[i : i + BATCH_SIZE]
            print(f"[-] Processing Batch {batch_id}/{total_batches} ({len(batch_flows)} flows)")
            
            # 为当前批次构建瘦身后的上下文，降低超时风险
            process_context = self._build_batch_context(
                process_data=process_data,
                exchange_map=exchange_map,
                batch_flows=batch_flows,
                relevant_ghgs=relevant_ghgs,
            )

            # 运行该批次
            batch_results = self._run_batch_analysis(process_context, batch_flows, ghg_list_str)
            all_analyses.extend(batch_results)

        # 3. 构造最终符合原始格式的返回
        final_structure = {
            "flow_analyses": all_analyses
        }
        
        completion_msg = f"[+] Analysis complete for {process_id}. Total flows analyzed: {len(all_analyses)}"
        print(completion_msg)
        logging.info(completion_msg)
        return final_structure
