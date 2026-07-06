"""Agent 工具定义与函数调用接口。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Type

from langchain.tools import Tool
from pydantic import BaseModel, Field

from app.config.config import load_semantic_config
from app.db.schema import get_schema_text
from app.tools.data_source import get_data_source_by_name
from app.tools.pattern import run_pattern_analysis
from app.tools.quant_analysis import run_analysis, run_volatility_analysis, run_volume_price_analysis
from app.tools.sql_executor import safe_execute, safe_execute_aggregate

SEMANTIC_CONFIG = load_semantic_config()


class AgentTool(ABC):
    """Agent 工具基类。"""

    name: str
    description: str
    input_model: Type[BaseModel]
    output_model: Type[BaseModel]
    examples: List[Dict[str, Any]] = []

    def function_schema(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.input_model.model_json_schema(),
        }

    @abstractmethod
    def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError


class QueryRawStockDataInput(BaseModel):
    sql_query: str
    data_source: str = "sqlite_default"


class QueryRawStockDataOutput(BaseModel):
    ok: bool
    rows: List[Dict[str, Any]] = []
    error: str = ""
    count: int = 0


class QueryRawStockDataTool(AgentTool):
    name = "QueryRawStockData"
    description = "执行只读数据源查询，返回原始股票数据，禁止聚合函数。"
    input_model = QueryRawStockDataInput
    output_model = QueryRawStockDataOutput
    examples = [
        {
            "name": name,
            "input": {
                "sql_query": "SELECT * FROM StockData WHERE Name='宁德时代' ORDER BY TradeTime DESC LIMIT 20",
                "data_source": "sqlite_default",
            },
            "output": {"ok": True, "count": 20, "rows": []},
        },
    ]

    def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        data_source = get_data_source_by_name(arguments.get("data_source", "sqlite_default"))
        if not data_source:
            return {"ok": False, "error": f"未知数据源: {arguments.get('data_source')}", "rows": [], "count": 0}
        return data_source.query({"sql": arguments["sql_query"]})


class QueryAggregateStockDataInput(BaseModel):
    sql_query: str
    data_source: str = "sqlite_default"


class QueryAggregateStockDataOutput(BaseModel):
    ok: bool
    stats: Dict[str, Any] = {}
    error: str = ""


class QueryAggregateStockDataTool(AgentTool):
    name = "QueryAggregateStockData"
    description = "执行聚合查询，返回统计结果。"
    input_model = QueryAggregateStockDataInput
    output_model = QueryAggregateStockDataOutput
    examples = [
        {
            "name": name,
            "input": {
                "sql_query": "SELECT AVG(Volume) as avg_volume FROM StockData WHERE Name='特斯拉'",
                "data_source": "sqlite_default",
            },
            "output": {"ok": True, "stats": {"avg_volume": 12345}},
        },
    ]

    def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        data_source = get_data_source_by_name(arguments.get("data_source", "sqlite_default"))
        if not data_source:
            return {"ok": False, "error": f"未知数据源: {arguments.get('data_source')}", "stats": {}}
        return data_source.query({"sql": arguments["sql_query"]})


class PythonDataAnalysisInput(BaseModel):
    sql_query: str
    analysis_type: str
    target_field: str
    data_source: str = "sqlite_default"


class PythonDataAnalysisOutput(BaseModel):
    ok: bool
    stats: Dict[str, Any] = {}
    error: str = ""


class PythonDataAnalysisTool(AgentTool):
    name = "PythonDataAnalysis"
    description = "执行原始数据查询后，使用 Python 进行趋势、波动、异常等分析。"
    input_model = PythonDataAnalysisInput
    output_model = PythonDataAnalysisOutput
    examples = [
        {
            "name": name,
            "input": {
                "sql_query": "SELECT TradeTime, LatestPrice, Volume FROM StockData WHERE Name='宁德时代' ORDER BY TradeTime DESC LIMIT 100",
                "analysis_type": "trend",
                "target_field": "LatestPrice",
                "data_source": "sqlite_default",
            },
            "output": {"ok": True, "stats": {"trend": "up"}},
        },
    ]

    def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        # 始终走原始行查询路径，避免 data_source.query() 因 SQL 含聚合函数而路由到 safe_execute_aggregate
        query_result = safe_execute(arguments["sql_query"])
        rows = query_result.get("rows", [])
        if not rows:
            return {"ok": False, "error": query_result.get("error", "无数据可分析")}
        stats = run_analysis(rows, arguments["target_field"], arguments["analysis_type"])
        return {"ok": True, "stats": stats}


class PatternAnalysisInput(BaseModel):
    sql_query: str


class PatternAnalysisOutput(BaseModel):
    ok: bool
    pattern_result: Dict[str, Any] = {}
    error: str = ""


class PatternAnalysisTool(AgentTool):
    name = "PatternAnalysis"
    description = "识别 K 线形态特征，包括锤子线、吞没、十字星、均线金叉/死叉、支撑位、压力位、缺口等。"
    input_model = PatternAnalysisInput
    output_model = PatternAnalysisOutput
    examples = [
        {
            "name": name,
            "input": {"sql_query": "SELECT TradeTime, OpenPrice, HighPrice, LowPrice, LatestPrice, Volume FROM StockData WHERE Name='宁德时代' ORDER BY TradeTime DESC LIMIT 100"},
            "output": {"ok": True, "pattern_result": {}},
        },
    ]

    def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        rows = safe_execute(arguments["sql_query"]).get("rows", [])
        if not rows:
            return {"ok": False, "error": "无数据可分析"}
        return {"ok": True, "pattern_result": run_pattern_analysis(rows, "LatestPrice")}


class VolumePriceAnalysisInput(BaseModel):
    sql_query: str


class VolumePriceAnalysisOutput(BaseModel):
    ok: bool
    quant_result: Dict[str, Any] = {}
    error: str = ""


class VolumePriceAnalysisTool(AgentTool):
    name = "VolumePriceAnalysis"
    description = "分析量价关系，例如背离、放量突破、缩量盘整、OBV 等。"
    input_model = VolumePriceAnalysisInput
    output_model = VolumePriceAnalysisOutput
    examples = [
        {
            "name": name,
            "input": {"sql_query": "SELECT TradeTime, LatestPrice, Volume FROM StockData WHERE Name='特斯拉' ORDER BY TradeTime DESC LIMIT 100"},
            "output": {"ok": True, "quant_result": {}},
        },
    ]

    def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        rows = safe_execute(arguments["sql_query"]).get("rows", [])
        if not rows:
            return {"ok": False, "error": "无数据可分析"}
        return {"ok": True, "quant_result": run_volume_price_analysis(rows)}


class VolatilityAnalysisInput(BaseModel):
    sql_query: str


class VolatilityAnalysisOutput(BaseModel):
    ok: bool
    quant_result: Dict[str, Any] = {}
    error: str = ""


class VolatilityAnalysisTool(AgentTool):
    name = "VolatilityAnalysis"
    description = "分析波动率、ATR、最大回撤等风险统计特征。"
    input_model = VolatilityAnalysisInput
    output_model = VolatilityAnalysisOutput
    examples = [
        {
            "name": name,
            "input": {"sql_query": "SELECT TradeTime, LatestPrice FROM StockData WHERE Name='特斯拉' ORDER BY TradeTime DESC LIMIT 100"},
            "output": {"ok": True, "quant_result": {}},
        },
    ]

    def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        rows = safe_execute(arguments["sql_query"]).get("rows", [])
        if not rows:
            return {"ok": False, "error": "无数据可分析"}
        return {"ok": True, "quant_result": run_volatility_analysis(rows, "LatestPrice")}


class SchemaToolInput(BaseModel):
    data_source: str = "sqlite_default"


class SchemaToolOutput(BaseModel):
    schema_text: str


class SchemaTool(AgentTool):
    name = "SchemaTool"
    description = "返回指定数据源的表结构和字段说明，用于辅助 SQL 生成。"
    input_model = SchemaToolInput
    output_model = SchemaToolOutput
    examples = [
        {
            "name": name,
            "input": {"data_source": "sqlite_default"},
            "output": {"schema_text": "CREATE TABLE StockData ..."},
        },
    ]

    def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        data_source = get_data_source_by_name(arguments.get("data_source", "sqlite_default"))
        if not data_source:
            return {"ok": False, "schema_text": f"未知数据源: {arguments.get('data_source')}"}
        return {"ok": True, "schema_text": data_source.schema()}


class MarketQuoteToolInput(BaseModel):
    symbol: str
    limit: int = 20


class MarketQuoteToolOutput(BaseModel):
    ok: bool
    quotes: List[Dict[str, Any]] = []
    error: str = ""


class MarketQuoteTool(AgentTool):
    name = "MarketQuoteTool"
    description = "查询金融市场数据或因子数据，作为外部行情工具使用。"
    input_model = MarketQuoteToolInput
    output_model = MarketQuoteToolOutput
    examples = [
        {
            "name": name,
            "input": {"symbol": "TSLA", "limit": 10},
            "output": {"ok": True, "quotes": []},
        },
    ]

    def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        plugin = get_data_source_by_name("MarketQuote")
        if not plugin:
            return {"ok": False, "error": "未配置 MarketQuote 数据源"}
        return plugin.query({"symbol": arguments["symbol"], "limit": arguments.get("limit", 10)})


class NewsSentimentToolInput(BaseModel):
    query: str
    limit: int = 5


class NewsSentimentToolOutput(BaseModel):
    ok: bool
    sentiment_score: float = 0.0
    summary: str = ""
    error: str = ""


class NewsSentimentTool(AgentTool):
    name = "NewsSentimentTool"
    description = "查询金融新闻并返回舆情摘要和情绪分析。"
    input_model = NewsSentimentToolInput
    output_model = NewsSentimentToolOutput
    examples = [
        {
            "name": name,
            "input": {"query": "特斯拉 新闻", "limit": 3},
            "output": {"ok": True, "sentiment_score": 0.1, "summary": "金融新闻偏积极"},
        },
    ]

    def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        plugin = get_data_source_by_name("NewsSentiment")
        if not plugin:
            return {"ok": False, "error": "未配置 NewsSentiment 数据源"}
        return plugin.query({"query": arguments["query"], "limit": arguments.get("limit", 5)})


class ExternalApiToolInput(BaseModel):
    api_name: str
    params: Dict[str, Any] = Field(default_factory=dict)


class ExternalApiToolOutput(BaseModel):
    ok: bool
    result: Dict[str, Any] = Field(default_factory=dict)
    error: str = ""


class ExternalApiTool(AgentTool):
    name = "ExternalApiTool"
    description = "调用外部数据源插件，例如 MarketQuote 或 NewsSentiment。"
    input_model = ExternalApiToolInput
    output_model = ExternalApiToolOutput
    examples = [
        {
            "name": name,
            "input": {"api_name": "MarketQuote", "params": {"symbol": "TSLA", "limit": 5}},
            "output": {"ok": True, "result": {"quotes": []}},
        },
    ]

    def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        plugin = get_data_source_by_name(arguments["api_name"])
        if not plugin:
            return {"ok": False, "error": f"未知外部数据源: {arguments['api_name']}"}
        return plugin.query(arguments.get("params", {}))


def get_default_tools() -> List[AgentTool]:
    return [
        QueryRawStockDataTool(),
        QueryAggregateStockDataTool(),
        PythonDataAnalysisTool(),
        PatternAnalysisTool(),
        VolumePriceAnalysisTool(),
        VolatilityAnalysisTool(),
        SchemaTool(),
        MarketQuoteTool(),
        NewsSentimentTool(),
        ExternalApiTool(),
    ]


def get_tool_by_name(name: str) -> AgentTool | None:
    for tool in get_default_tools():
        if tool.name == name:
            return tool
    return None


def build_langchain_tools() -> List[Tool]:
    tools: List[Tool] = []
    for tool in get_default_tools():
        tools.append(
            Tool.from_function(
                func=tool.execute,
                name=tool.name,
                description=tool.description,
                args_schema=tool.input_model,
            )
        )
    return tools
