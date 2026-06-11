"""数据源插件接口与默认实现。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from app.db.schema import get_schema_text, get_table_names
from app.tools.sql_executor import safe_execute, safe_execute_aggregate


class DataSourcePlugin(ABC):
    """数据源插件基类。"""

    name: str
    description: str

    @abstractmethod
    def describe(self) -> Dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def schema(self) -> str:
        raise NotImplementedError

    @abstractmethod
    def query(self, params: Dict[str, Any]) -> Dict[str, Any]:
        raise NotImplementedError


class SQLiteDataSourcePlugin(DataSourcePlugin):
    name = "sqlite_default"
    description = "本地 SQLite 数据源，默认提供 StockData 和 StockData_15min 表。"

    def describe(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "tables": get_table_names(),
        }

    def schema(self) -> str:
        return get_schema_text()

    def query(self, params: Dict[str, Any]) -> Dict[str, Any]:
        sql = params.get("sql")
        if not sql:
            return {"ok": False, "error": "缺少 sql 参数", "rows": [], "count": 0}

        # 区分聚合和原始查询
        sql_upper = sql.strip().upper()
        if any(func in sql_upper for func in ["COUNT(", "AVG(", "MAX(", "MIN("]):
            return safe_execute_aggregate(sql)
        return safe_execute(sql)


class MarketQuotePlugin(DataSourcePlugin):
    name = "MarketQuote"
    description = "模拟外部行情工具，返回行情或因子类时间序列数据。"

    def describe(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "fields": ["symbol", "timestamp", "price", "volume"],
        }

    def schema(self) -> str:
        return (
            "外部行情数据源接口：接受 symbol 和 limit 参数，返回时间序列行情数据。"
            " 字段包括 symbol、timestamp、price、volume。"
        )

    def query(self, params: Dict[str, Any]) -> Dict[str, Any]:
        symbol = params.get("symbol") or params.get("query")
        limit = params.get("limit", 20)
        if not symbol:
            return {"ok": False, "error": "缺少 symbol 参数", "quotes": []}

        quotes = [
            {"symbol": symbol, "timestamp": f"2026-06-0{day} 15:00:00", "price": 100 + day, "volume": 1000 + day * 10}
            for day in range(1, min(limit, 10) + 1)
        ]
        return {"ok": True, "quotes": quotes}


class NewsSentimentPlugin(DataSourcePlugin):
    name = "NewsSentiment"
    description = "模拟外部新闻舆情工具，返回摘要和情绪评分。"

    def describe(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "fields": ["query", "summary", "sentiment_score"],
        }

    def schema(self) -> str:
        return "外部新闻舆情数据源接口：接受 query 和 limit 参数，返回新闻摘要和情绪评分。"

    def query(self, params: Dict[str, Any]) -> Dict[str, Any]:
        query = params.get("query") or params.get("symbol")
        if not query:
            return {"ok": False, "error": "缺少 query 参数", "summary": "", "sentiment_score": 0.0}

        summary = f"针对 '{query}' 的新闻摘要：近期舆情偏中性，市场关注度一般。"
        return {"ok": True, "summary": summary, "sentiment_score": 0.05}


def get_default_data_sources() -> List[DataSourcePlugin]:
    return [
        SQLiteDataSourcePlugin(),
        MarketQuotePlugin(),
        NewsSentimentPlugin(),
    ]


def get_data_source_by_name(name: str) -> Optional[DataSourcePlugin]:
    for plugin in get_default_data_sources():
        if plugin.name == name:
            return plugin
    return None
