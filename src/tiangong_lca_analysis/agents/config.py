import os
from pathlib import Path

def _parse_base_urls(raw_value: str) -> list[str]:
    urls = [item.strip().rstrip("/") for item in raw_value.split(",") if item.strip()]
    return urls or ["http://192.168.1.148:7730/v1"]


# --- 核心配置 ---

MODEL_NAME = os.getenv("MODEL_NAME", "Qwen/Qwen3.5-397B-A17B-GPTQ-Int4")
MODELHUB_API_KEY = os.getenv("MODELHUB_API_KEY", "EMPTY")
MODELHUB_BASE_URLS = _parse_base_urls(
    os.getenv(
        "MODELHUB_BASE_URLS",
        "http://192.168.1.148:7730/v1,http://192.168.1.143:7730/v1",
    )
)
MODELS_TO_RUN = [MODEL_NAME]

MODEL_TEMPERATURE = float(os.getenv("MODEL_TEMPERATURE", "0.1"))
MAX_GHGS_PER_CALL = int(os.getenv("MAX_GHGS_PER_CALL", "5"))
MAX_CHUNK_RETRIES = int(os.getenv("MAX_CHUNK_RETRIES", "5"))
MODEL_TIMEOUT_SECONDS = int(os.getenv("MODEL_TIMEOUT_SECONDS", "180"))
DEFAULT_LCA_MAX_WORKERS = int(os.getenv("LCA_MAX_WORKERS", "8"))
MAX_CONCURRENT_FLOWS_PER_PROCESS = int(os.getenv("MAX_CONCURRENT_FLOWS_PER_PROCESS", "2"))
MAX_IN_FLIGHT_MODEL_REQUESTS = int(
    os.getenv("MAX_IN_FLIGHT_MODEL_REQUESTS", str(DEFAULT_LCA_MAX_WORKERS))
)


# --- 路径配置 ---

# 获取项目的根目录 (即仓库根目录)
# Path(__file__) 获取当前文件路径
# .resolve() 获取绝对路径
# .parent 获取父目录
# 当前文件位于 src/tiangong_lca_analysis/agents/config.py，向上三级回到仓库根目录
ROOT_DIR = Path(__file__).resolve().parents[3]

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
