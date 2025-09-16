"""
LCA Agent Package - 生命周期评估分析智能体

这个包提供了对工业过程进行生命周期评估分析的工具，
特别关注其温室气体排放与特定元素流之间的关系。
"""

# 导出关键模块，使它们可以通过 lca_agent.xxx 直接访问
from . import config
from . import data_fetcher
from . import lca_analyst

# 可以选择性地导出一些常用的函数或类，使其可以直接导入
# 例如：from lca_agent import LCAAnalystAgent
from .lca_analyst import LCAAnalystAgent
from .data_fetcher import load_static_data, fetch_data_for_process

# 版本信息
__version__ = "0.1.0"