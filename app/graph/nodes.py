"""LangGraph 图节点函数：意图识别、SQL 生成、执行、分析、总结。"""

from __future__ import annotations

import concurrent.futures as _cf
import json
import re
import time as _time
from datetime import datetime, timedelta
from typing import Optional

from app.utils import cache as _cache
from app.utils.logger import log_decision as _log_decision, log_tool_call as _log_tool_call

from pydantic import BaseModel, Field

from app.config.config import load_examples_config, load_prompts_config, load_semantic_config
from app.db.schema import get_schema_text
from app.graph.state import MAX_RETRY_COUNT, AgentState, IntentType
from app.llm.llm import get_llm, invoke_llm, invoke_with_tools
from app.tools.agent_tools import (
    build_langchain_tools,
    get_default_tools,
    get_tool_by_name,
)
from app.tools.quant_analysis import run_analysis, run_volatility_analysis, run_volume_price_analysis
from app.tools.pattern import run_pattern_analysis
from app.tools.sql_executor import safe_execute, safe_execute_aggregate

# ==================== 配置加载 ====================

_SEMANTIC_CONFIG = load_semantic_config()
_PROMPTS_CONFIG = load_prompts_config()
_EXAMPLES = load_examples_config()

TOOL_TIMEOUT_SECONDS = 20

ALLOWED_ANALYSIS_TYPES = {"basic", "volatility", "trend", "anomaly", "count", "comparison", "pattern", "volume_price"}
ALLOWED_INTENTS = {e.value for e in IntentType}

DEFAULT_LIMIT = _SEMANTIC_CONFIG["defaults"]["limit"]
MAX_LIMIT = _SEMANTIC_CONFIG["defaults"]["max_limit"]
DEFAULT_FIELD = _SEMANTIC_CONFIG["defaults"]["field"]
DEFAULT_ANALYSIS_TYPE = _SEMANTIC_CONFIG["defaults"]["analysis_type"]
DEFAULT_INTENT = _SEMANTIC_CONFIG["defaults"]["intent"]


# ==================== Agent 工具 Schema ====================

class QueryRawStockData(BaseModel):
    """用于查询股票的原始明细数据，按时间排序。严禁在此技能中使用任何聚合函数。"""
    sql_query: str = Field(..., description="必须包含 LIMIT 限制的 SQLite 语句。只查明细。")


class QueryAggregateStockData(BaseModel):
    """用于计算股票数据的统计指标。只能使用 COUNT, AVG, MAX, MIN 等简单聚合函数。"""
    sql_query: str = Field(..., description="包含聚合函数的 SQLite 语句。")


class PythonDataAnalysis(BaseModel):
    """当用户需要分析趋势、波动率、极值差异或异常情况时使用。先用SQL拉取原始数据，后交由Python运算。"""
    sql_query: str = Field(..., description="用于提取原始数据的 SQLite 语句（严禁使用聚合函数）。")
    analysis_type: str = Field(..., description="分析类型：trend/volatility/anomaly/comparison/basic")
    target_field: str = Field(..., description="优先分析的字段名（如 LatestPrice, Volume, Turnover）")


class PatternAnalysis(BaseModel):
    """当用户需要分析K线形态、均线交叉、支撑压力位等价格形态特征时使用。"""
    sql_query: str = Field(..., description="用于提取 OHLC + Volume 数据的 SQLite 语句。")


class VolumePriceAnalysis(BaseModel):
    """当用户需要分析量价关系（量价背离、放量突破、OBV等）时使用。"""
    sql_query: str = Field(..., description="用于提取价格和成交量数据的 SQLite 语句。")


class VolatilityAnalysis(BaseModel):
    """当用户需要分析波动率、最大回撤、VaR、ATR等统计特征时使用。"""
    sql_query: str = Field(..., description="用于提取价格数据用于波动率计算的 SQLite 语句。")


# ==================== 时间解析 ====================

def _parse_time_range(question: str) -> Optional[dict]:
    """解析问题中的时间范围。"""
    from app.tools.sql_executor import get_latest_trade_time

    latest = get_latest_trade_time()
    if not latest:
        return None

    try:
        latest_dt = datetime.strptime(latest, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None

    base_day = latest_dt.replace(hour=0, minute=0, second=0, microsecond=0)
    q = question.strip()

    day_offsets = {
        "前天": 2, "前3天": 3, "前三天": 3,
        "最近3天": 3, "最近三天": 3,
        "最近5天": 5, "最近五天": 5, "过去5天": 5, "过去五天": 5,
        "最近7天": 7, "最近一周": 7, "最近1周": 7,
        "过去7天": 7, "过去一周": 7, "最近30天": 30, "最近一个月": 30,
    }

    for keyword, days in day_offsets.items():
        if keyword in q:
            start = base_day - timedelta(days=days)
            return {"start": start, "end": base_day, "granularity": "day", "keyword": keyword}

    if any(word in q for word in ["今天", "今日"]):
        return {"start": base_day, "end": latest_dt + timedelta(seconds=1), "granularity": "day", "keyword": "today"}

    if "最新" in q or "最近一条" in q or "最新一条" in q:
        return {"start": latest_dt - timedelta(days=1), "end": latest_dt + timedelta(seconds=1), "granularity": "latest", "keyword": "latest"}

    if "昨" in q:
        return {"start": base_day - timedelta(days=1), "end": base_day, "granularity": "day", "keyword": "yesterday"}

    return None


# ==================== 规则兜底意图识别 ====================

def _rule_based_intent(question: str) -> str:
    """基于规则的意图识别兜底。"""
    q = question.strip()

    # 闲聊/问候检测（优先级最高）
    chitchat_keywords = [
        "你好", "您好", "hi", "hello", "hey", "嗨", "哈喽",
        "谢谢", "感谢", "thanks", "thank you",
        "再见", "拜拜", "bye",
        "你是谁", "你叫什么", "你是啥", "自我介绍",
        "早上好", "下午好", "晚上好", "早安", "晚安",
    ]
    if any(q.lower() == kw or q.lower().startswith(kw) for kw in chitchat_keywords):
        return IntentType.CHITCHAT.value
    # 纯短句且不含任何股票相关词，也视为闲聊
    stock_keywords = ["股", "价", "量", "线", "涨", "跌", "盘", "仓", "仓", "查", "分析", "数据", "行情", "交易", "市值"]
    if len(q) <= 6 and not any(kw in q for kw in stock_keywords):
        return IntentType.CHITCHAT.value

    q_lower = q.lower()
    pattern_keywords = ["k线", "形态", "均线", "金叉", "死叉", "支撑", "压力", "缺口", "锤子", "吞没", "十字星", "启明星"]
    volume_price_keywords = ["量价", "放量", "缩量", "obv", "换手率", "量能", "背离"]
    volatility_keywords = ["波动率", "atr", "偏度", "峰度", "var", "回撤", "在险"]

    if any(kw in q_lower for kw in volatility_keywords):
        return IntentType.VOLATILITY.value
    if any(kw in q_lower for kw in volume_price_keywords):
        return IntentType.VOLUME_PRICE.value
    if any(kw in q_lower for kw in pattern_keywords):
        return IntentType.PATTERN.value

    analysis_keywords = _SEMANTIC_CONFIG["intents"].get("analysis", [])
    if any(kw in question or kw in q_lower for kw in analysis_keywords):
        return IntentType.ANALYSIS.value

    return DEFAULT_INTENT


def _rule_based_field(question: str) -> str:
    """基于规则的字段识别。"""
    q = question.lower()
    english_map = {
        "Volume": ["volume", "turnover", "amount"],
        "ChangePercent": ["change percent", "percentage", "pct"],
        "HighPrice": ["high price", "highest"],
        "LowPrice": ["low price", "lowest"],
        "LatestPrice": ["latest price", "price", "current price"],
    }
    for field, keywords in english_map.items():
        if any(kw in q for kw in keywords):
            return field

    for field, keywords in _SEMANTIC_CONFIG.get("fields", {}).items():
        if any(kw in question for kw in keywords):
            return field
    return DEFAULT_FIELD


# ==================== 节点 1：意图识别 ====================

def intent_node(state: AgentState) -> dict:
    """意图识别节点：通过 Agent Tool Calling 确定意图和 SQL。"""
    question = state["question"]

    # 解析时间范围
    time_range = _parse_time_range(question)

    # 尝试 Agent Tool Calling
    prompt_config = _PROMPTS_CONFIG.get("agent_system", "")
    system_prompt = prompt_config.format(schema_text=get_schema_text())

    llm = get_llm()
    tools = build_langchain_tools()

    try:
        content, tool_calls = invoke_with_tools(system_prompt, question, tools)
    except Exception:
        tool_calls = []
        content = ""

    # Fallback 1: 尝试从原始文本解析 tool_calls
    if not tool_calls and '"arguments":' in content:
        try:
            match_name = re.search(r'"name"\s*:\s*"([a-zA-Z0-9_]+)"', content)
            match_args = re.search(r'"arguments"\s*:\s*("(?:\\.|[^"\\])*")', content)
            if match_name and match_args:
                tool_name = match_name.group(1)
                args_str = json.loads(match_args.group(1))
                args = json.loads(args_str)
                tool_calls = [{"name": tool_name, "args": args}]
        except Exception:
            pass

    # Fallback 2: 从 Markdown SQL 代码块推断
    if not tool_calls:
        sql_match = re.search(r"```sql\s*(.*?)\s*```", content, re.IGNORECASE | re.DOTALL)
        if sql_match:
            sql_query = sql_match.group(1).strip()
            sql_upper = sql_query.upper()
            if any(func in sql_upper for func in ["COUNT(", "AVG(", "MAX(", "MIN("]):
                tool_calls = [{"name": "QueryAggregateStockData", "args": {"sql_query": sql_query}}]
            else:
                tool_calls = [{"name": "QueryRawStockData", "args": {"sql_query": sql_query}}]

    # 完全降级：规则兜底
    if not tool_calls:
        intent = _rule_based_intent(question)
        plan = _build_fallback_plan(question, intent)
        return {
            "intent": intent,
            "plan": plan,
            "sql": "-- 无法生成有效SQL",
            "time_range": time_range,
            "status": "no_sql",
            "message": f"模型未触发工具调用，使用规则兜底，意图: {intent}",
            "retry_count": 0,
        }

    # 解析 tool_calls → plan + sql
    tool_call = tool_calls[0]
    tool_name = tool_call["name"]
    args = tool_call["args"]

    intent, plan = _parse_tool_call(tool_name, args, question)

    return {
        "intent": intent,
        "plan": plan,
        "sql": args.get("sql_query", "-- 无法生成有效SQL"),
        "time_range": time_range,
        "status": "no_sql" if args.get("sql_query", "").strip().startswith("--") else "intent_ok",
        "message": "意图识别完成",
        "retry_count": 0,
    }


def _parse_tool_call(tool_name: str, args: dict, question: str) -> tuple[str, dict]:
    """将 Agent 工具调用映射为意图和计划。"""
    plan = {"limit": 20, "needs_clarification": False}

    if tool_name == "QueryRawStockData":
        return IntentType.QUERY.value, {**plan, "intent": "query", "execution_mode": None, "field": None, "analysis_type": "basic"}

    if tool_name == "QueryAggregateStockData":
        return IntentType.ANALYSIS.value, {**plan, "intent": "analysis", "execution_mode": "sql_aggregate", "field": None, "analysis_type": "basic"}

    if tool_name == "PythonDataAnalysis":
        field = args.get("target_field", _rule_based_field(question))
        return IntentType.ANALYSIS.value, {
            **plan, "intent": "analysis", "execution_mode": "python_analysis",
            "field": field, "analysis_type": args.get("analysis_type", "basic"),
        }

    if tool_name == "PatternAnalysis":
        return IntentType.PATTERN.value, {**plan, "intent": "pattern", "execution_mode": "python_analysis", "field": "LatestPrice", "analysis_type": "pattern"}

    if tool_name == "VolumePriceAnalysis":
        return IntentType.VOLUME_PRICE.value, {**plan, "intent": "volume_price", "execution_mode": "python_analysis", "field": "Volume", "analysis_type": "volume_price"}

    if tool_name == "VolatilityAnalysis":
        return IntentType.VOLATILITY.value, {**plan, "intent": "volatility", "execution_mode": "python_analysis", "field": "LatestPrice", "analysis_type": "volatility"}

    return DEFAULT_INTENT, {**plan, "intent": DEFAULT_INTENT, "execution_mode": None, "field": None, "analysis_type": "basic"}


def _build_fallback_plan(question: str, intent: str) -> dict:
    """构建规则兜底计划。"""
    if intent == IntentType.QUERY.value:
        return {"intent": "query", "field": None, "analysis_type": "basic", "execution_mode": None, "limit": DEFAULT_LIMIT, "needs_clarification": False}

    field = _rule_based_field(question) if intent != IntentType.QUERY.value else None
    analysis_type = {
        IntentType.PATTERN.value: "pattern",
        IntentType.VOLUME_PRICE.value: "volume_price",
        IntentType.VOLATILITY.value: "volatility",
    }.get(intent, "basic")

    return {
        "intent": intent, "field": field, "analysis_type": analysis_type,
        "execution_mode": "python_analysis", "limit": DEFAULT_LIMIT, "needs_clarification": False,
    }


def _parse_planner_output(content: str) -> dict | None:
    """从 LLM 规划器输出中解析 JSON 计划。"""
    if not content:
        return None
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        match = re.search(r"\{[\s\S]*\}", content)
        if not match:
            return None
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            return None


def planner_node(state: AgentState) -> dict:
    """规划节点：根据用户问题生成结构化计划。"""
    question = state.get("question", "")
    if not question:
        return {"plan": _build_fallback_plan(question, DEFAULT_INTENT), "status": "planned"}

    prompt_system = _PROMPTS_CONFIG.get("planner_system", "")
    prompt_human = _PROMPTS_CONFIG.get("planner_human", "").format(question=question)

    try:
        plan_text = invoke_llm(prompt_system, prompt_human)
        plan = _parse_planner_output(plan_text) or _build_fallback_plan(question, _rule_based_intent(question))
    except Exception:
        plan = _build_fallback_plan(question, _rule_based_intent(question))

    if not isinstance(plan, dict):
        plan = _build_fallback_plan(question, _rule_based_intent(question))

    # 保证必需字段
    plan.setdefault("intent", _rule_based_intent(question))
    plan.setdefault("field", None)
    plan.setdefault("analysis_type", DEFAULT_ANALYSIS_TYPE)
    plan.setdefault("execution_mode", None)
    plan.setdefault("limit", DEFAULT_LIMIT)
    plan.setdefault("confidence", 0.5)
    plan.setdefault("needs_clarification", False)

    return {
        "plan": plan,
        "status": "planned",
        "message": "任务规划完成",
        "thoughts": (state.get("thoughts", []) or []) + ["planner_node: 生成执行计划"],
    }


# ==================== 节点 1b：工具选择 ====================

def _parse_tool_selection_content(content: str) -> list[dict]:
    """解析模型输出中的工具调用信息。"""
    tool_calls = []
    if not content:
        return tool_calls

    if '"name"' in content and '"arguments"' in content:
        try:
            match_name = re.search(r'"name"\s*:\s*"([a-zA-Z0-9_]+)"', content)
            match_args = re.search(r'"arguments"\s*:\s*(\{[\s\S]*\})', content)
            if match_name and match_args:
                tool_name = match_name.group(1)
                args = json.loads(match_args.group(1))
                tool_calls.append({"name": tool_name, "args": args})
                return tool_calls
        except Exception:
            pass

    sql_match = re.search(r"```sql\s*(.*?)\s*```", content, re.IGNORECASE | re.DOTALL)
    if sql_match:
        sql_query = sql_match.group(1).strip()
        sql_upper = sql_query.upper()
        if any(func in sql_upper for func in ["COUNT(", "AVG(", "MAX(", "MIN("]):
            tool_calls.append({"name": "QueryAggregateStockData", "args": {"sql_query": sql_query}})
        else:
            tool_calls.append({"name": "QueryRawStockData", "args": {"sql_query": sql_query}})
    return tool_calls


def tool_selector_node(state: AgentState) -> dict:
    """选择最合适的工具并生成调用参数。"""
    question = state.get("question", "")
    plan = state.get("plan", {})
    tools = build_langchain_tools()
    system_prompt = _PROMPTS_CONFIG.get("tool_selection_system", "")
    human_prompt = _PROMPTS_CONFIG.get("tool_selection_human", "").format(
        question=question,
        plan=json.dumps(plan, ensure_ascii=False),
    )

    try:
        content, tool_calls = invoke_with_tools(system_prompt, human_prompt, tools)
    except Exception:
        content = ""
        tool_calls = []

    if not tool_calls:
        tool_calls = _parse_tool_selection_content(content)

    if not tool_calls:
        return {
            "status": "tool_selection_failed",
            "message": "工具选择失败，未生成有效工具调用",
            "tool_history": state.get("tool_history", []) or [],
            "thoughts": (state.get("thoughts", []) or []) + ["tool_selector_node: 未能识别工具调用"],
        }

    tool_call = tool_calls[0]
    return {
        "tool_name": tool_call["name"],
        "tool_args": tool_call["args"],
        "status": "tool_selected",
        "message": f"已选择工具 {tool_call['name']}",
        "tool_history": state.get("tool_history", []) or [],
        "thoughts": (state.get("thoughts", []) or []) + [f"tool_selector_node: 选择工具 {tool_call['name']}"] ,
    }


def tool_executor_node(state: AgentState) -> dict:
    """执行已选择的工具（含超时保护、结果缓存、执行计时）。"""
    tool_name = state.get("tool_name")
    tool_args = state.get("tool_args", {}) or {}
    tool_history = state.get("tool_history", []) or []

    if not tool_name:
        return {
            "status": "tool_not_found",
            "message": "未选择工具，无法执行",
            "tool_history": tool_history,
        }

    tool = get_tool_by_name(tool_name)
    if not tool:
        return {
            "status": "tool_not_found",
            "message": f"未找到工具: {tool_name}",
            "tool_history": tool_history,
        }

    # 检查缓存
    cached = _cache.get(tool_name, tool_args)
    if cached is not None:
        _log_tool_call(tool_name, tool_args, cached, 0)
        result = cached
        from_cache = True
    else:
        # 执行工具（带超时保护）
        t0 = _time.time()
        executor = _cf.ThreadPoolExecutor(max_workers=1)
        future = executor.submit(tool.execute, tool_args)
        try:
            result = future.result(timeout=TOOL_TIMEOUT_SECONDS)
        except _cf.TimeoutError:
            result = {"ok": False, "error": f"工具 {tool_name} 执行超时（>{TOOL_TIMEOUT_SECONDS}s）"}
            future.cancel()
        except Exception as exc:
            result = {"ok": False, "error": str(exc)}
        finally:
            executor.shutdown(wait=False)
        elapsed_ms = (_time.time() - t0) * 1000
        _log_tool_call(tool_name, tool_args, result, elapsed_ms)
        from_cache = False
        # 缓存成功结果
        if result.get("ok"):
            _cache.put(tool_name, tool_args, result)

    tool_history = tool_history + [{
        "tool": tool_name,
        "args": tool_args,
        "result": result,
        "from_cache": from_cache,
    }]

    return {
        "tool_result": result,
        "tool_history": tool_history,
        "status": "tool_executed",
        "message": f"工具 {tool_name} 执行完成",
        "thoughts": (state.get("thoughts", []) or []) + [f"tool_executor_node: 执行工具 {tool_name}"],
    }


def observation_node(state: AgentState) -> dict:
    """将工具执行结果映射到状态，并生成观察信息。"""
    tool_name = state.get("tool_name", "")
    tool_result = state.get("tool_result", {}) or {}
    observations = (state.get("observations", []) or [])
    observation_text = f"{tool_name} 返回 ok={tool_result.get('ok', False)}"
    if tool_result.get("error"):
        observation_text += f"，error={tool_result.get('error')}"
    observations.append(observation_text)

    if tool_name == "QueryRawStockData":
        status = "query_ok" if tool_result.get("ok") else "query_error"
        message = "原始数据查询完成" if tool_result.get("ok") else "原始数据查询失败"
        summary = None
        if tool_result.get("ok"):
            count = tool_result.get("count", 0)
            summary = f"查询成功，共返回 {count} 条数据。"
        return {
            "query_result": tool_result,
            "status": status,
            "message": message,
            "summary": summary,
            "observations": observations,
        }

    if tool_name == "QueryAggregateStockData":
        stats = tool_result.get("stats", {})
        analysis_result = {"ok": tool_result.get("ok", False), "stats": stats}
        summary = _summarize(state.get("question", ""), stats) if tool_result.get("ok") else None
        return {
            "analysis_result": analysis_result,
            "status": "analysis_ok" if tool_result.get("ok") else "analysis_error",
            "message": "聚合统计分析完成" if tool_result.get("ok") else "聚合统计分析失败",
            "summary": summary,
            "observations": observations,
        }

    if tool_name == "PythonDataAnalysis":
        summary = _quant_summarize(state.get("question", ""), tool_result) if tool_result.get("ok") else None
        return {
            "analysis_result": tool_result,
            "status": "analysis_ok" if tool_result.get("ok") else "analysis_error",
            "message": "Python 数据分析完成" if tool_result.get("ok") else "Python 数据分析失败",
            "summary": summary,
            "observations": observations,
        }

    if tool_name in {"PatternAnalysis", "VolumePriceAnalysis", "VolatilityAnalysis"}:
        result_field = "pattern_result" if tool_name == "PatternAnalysis" else "quant_result"
        actual_result = tool_result.get(result_field, {})  # 解包：去掉 ok/error 外壳
        summary = _quant_summarize(state.get("question", ""), actual_result) if tool_result.get("ok") else None
        update: dict = {
            result_field: actual_result,
            "status": "analysis_ok" if tool_result.get("ok") else "analysis_error",
            "message": "量化分析完成" if tool_result.get("ok") else "量化分析失败",
            "summary": summary,
            "observations": observations,
        }
        if tool_result.get("ok"):
            update["composite_signal"] = actual_result.get("composite_signal")
            update["backtest_result"] = actual_result.get("backtest")
        return update

    return {
        "status": "tool_error",
        "message": "工具返回结果无法映射",
        "observations": observations,
    }


def decision_node(state: AgentState) -> dict:
    """决策节点：根据当前状态选择下一步。"""
    status = state.get("status", "")
    retry_count = state.get("retry_count", 0)
    decision = "summarize"

    if status in ("query_ok", "analysis_ok"):
        decision = "summarize"
    elif status in ("tool_selection_failed", "tool_not_found", "tool_error", "analysis_error", "query_error"):
        decision = "tool_selector" if retry_count < MAX_RETRY_COUNT else "sql_generate"
    elif status == "tool_selected":
        decision = "tool_executor"
    else:
        decision = "summarize"

    _log_decision(decision, status, retry_count)

    result = {
        "decision": decision,
        "status": state.get("status"),
        "thoughts": (state.get("thoughts", []) or []) + [f"decision_node: 下一步 -> {decision}"],
    }
    if decision == "tool_selector" and status in ("tool_selection_failed", "tool_not_found", "tool_error", "analysis_error", "query_error"):
        result["retry_count"] = retry_count + 1
    return result


def route_after_decision(state: AgentState) -> str:
    """决策节点后的路由。"""
    decision = state.get("decision", "summarize")
    return decision if decision in {"summarize", "tool_selector", "sql_generate"} else "summarize"


# ==================== 节点 1b：闲聊回复 ====================

_CHITCHAT_RESPONSES = {
    "你好": "你好！我是 SQLark 量化分析智能体，可以帮你查询和分析股票数据。试试问我某只股票的行情吧！",
    "您好": "您好！我是 SQLark 量化分析智能体，有什么股票数据需要查询或分析吗？",
    "hi": "Hi！我是 SQLark 量化分析智能体，可以帮你查询股票行情、分析K线形态和量价关系。",
    "hello": "Hello！我是 SQLark 量化分析智能体，有什么股票数据需要查询吗？",
    "谢谢": "不客气！有任何股票数据问题随时问我。",
    "感谢": "不客气！有任何股票数据问题随时问我。",
    "你是谁": "我是 SQLark 量化分析智能体，专注于股票数据查询与分析。你可以用自然语言问我股票行情、K线形态、量价关系、波动率等问题。",
    "再见": "再见！有股票数据问题随时回来问我。",
}


def chitchat_node(state: AgentState) -> dict:
    """闲聊节点：对问候和日常对话返回友好回复。"""
    question = state.get("question", "").strip().lower()

    # 匹配最合适的回复
    for keyword, response in _CHITCHAT_RESPONSES.items():
        if keyword in question:
            return {"summary": response, "status": "chitchat", "intent": IntentType.CHITCHAT.value}

    # 默认闲聊回复
    return {
        "summary": "我是 SQLark 量化分析智能体，擅长股票数据查询与分析。你可以试试问我：\n• 查询宁德时代最近30条数据\n• 分析贵州茅台的K线形态特征\n• 比亚迪的量价关系如何",
        "status": "chitchat",
        "intent": IntentType.CHITCHAT.value,
    }


# ==================== 节点 2：SQL 生成（含时间范围注入） ====================

def sql_generate_node(state: AgentState) -> dict:
    """当 Agent 未通过 Tool Calling 生成 SQL 时，使用 NL2SQL 链生成。"""
    if state.get("sql", "").strip() and not state["sql"].strip().startswith("--"):
        return {}  # 已有有效 SQL，跳过

    question = state["question"]
    plan = state.get("plan", {})
    time_range = state.get("time_range")

    # 构建 extra_rule
    extra_rule = f"本次查询必须使用 LIMIT {plan.get('limit', DEFAULT_LIMIT)}。"
    if plan.get("field"):
        extra_rule += f"\n本次分析任务必须优先查询字段：{plan['field']}。"
    if plan.get("execution_mode") == "sql_aggregate":
        extra_rule += "\n本次任务允许使用简单聚合（COUNT/AVG/MAX/MIN）。"
    else:
        extra_rule += "\n本次任务只允许返回原始样本数据，不要在 SQL 里做统计聚合。"
    if time_range:
        extra_rule += (
            f"\n时间范围要求：仅查询 TradeTime >= '{time_range['start']:%Y-%m-%d %H:%M:%S}' "
            f"且 TradeTime < '{time_range['end']:%Y-%m-%d %H:%M:%S}' 的数据。"
        )
    if state.get("intent") == IntentType.QUERY.value:
        extra_rule += "\n优先加 ORDER BY TradeTime DESC。"

    # 对于 pattern/volume_price/volatility 意图，SQL 需要查询完整 OHLCV 数据
    if state.get("intent") in (IntentType.PATTERN.value, IntentType.VOLUME_PRICE.value, IntentType.VOLATILITY.value):
        extra_rule += "\n请查询所有价格相关字段（OpenPrice, HighPrice, LowPrice, LatestPrice, Volume, Turnover, TradeTime）。"

    # 构建 few-shot 示例
    examples_text = "\n\n".join(
        f"示例{i}：\n问题：{ex['question']}\nSQL：\n{ex['sql']}"
        for i, ex in enumerate(_EXAMPLES, start=1)
    )

    system_prompt = _PROMPTS_CONFIG["nl2sql_system"].format(
        schema_text=get_schema_text(), extra_rule=extra_rule, examples=examples_text,
    )
    human_prompt = _PROMPTS_CONFIG["nl2sql_human"].format(question=question)

    try:
        sql = invoke_llm(system_prompt, human_prompt)
    except Exception:
        sql = "-- 无法生成有效SQL"

    return {"sql": sql}


# ==================== 节点 3：SQL 执行 ====================

def sql_execute_node(state: AgentState) -> dict:
    """执行 SQL 查询。"""
    if state.get("status") == "no_sql":
        return {"query_result": {"ok": False, "error": state.get("message", "无法生成有效SQL")}}

    sql = state.get("sql", "")
    plan = state.get("plan", {})
    intent = plan.get("intent")
    execution_mode = plan.get("execution_mode")

    if intent == "analysis" and execution_mode == "sql_aggregate":
        return {"query_result": safe_execute_aggregate(sql), "retried": False}

    if intent == "analysis" and execution_mode == "python_analysis":
        # Python 分析仍然先拉取原始数据，后续分析节点使用 rows 进行计算。
        return {"query_result": safe_execute(sql), "retried": False}

    return {"query_result": safe_execute(sql), "retried": False}


# ==================== 节点 4：SQL 验证与自纠 ====================

def sql_validate_node(state: AgentState) -> dict:
    """验证 SQL 执行结果，失败时生成修复 SQL（不自行执行，交由图循环处理）。"""
    query_result = state.get("query_result", {})
    retry_count = state.get("retry_count", 0)

    # 查询成功
    if query_result.get("ok"):
        plan = state.get("plan", {})
        if plan.get("intent") == "analysis" and plan.get("execution_mode") == "sql_aggregate":
            return {"status": "query_ok", "message": "聚合查询成功"}
        if query_result.get("count", 0) == 0:
            return {"status": "empty_result", "message": "查询成功，但没有匹配到数据"}
        return {"status": "query_ok", "message": "查询成功"}

    # 查询失败 + 超过重试次数
    if retry_count >= MAX_RETRY_COUNT:
        return {"status": "query_error", "message": f"SQL执行失败（已重试{MAX_RETRY_COUNT}次）: {query_result.get('error', '')}"}

    # 尝试修复 SQL（仅生成修复后的 SQL，不执行）
    bad_sql = state["sql"]
    error_message = query_result.get("error", "未知错误")

    system_prompt = _PROMPTS_CONFIG["sql_retry_system"].format(
        schema_text=get_schema_text(), question=state["question"],
        bad_sql=bad_sql, error_message=error_message,
    )
    human_prompt = _PROMPTS_CONFIG["sql_retry_human"]

    try:
        retry_sql = invoke_llm(system_prompt, human_prompt)
    except Exception:
        return {"status": "query_error", "message": f"SQL修复失败: {error_message}"}

    # 将修复后的 SQL 写入 state，由图循环回 sql_execute 重新执行
    return {
        "sql": retry_sql,
        "retry_sql": retry_sql,
        "retry_count": retry_count + 1,
        "retried": True,
        "status": "retry",
        "message": f"SQL修复中（第{retry_count + 1}次重试）",
    }


# ==================== 节点 5：分析节点（按意图分发） ====================

def analysis_node(state: AgentState) -> dict:
    """基础统计分析节点（analysis 意图）。"""
    if state.get("status") not in ("query_ok",):
        return {"analysis_result": None, "summary": None}

    plan = state.get("plan", {})
    intent = state.get("intent", "")

    if intent == IntentType.QUERY.value:
        return {"analysis_result": None, "summary": None}

    # sql_aggregate 模式直接取结果
    if plan.get("execution_mode") == "sql_aggregate":
        stats = state["query_result"].get("stats", {})
        analysis_result = {"ok": True, "stats": stats}
        summary = _summarize(state["question"], stats)
        return {"analysis_result": analysis_result, "summary": summary, "status": "analysis_ok", "message": "分析成功"}

    # python_analysis 模式
    rows = state.get("query_result", {}).get("rows", [])
    if not rows:
        return {"analysis_result": {"ok": False, "error": "无数据可分析"}, "summary": None}

    field = plan.get("field", DEFAULT_FIELD)
    analysis_type = plan.get("analysis_type", DEFAULT_ANALYSIS_TYPE)

    stats = run_analysis(rows, field, analysis_type)
    analysis_result = {"ok": True, "stats": stats}
    summary = _summarize(state["question"], stats)

    return {"analysis_result": analysis_result, "summary": summary, "status": "analysis_ok", "message": "分析成功"}


def pattern_node(state: AgentState) -> dict:
    """价格形态特征分析节点。"""
    if state.get("status") != "query_ok":
        return {"pattern_result": None, "summary": None}

    rows = state.get("query_result", {}).get("rows", [])
    if not rows:
        return {"pattern_result": {"error": "无数据"}, "summary": "无法进行形态分析：数据为空"}

    field = state.get("plan", {}).get("field", "LatestPrice")
    result = run_pattern_analysis(rows, field)
    summary = _quant_summarize(state["question"], result)

    return {"pattern_result": result, "summary": summary, "status": "analysis_ok", "message": "形态分析完成",
            "composite_signal": result.get("composite_signal")}


def volume_price_node(state: AgentState) -> dict:
    """量价关系分析节点。"""
    if state.get("status") != "query_ok":
        return {"quant_result": None, "summary": None}

    rows = state.get("query_result", {}).get("rows", [])
    if not rows:
        return {"quant_result": {"error": "无数据"}, "summary": "无法进行量价分析：数据为空"}

    result = run_volume_price_analysis(rows)
    summary = _quant_summarize(state["question"], result)

    return {"quant_result": result, "summary": summary, "status": "analysis_ok", "message": "量价分析完成",
            "composite_signal": result.get("composite_signal"),
            "backtest_result": result.get("backtest")}


def volatility_node(state: AgentState) -> dict:
    """波动率与统计特征分析节点。"""
    if state.get("status") != "query_ok":
        return {"quant_result": None, "summary": None}

    rows = state.get("query_result", {}).get("rows", [])
    if not rows:
        return {"quant_result": {"error": "无数据"}, "summary": "无法进行波动率分析：数据为空"}

    field = state.get("plan", {}).get("field", "LatestPrice")
    result = run_volatility_analysis(rows, field)
    summary = _quant_summarize(state["question"], result)

    return {"quant_result": result, "summary": summary, "status": "analysis_ok", "message": "波动率分析完成",
            "composite_signal": result.get("composite_signal"),
            "backtest_result": result.get("backtest")}


# ==================== 节点 6：结果总结 ====================

def summarize_node(state: AgentState) -> dict:
    """总结节点：汇总最终输出。"""
    # 闲聊直接透传 summary
    if state.get("status") == "chitchat":
        return {"summary": state.get("summary", "你好！我是 SQLark 量化分析智能体。")}

    # 如果已经有 summary，直接格式化输出
    summary = state.get("summary")
    if not summary:
        status = state.get("status", "")
        if status == "empty_result":
            summary = "查询成功但没有匹配到数据。"
        elif status in ("query_error", "no_sql"):
            summary = state.get("message", "查询失败")
        elif state.get("intent") == IntentType.QUERY.value:
            count = state.get("query_result", {}).get("count", 0)
            summary = f"查询成功，共返回 {count} 条数据。"

    return {"summary": summary or "执行完成"}


# ==================== LLM 总结辅助 ====================

def _summarize(question: str, stats: dict) -> str:
    """使用 LLM 生成分析总结。"""
    system_prompt = _PROMPTS_CONFIG["summarize_system"]
    human_prompt = _PROMPTS_CONFIG["summarize_human"].format(question=question, stats=stats)

    try:
        return invoke_llm(system_prompt, human_prompt)
    except Exception:
        return _local_summary(stats)


def _quant_summarize(question: str, analysis_result: dict) -> str:
    """使用 LLM 生成量化分析总结。"""
    system_prompt = _PROMPTS_CONFIG["quant_summarize_system"]
    human_prompt = _PROMPTS_CONFIG["quant_summarize_human"].format(
        question=question, analysis_result=analysis_result,
    )

    try:
        return invoke_llm(system_prompt, human_prompt)
    except Exception:
        return _local_quant_summary(analysis_result)


def _local_summary(stats: dict) -> str:
    """本地规则兜底总结。"""
    if not isinstance(stats, dict):
        return "分析结果不可用。"
    if stats.get("error"):
        return f"分析失败：{stats['error']}"

    if "trend" in stats:
        trend_map = {"up": "呈上升趋势", "down": "呈下降趋势", "flat": "整体较平稳"}
        trend_text = trend_map.get(stats.get("trend"), "趋势不明显")
        change = stats.get("change")
        change_rate = stats.get("change_rate")
        if change is not None and change_rate is not None:
            return f"该字段整体{trend_text}，区间变化为 {change}，变化率约 {change_rate}%。"
        return f"该字段整体{trend_text}。"

    if "anomaly_count" in stats:
        return f"共检测到 {stats.get('anomaly_count')} 个异常点，建议重点关注。"

    if "mean" in stats and "max" in stats and "min" in stats:
        return f"均值为 {stats.get('mean')}，最高 {stats.get('max')}，最低 {stats.get('min')}，范围 {stats.get('range')}。"

    return "统计结果已生成。"


def _local_quant_summary(result: dict) -> str:
    """量化分析本地兜底总结。"""
    if not isinstance(result, dict):
        return "分析结果不可用。"
    if result.get("error"):
        return f"分析失败：{result['error']}"
    return "量化分析完成，请查看详细结果。"


# ==================== 路由函数 ====================

def route_after_intent(state: AgentState) -> str:
    """意图识别后的路由：先进入 planner 规划节点。"""
    if state.get("intent") == IntentType.CHITCHAT.value:
        return "chitchat"
    return "planner"


def route_after_validate(state: AgentState) -> str:
    """SQL 验证后的路由：成功→分析，需重试→执行，失败→总结。"""
    status = state.get("status", "")

    if status == "query_ok":
        return "analysis_dispatch"
    if status == "empty_result":
        return "summarize"
    if status == "retry":
        return "sql_execute"

    # query_error / no_sql / 其他
    return "summarize"


def route_analysis_dispatch(state: AgentState) -> str:
    """分析分发路由：根据意图选择分析节点。"""
    intent = state.get("intent", DEFAULT_INTENT)
    dispatch = {
        IntentType.QUERY.value: "query_done",
        IntentType.ANALYSIS.value: "basic_analysis",
        IntentType.PATTERN.value: "pattern_analysis",
        IntentType.VOLUME_PRICE.value: "volume_price_analysis",
        IntentType.VOLATILITY.value: "volatility_analysis",
    }
    return dispatch.get(intent, "query_done")
