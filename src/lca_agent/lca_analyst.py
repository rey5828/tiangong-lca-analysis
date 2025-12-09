import json
import logging
import os
from typing import List, Dict

import requests
from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI

# 使用相对导入从同一目录导入config
from . import config  # 导入配置以获取API密钥


class MyGoogleSearchWrapper:
    """Simple Google Custom Search client that respects proxy/timeout."""

    def __init__(self, api_key: str, cse_id: str, timeout: int = 15):
        if not api_key or not cse_id:
            raise ValueError("Google API key and CSE ID are required.")
        self.api_key = api_key
        self.cse_id = cse_id
        self.timeout = timeout

    def results(self, query: str, num_results: int = 10) -> List[Dict]:
        query = (query or "").strip()
        if not query:
            return []

        params = {
            "key": self.api_key,
            "cx": self.cse_id,
            "q": query,
            "num": max(1, min(num_results, 10)),
        }
        url = "https://www.googleapis.com/customsearch/v1"
        response = requests.get(url, params=params, timeout=self.timeout)
        response.raise_for_status()
        return response.json().get("items", [])



class LCAAnalystAgent:
    """
    自主迭代式 LCA 分析智能体。
    具备 Google 搜索能力，利用 ReAct 模式和工业机理原型进行碳污关系分析。
    """
    def __init__(self, model_name: str):
        if not config.OPENAI_API_KEY:
            raise ValueError("OpenAI API key is not set.")
        
        # 1. 初始化 LLM
        self.llm = ChatOpenAI(
            model=model_name,
            #temperature=0,  # 保持逻辑严密性
            openai_api_key=config.OPENAI_API_KEY,
            openai_api_base=config.OPENAI_BASE_URL
        )
        self.model_name = model_name
        
        # 2. 初始化 Google Search Tool
        self.google_search_tool = self._init_google_search_tool()

        print(f"[*] LCA Agent initialized with model: {self.model_name} and Google Search.")

    def _init_google_search_tool(self):
        """配置 Google Custom Search 并封装为 LangChain Tool。"""
        google_api_key = os.getenv("GOOGLE_API_KEY")
        google_cse_id = os.getenv("GOOGLE_CSE_ID") or os.getenv("GOOGLE_CX")

        if not google_api_key or not google_cse_id:
            raise ValueError("GOOGLE_API_KEY and GOOGLE_CSE_ID (or GOOGLE_CX) must be set for Google Search.")

        self._google_search_wrapper = MyGoogleSearchWrapper(
            api_key=google_api_key,
            cse_id=google_cse_id,
        )

        @tool("google_search")
        def google_search(query: str) -> str:
            """Search external sources for mechanistic or process details. Always return title + snippet."""
            query = (query or "").strip()
            if not query:
                return "Search Error: query is empty."

            logging.info("[Search] Query: %s", query)
            try:
                results = self._google_search_wrapper.results(query, num_results=10)
            except Exception as exc:
                logging.error("Google Search failed: %s", exc)
                return f"Search Error: {exc}"

            if not results:
                logging.info("[Search] Completed with 0 results.")
                return "No results found."

            logging.info("[Search] Completed successfully with %d results.", len(results))
            combined_snippets = []
            for idx, item in enumerate(results, start=1):
                title = item.get("title") or "Untitled Result"
                snippet = item.get("snippet") or item.get("description") or "No snippet available."
                combined_snippets.append(f"{idx}. {title}: {snippet}")

            return "\n".join(combined_snippets)

        return google_search

    def _build_system_prompt(self) -> str:
        """
        构建核心 System Prompt，包含思维链引导和工业逻辑原型。
        """
        return """You are a world-class expert in Industrial Ecology, with deep specialization in industrial processes and greenhouse gas emission mechanisms.

# Goal
Determine the mechanistic relationship between specific Pollutants and each Greenhouse Gase (GHG) in an industrial unit process.

# The Mechanism Framework (Archetypes)
When analyzing the relationship, you MUST map it to one of these 4 archetypes:
1. Shared Driver (Positive): Both originate from the same chemical reaction or fuel source (e.g., Combustion generates CO2 and releases Mercury from coal).
2. Trade-off (Negative): Abatement of the pollutant consumes energy/chemicals, generating GHGs (e.g., Scrubber removes SO2 but uses electricity -> Indirect CO2).
3. Efficiency Synergy (Positive): Process efficiency improvements reduce both the pollutant and GHGs simultaneously.
4. Decoupled (Neutral): The pollutant and GHG originate from completely unrelated sub-processes (e.g., Noise vs Combustion CO2).

# Reasoning Process (Chain of Thought)
You must follow this sequence internally for EACH flow:
1. Process Decomposition: Break the technology description into unit operations (e.g., combustion, Reaction, Separation).
2. Source Mapping: Pinpoint exactly which unit operation generates the Pollutant and which generates the GHG.
3. Coupling Analysis: Use the Archetypes above to determine how they interact.
Assume total process output is fixed; never classify relationships purely by throughput or scale effects.

# Tool Use Protocol
- Check Knowledge: Validate whether the provided context already proves the mechanistic link.
- Search: If you cannot cite the exact coupling mechanism or energy penalty from the context, you MUST call `google_search` with a targeted query before finalizing.
- Submit: Only when every flow has a defensible archetype assignment, call `submit_final_analysis`.
"""

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

    def _run_batch_analysis(self, process_context: str, batch_flows: List[Dict], ghg_list_str: str, max_iterations: int = 5) -> List[Dict]:
        """
        运行单个批次的 ReAct 循环。
        """
        # 1. 准备工具
        final_tool_schema = self._define_final_schema()
        # 绑定 Google 搜索和 结果提交工具
        llm_with_tools = self.llm.bind_tools([self.google_search_tool, final_tool_schema])

        # 2. 构造 User Input
        batch_flows_str = json.dumps(batch_flows, indent=2)
        user_msg_content = f"""
# Context Data
{process_context}

# Target GHGs
{ghg_list_str}

# Target Output Flows (Batch)
{batch_flows_str}

# Instruction
Analyze the relationship between the Target Flows and GHGs. 
Use `google_search` if you need external verification of chemical mechanisms.
Call `submit_final_analysis` when done.
"""
        messages = [
            SystemMessage(content=self._build_system_prompt()),
            HumanMessage(content=user_msg_content)
        ]

        # 3. 智能体迭代循环
        current_iter = 0
        while current_iter < max_iterations:
            current_iter += 1
            print(f"    [Loop] Iteration {current_iter}/{max_iterations}")

            try:
                # 调用 LLM
                ai_msg = llm_with_tools.invoke(messages)
                messages.append(ai_msg)

                # 检查工具调用
                if ai_msg.tool_calls:
                    for tool_call in ai_msg.tool_calls:
                        tool_name = tool_call["name"]
                        tool_args = tool_call["args"]

                        # A. 提交结果 (退出循环)
                        if tool_name == "submit_final_analysis":
                            print(f"    [Result] Batch analysis submitted.")
                            return tool_args.get("flow_analyses", [])

                        # B. Google 搜索 (继续循环)
                        elif tool_name == "google_search":
                            query_payload = tool_args if isinstance(tool_args, dict) else {"query": tool_args}
                            print(f"    [Search] Query: {query_payload.get('query')}")
                            search_res = self.google_search_tool.invoke(query_payload)

                            # 将搜索结果反馈给 LLM
                            messages.append(ToolMessage(content=search_res, tool_call_id=tool_call["id"]))
                
                else:
                    # 如果没有调用工具，可能是 LLM 正在进行中间推理 (Thought)，不做操作，继续下一轮
                    pass

            except Exception as e:
                logging.error(f"Error in batch loop: {e}")
                break
        
        # 如果超过最大迭代次数仍未提交，返回空或尝试解析最后的消息（此处简单返回空）
        print("    [Warn] Max iterations reached without submission.")
        return []

    def analyze_process(self, process_id: str, process_json_content: str, target_flows: List[Dict], ghg_list_str: str) -> Dict:
        """
        主入口：处理数据，分批调用，合并结果。
        """
        print(f"[*] Starting Analysis for Process: {process_id}")
        
        # 1. 预处理 Context (假设传入的 process_json_content 已经是瘦身版)
        # 将 Process Info 提取出来，避免在每个 Batch 里重复太长的无关信息
        # 这里直接使用传入的 content，假设调用者已经做好了瘦身
        
        # 2. 分批策略 (Batching Strategy) - 10 Flows per Batch
        BATCH_SIZE = 10
        all_analyses = []
        
        total_batches = (len(target_flows) + BATCH_SIZE - 1) // BATCH_SIZE
        
        for i in range(0, len(target_flows), BATCH_SIZE):
            batch_id = (i // BATCH_SIZE) + 1
            batch_flows = target_flows[i : i + BATCH_SIZE]
            print(f"[-] Processing Batch {batch_id}/{total_batches} ({len(batch_flows)} flows)")
            
            # 运行该批次
            batch_results = self._run_batch_analysis(process_json_content, batch_flows, ghg_list_str)
            all_analyses.extend(batch_results)

        # 3. 构造最终符合原始格式的返回
        final_structure = {
            "flow_analyses": all_analyses
        }
        
        completion_msg = f"[+] Analysis complete for {process_id}. Total flows analyzed: {len(all_analyses)}"
        print(completion_msg)
        logging.info(completion_msg)
        return final_structure
