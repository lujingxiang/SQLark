"""LangGraph 智能体状态定义。"""

from enum import Enum
from typing import Any, Optional, TypedDict


class IntentType(str, Enum):
    """意图类型枚举。"""
    QUERY = "query"
    ANALYSIS = "analysis"
    PATTERN = "pattern"
    VOLUME_PRICE = "volume_price"
    VOLATILITY = "volatility"
    CHITCHAT = "chitchat"


class AgentState(TypedDict, total=False):
    """LangGraph 智能体状态。"""
    # 输入
    question: str

    # 意图识别结果
    intent: str
    plan: dict
    time_range: Optional[dict]

    # SQL 生成与执行
    sql: str
    sql_error: str
    retry_count: int

    # 查询结果
    query_result: dict

    # 分析
    analysis_type: str
    analysis_result: Optional[dict]

    # 量化分析
    pattern_result: Optional[dict]
    quant_result: Optional[dict]
    composite_signal: Optional[dict]
    backtest_result: Optional[dict]

    # 输出
    summary: str
    status: str
    message: str
    retried: bool
    retry_sql: Optional[str]

    # 对话历史
    messages: list

    # ReAct / 工具调用追踪
    tool_name: str
    tool_args: dict
    tool_result: dict
    tool_status: str
    decision: str
    tool_history: list
    thoughts: list
    observations: list


MAX_RETRY_COUNT = 3
