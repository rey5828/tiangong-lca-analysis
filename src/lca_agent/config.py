import os
from pathlib import Path

# --- 核心配置 ---

# 使用环境变量获取API密钥，这比硬编码更安全。
# 在运行脚本前，请设置环境变量 OPENAI_API_KEY
# 如果没有设置，它会使用 "YOUR_API_KEY_HERE" 作为备用
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
OPENAI_BASE_URL = "https://api.openai.com/v1"

MODELS_TO_RUN = [
    #"anthropic/claude-sonnet-4", 
    #"deepseek/deepseek-r1-0528",
    #"qwen/qwen3-235b-a22b-thinking-2507",
    #"deepseek/deepseek-r1-0528:free",
    #"google/gemini-2.5-pro", 
    #"google/gemini-3-pro-preview",
    #"openai/o3-mini-high",
    "gpt-5-mini-2025-08-07",
    #"gpt-5.1-2025-11-13",
]


# --- 路径配置 ---

# 获取项目的根目录 (即 config.py 所在的目录的上一级)
# Path(__file__) 获取当前文件路径
# .resolve() 获取绝对路径
# .parent 获取父目录
# 假设结构是 project_root/config.py, 那么 ROOT_DIR 就是 project_root
ROOT_DIR = Path(__file__).resolve().parents[2] # 获取上两级目录

# 定义数据和结果目录的路径
DATA_DIR = ROOT_DIR / "data"
RESULTS_DIR = ROOT_DIR / "output" / "agent_results"
RESULTS_JSON_DIR = RESULTS_DIR / "individual_jsons"

# 确保结果目录存在
RESULTS_DIR.mkdir(parents=True, exist_ok=True)
RESULTS_JSON_DIR.mkdir(parents=True, exist_ok=True)

# --- 输入文件路径 ---

# 1. 单元过程ID列表
PROCESS_LIST_PATH = DATA_DIR / "jsons" / "process_list.json"

# 2. 存放所有单元过程JSON文件的目录
PROCESS_JSONS_DIR = DATA_DIR / "process_compressed"

# 3. 温室气体名单
GHG_LIST_PATH = DATA_DIR / "jsons" / "ghgs_combo.json"

# 4. 待分析的Flows列表
FLOWS_TO_ANALYZE_PATH = DATA_DIR / "jsons" / "flows_to_analyze_combo.json"


# --- 输出文件路径 ---

# MASTER_RESULTS_PATH = RESULTS_DIR / "master_results.json"