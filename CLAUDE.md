# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```powershell
# Install dependencies
pip install -r requirements.txt

# CLI interactive mode
.venv\Scripts\python.exe app/main.py

# Web UI mode (FastAPI + SSE streaming, default port 8000)
.venv\Scripts\python.exe app/main.py --web --port 8000

# Unit tests (no LLM calls required)
.venv\Scripts\python.exe -m unittest test.test_baseline
.venv\Scripts\python.exe -m unittest test.test_advanced

# Batch test (requires questions.json at project root)
.venv\Scripts\python.exe -m test.batch_test
```

## Setup

Set `ZAI_API_KEY` in `configs/.env` (智谱 GLM-4-Flash API key). This file is not committed.

`app/db/schema.py` has `DB_PATH` hardcoded to an absolute Windows path. Update it if the project is moved.

## Architecture

SQLark is a natural-language-to-SQL agent for stock market data, built on **LangGraph** with a compiled `StateGraph`.

### Request flow

The graph has two execution paths. The primary path is a **ReAct-style loop**; the legacy SQL path is a fallback.

```
intent_node → route_after_intent
  ├─ chitchat → chitchat_node → summarize_node
  └─ (else) → planner_node → tool_selector_node → tool_executor_node
                                                        ↓
                                                 observation_node → decision_node
                                                   ├─ query_ok / analysis_ok → summarize_node
                                                   ├─ error (retry < MAX) → tool_selector_node (loop)
                                                   └─ error (retry = MAX) → sql_generate_node
                                                                                ↓
                                                              sql_execute_node → sql_validate_node
                                                                ├─ retry (up to 3×) → sql_execute_node (loop)
                                                                ├─ query_ok → analysis_dispatch
                                                                │     ├─ query_done → summarize_node
                                                                │     ├─ basic_analysis → analysis_node
                                                                │     ├─ pattern_analysis → pattern_node
                                                                │     ├─ volume_price_analysis → volume_price_node
                                                                │     └─ volatility_analysis → volatility_node
                                                                └─ fail/empty → summarize_node
```

### State (`AgentState` TypedDict — `app/graph/state.py`)

Single dict passed between all nodes. Key fields: `question`, `intent`, `plan`, `sql`, `query_result`, `retry_count`, `status`, `summary`, `analysis_result`/`pattern_result`/`quant_result`. ReAct fields: `tool_name`, `tool_args`, `tool_result`, `tool_history`, `thoughts`, `observations`, `decision`.

### Intent recognition (`app/graph/nodes.py`)

`intent_node` uses LLM tool calling with six Pydantic tool schemas (`QueryRawStockData`, `QueryAggregateStockData`, `PythonDataAnalysis`, `PatternAnalysis`, `VolumePriceAnalysis`, `VolatilityAnalysis`). Falls back through two intermediate strategies (parse raw JSON, extract Markdown SQL block) before a final `_rule_based_intent` regex fallback.

After intent, `planner_node` generates a structured `plan` dict (intent, field, analysis_type, execution_mode, limit). `tool_selector_node` then picks the concrete tool and args; `tool_executor_node` runs it with a 20-second timeout; `observation_node` maps results back to state; `decision_node` decides whether to summarize, retry tool selection, or fall through to the SQL path.

### SQL safety (`app/tools/sql_executor.py`)

All SQL passes `_validate_sql` before execution: only `SELECT` statements allowed, no multi-statement batches, blocklist of mutation keywords. `safe_execute` returns `{"ok": bool, ...}` for raw queries; `safe_execute_aggregate` for aggregate queries returning `stats`.

### Tool caching (`app/utils/cache.py`)

In-memory TTL cache for stable tools only: `SchemaTool` (5 min), `MarketQuoteTool`/`NewsSentimentTool`/`ExternalApiTool` (1 min). SQL query tools are never cached. `tool_executor_node` checks and populates this cache automatically.

### Data source plugins (`app/tools/data_source.py`)

`DataSourcePlugin` ABC with three implementations: `SQLiteDataSourcePlugin` (default, routes to `safe_execute`/`safe_execute_aggregate`), `MarketQuotePlugin` (mock external quotes), `NewsSentimentPlugin` (mock sentiment). Register new sources in `get_default_data_sources()`.

### Configuration (`configs/`)

All prompts (`prompts.yaml`), intent keywords (`semantic.yaml`), and NL2SQL few-shot examples (`examples.yaml`) are YAML-driven, loaded at module import time via `app/config/config.py`. Edit YAML to tune behavior without touching Python.

### LLM singleton (`app/llm/llm.py`)

`get_llm()` returns a module-level singleton `ChatOpenAI` pointing at `https://open.bigmodel.cn/api/paas/v4/` with `glm-4-flash`. `invoke_llm(system, human)` is the convenience wrapper; `invoke_with_tools(system, human, tools)` returns `(content, tool_calls)`.

### Web server (`app/web_server.py`)

Two endpoints:
- `POST /api/chat` — synchronous, returns final serialized state
- `POST /api/stream` — SSE, streams each LangGraph node's output as it completes; frontend is `static/index.html`

## Coding Guidelines

### 1. Think Before Coding

Before implementing: state assumptions explicitly, ask if uncertain. If multiple interpretations exist, present them — don't pick silently. If a simpler approach exists, say so. If something is unclear, stop and ask.

### 2. Simplicity First

Minimum code that solves the problem. No features beyond what was asked, no abstractions for single-use code, no unrequested "flexibility". If you write 200 lines and it could be 50, rewrite it.

### 3. Surgical Changes

Touch only what you must. Don't improve adjacent code, comments, or formatting. Match existing style. Remove imports/variables/functions that YOUR changes made unused — don't remove pre-existing dead code unless asked.

### 4. Goal-Driven Execution

Transform tasks into verifiable goals. For multi-step tasks, state a brief plan:
```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
```
Clarifying questions come before implementation, not after mistakes.
