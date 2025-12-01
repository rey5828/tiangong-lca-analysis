import json
import logging
from typing import List, Dict, Optional, Any

from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

# 使用相对导入从同一目录导入config
from . import config  # 导入配置以获取API密钥



class LCAAnalystAgent:
    """
    负责与大语言模型交互，执行核心分析任务的Agent。
    使用LangChain框架和结构化输出。
    """
    def __init__(self, model_name: str):
        """
        初始化Agent,设置LangChain模型并连接到OpenAI/OpenRouter
        """
        if not config.OPENAI_API_KEY:
            raise ValueError("OpenAI API key is not set. Please set the OPENAI_API_KEY environment variable.")
        
        # 初始化LangChain的ChatOpenAI模型,并指向OpenAI/OpenRouter
        self.llm = ChatOpenAI(
            model=model_name,
            #temperature=0.1,  # 较低的温度以获得更稳定的输出
            openai_api_key=config.OPENAI_API_KEY,
            openai_api_base=config.OPENAI_BASE_URL
        )
        
        self.model_name = model_name
        print(f"[*] LCA Analyst Agent initialized with model: {self.model_name}")

    def _build_prompt(self, process_json_content: str, target_flows: List[Dict], ghg_list_str: str) -> str:
        """
        一个私有方法，用于构建最终发送给LLM的完整Prompt。
        """
        # 使用json.dumps美化target_flows列表，使其在Prompt中更易读
        flows_to_analyze_str = json.dumps(target_flows, indent=2)

        # 转义 JSON 中的花括号，将 { 替换为 {{ 并将 } 替换为 }}
        process_json_content = process_json_content.replace("{", "{{").replace("}", "}}")
        flows_to_analyze_str = flows_to_analyze_str.replace("{", "{{").replace("}", "}}")

        # 完整Prompt模板
        prompt_template = f"""
# Task and Context
Analyze an ecoinvent unit process to determine the relationship between its specific output elementary flows and its total Greenhouse Gas (GHG) emissions.
# Context
1.  Unit Process for Analysis: The process is described in the following JSON data. Pay close attention to the `name`, `description`, `technologyDescription`, and `samplingDescription` fields to understand its nature.
    {process_json_content}
2.  Greenhouse Gas (GHG) Definition: For this analysis, GHG emissions are defined as the set of elementary flows listed below. Treat any emission of these flows as contributing to total GHG emissions:
    {ghg_list_str}
3.  Target Output Flows: You must focus your analysis ONLY on the following output elementary flows from the process. Do not analyze any other flows:
    {flows_to_analyze_str}
# Task & Instructions
Each entry in the target list provides a canonical `flow_combo` string (`flow_name | flow_category`). Treat this `flow_combo` as the unique identifier for the flow and include it verbatim in your output. Each greenhouse gas listed above is also provided as a canonical `ghg_combo` string with the same structure—use that exact combo when referring to individual GHGs. For EACH elementary flow, perform the following analysis:
Qualitative Relationship Analysis
- Question: Assuming the production output of the main product is held constant, based on the process mechanism and operating conditions (e.g., combustion efficiency, reaction pathways, treatment technology), what is the qualitative relationship between the emission of this target flow and the emission of GHGs?
- Answer Format: Provide one of the following keywords:
 - `Positive`: The target flow and GHG emissions tend to increase or decrease together under the same process conditions.
 - `Negative`: The target flow and GHG emissions tend to vary in opposite directions under the same process conditions (e.g., a change that reduces GHG emissions typically increases this flow, or vice versa).
 - `Neutral`: There is no clear or consistent relationship between this flow and GHG emissions. Their variation appears independent or too uncertain to establish a directional link.
- Reasoning: Briefly explain the underlying physical, chemical, or operational mechanism for the relationship, or the lack thereof.
# Output Format
Do not include any text or keys outside of this JSON object. You MUST provide an analysis object in the `flow_analyses` array for EVERY SINGLE flow listed in the 'Target Output Flows' section above. Do not omit any flows.
"""
        return prompt_template


    def analyze_process(self, process_id: str, process_json_content: str, target_flows: List[Dict], ghg_list_str: str) -> Optional[Dict]:
        """
        执行对单个单元过程的分析。

        Args:
            process_id: 当前正在分析的过程ID（主要用于日志记录）。
            process_json_content: 过程的JSON内容字符串。
            target_flows: 此过程待分析的flows列表。
            ghg_list_str: 格式化好的GHG列表字符串。

        Returns:
            LLM返回的结构化字典对象，如果发生错误则返回None。
        """
        print(f"[*] Building prompt and analyzing process: {process_id}")
        
      
        prompt_content = self._build_prompt(process_json_content, target_flows, ghg_list_str)
        
     
        system_prompt = f"""You are a world-class expert in Life Cycle Assessment and industrial ecology, with deep specialization in industrial processes and greenhouse gas emission mechanisms."""
        
       
        json_schema = {
            "title": "Analysis_Result",
            "description": "Analysis of elementary flows for a given process.",
            "type": "object",
            "properties": {
                "flow_analyses": {
                    "type": "array",
                    "description": "A list of analysis results for each target flow.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "flow_combo": {
                                "type": "string",
                                "description": "Canonical 'flow_name | flow_category' string identifying the flow."
                            },
                            "individual_ghg_analyses": {
                                "type": "array",
                                "description": "A list of analysis results for this pollutant against each individual greenhouse gas.",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "ghg_combo": {
                                            "type": "string",
                                            "description": "Canonical 'flow_name | flow_category' string identifying the greenhouse gas."
                                        },
                                        "qualitative_relationship": {
                                            "type": "string",
                                            "enum": [
                                                "Positive",
                                                "Negative",
                                                "Neutral"
                                            ]
                                        },
                                        "qualitative_reasoning": {
                                            "type": "string"
                                        },
                                        "confidence": {
                                            "type": "string",
                                            "enum": [
                                                "High",
                                                "Medium",
                                                "Low"
                                            ]
                                        },
                                        "evidence_flows": {
                                            "type": "array",
                                            "description": "List of flow names from the JSON that act as evidence.",
                                            "items": {
                                                "type": "string"
                                            }
                                        }
                                    },
                                    "required": [
                                        "ghg_combo",
                                        "qualitative_relationship",
                                        "qualitative_reasoning",
                                        "confidence",
                                        "evidence_flows"
                                    ]
                                }
                            }
                        },
                        "required": [
                            "flow_combo",
                            "individual_ghg_analyses"
                        ]
                    }
                }
            },
            "required": [
                "flow_analyses"
            ]
        }
        
        prompt_template = ChatPromptTemplate.from_messages([
            ("system", system_prompt),
            ("user", prompt_content)
        ])
        
        # 使用带结构化输出的LLM
        structured_llm = self.llm.with_structured_output(json_schema)
        
        try:
            # 执行提示并获取结构化输出
            chain = prompt_template | structured_llm
            response = chain.invoke({})
            
            # 直接返回结构化对象，而不是转换为字符串
            print(f"[+] Successfully received analysis from LLM for {process_id}.")
            return response
            
        except Exception as e:
            logging.error(f"[X] Error during analysis of {process_id}: {e}", exc_info=True)
            return None
