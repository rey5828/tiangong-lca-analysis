
# TianGong LCA Analysis 

## Env Preparing

### Using VSCode Dev Contariners

[Tutorial](https://code.visualstudio.com/docs/devcontainers/tutorial)

Python 3 -> Additional Options -> 3.12-bullseye -> ZSH Plugins (Last One) -> Trust @devcontainers-contrib -> Keep Defaults

Setup `venv`:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
```

Install requirements:

```bash
pip install --upgrade pip
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
pip install -r requirements.txt --upgrade

pip freeze > requirements_freeze.txt
```

### API Keys

- OpenAI models（例如 `gpt-*`）：设置环境变量 `OPENAI_API_KEY`
- OpenRouter models（例如 `google/gemini-*`）：设置环境变量 `OPENROUTER_API_KEY`
- 如需启用 Google 搜索工具：设置 `GOOGLE_API_KEY` 与 `GOOGLE_CSE_ID`（或 `GOOGLE_CX`）

```bash
sudo apt install python3.12-dev
```

## Project layout

- `docs/`：整理后的笔记与校验报告（`notes/`、`reports/`）。
- `scripts/`：一次性或辅助脚本（例如 `check_flow_counts.py`）。
- `src/tiangong_lca_analysis/`：核心代码包，入口为 `cli.py`（从仓库根目录运行时确保 `PYTHONPATH=src python -m tiangong_lca_analysis.cli`）。
  - `agents/`：LCA 智能体与配置。
  - `workflows/`：数据准备、过滤、合并等流程脚本。
  - `tooling/`：Elasticsearch 及数据处理小工具。
  - `analysis/`：概率分析等模型结果研究脚本。
  - `reporting/`：结果合并、对比与可视化。
  - `validation/`：索引/数据一致性校验工具。
- `data/`、`output/`、`logs/` 等按 `.gitignore` 保持原路径，只移动不改内容。

### Auto Build

The auto build will be triggered by pushing any tag named like release-v$version. For instance, push a tag named as v0.0.1 will build a docker image of 0.0.1 version.

```bash
#list existing tags
git tag
#creat a new tag
git tag v0.0.1
#push this tag to origin
git push origin v0.0.1
```
