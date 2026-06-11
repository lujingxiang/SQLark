"""阶段 4 进阶场景测试：空结果、SQL 重试、工具缓存、超时保护、多数据源、观察节点。"""

from __future__ import annotations

import time
import unittest
from unittest.mock import patch

from app.graph.nodes import (
    decision_node,
    observation_node,
    route_after_validate,
    sql_validate_node,
    tool_executor_node,
)
from app.graph.state import MAX_RETRY_COUNT
from app.tools.agent_tools import (
    ExternalApiTool,
    MarketQuoteTool,
    NewsSentimentTool,
    SchemaTool,
)
from app.tools.data_source import MarketQuotePlugin, NewsSentimentPlugin
from app.utils import cache as tool_cache


# ─────────────────────────────────────────────
# 空结果路由
# ─────────────────────────────────────────────

class TestEmptyResultHandling(unittest.TestCase):
    def test_empty_result_routes_to_summarize(self):
        self.assertEqual(route_after_validate({"status": "empty_result"}), "summarize")

    def test_sql_validate_detects_empty_rows(self):
        state = {
            "query_result": {"ok": True, "count": 0, "rows": []},
            "retry_count": 0,
            "status": "intent_ok",
            "sql": "SELECT * FROM StockData LIMIT 10",
            "plan": {},
            "question": "test",
        }
        result = sql_validate_node(state)
        self.assertEqual(result["status"], "empty_result")


# ─────────────────────────────────────────────
# SQL 重试流程
# ─────────────────────────────────────────────

class TestSqlRetryFlow(unittest.TestCase):
    def test_failed_query_triggers_retry(self):
        state = {
            "query_result": {"ok": False, "error": "no such table: BadTable"},
            "retry_count": 0,
            "sql": "SELECT * FROM BadTable",
            "status": "intent_ok",
            "question": "查询坏表",
        }
        with patch("app.graph.nodes.invoke_llm", return_value="SELECT * FROM StockData LIMIT 10"):
            result = sql_validate_node(state)
        self.assertEqual(result["status"], "retry")
        self.assertEqual(result["retry_count"], 1)
        self.assertTrue(result["sql"].strip().upper().startswith("SELECT"))

    def test_exceeds_max_retry_returns_error(self):
        state = {
            "query_result": {"ok": False, "error": "persistent error"},
            "retry_count": MAX_RETRY_COUNT,
            "sql": "SELECT * FROM BadTable",
            "status": "intent_ok",
            "question": "测试",
        }
        result = sql_validate_node(state)
        self.assertEqual(result["status"], "query_error")

    def test_retry_status_routes_to_sql_execute(self):
        self.assertEqual(route_after_validate({"status": "retry"}), "sql_execute")

    def test_query_ok_routes_to_analysis_dispatch(self):
        self.assertEqual(route_after_validate({"status": "query_ok"}), "analysis_dispatch")


# ─────────────────────────────────────────────
# 工具结果缓存
# ─────────────────────────────────────────────

class TestToolCache(unittest.TestCase):
    def setUp(self):
        tool_cache.clear()

    def test_schema_tool_result_is_cached(self):
        schema_result = SchemaTool().execute({})
        tool_cache.put("SchemaTool", {}, schema_result)

        cached = tool_cache.get("SchemaTool", {})
        self.assertIsNotNone(cached)
        self.assertEqual(cached["schema_text"], schema_result["schema_text"])

    def test_sql_query_tool_not_cached(self):
        """SQL 查询工具不在 TTL 字典中，不应缓存。"""
        args = {"sql_query": "SELECT * FROM StockData LIMIT 5"}
        tool_cache.put("QueryRawStockData", args, {"ok": True, "rows": []})
        self.assertIsNone(tool_cache.get("QueryRawStockData", args))

    def test_cache_entry_expires(self):
        from app.utils.cache import _key, _store
        tool_cache.put("MarketQuoteTool", {"symbol": "TSLA"}, {"ok": True, "quotes": []})
        k = _key("MarketQuoteTool", {"symbol": "TSLA"})
        # 手动使条目过期
        _store[k] = (_store[k][0], time.time() - 1)
        self.assertIsNone(tool_cache.get("MarketQuoteTool", {"symbol": "TSLA"}))

    def test_cache_size_increases_after_put(self):
        tool_cache.put("SchemaTool", {}, {"schema_text": "test"})
        self.assertEqual(tool_cache.size(), 1)

    def test_tool_executor_uses_cache_on_second_call(self):
        """tool_executor_node 命中缓存时 from_cache 为 True。"""
        schema_result = SchemaTool().execute({})
        tool_cache.put("SchemaTool", {}, schema_result)

        state = {"tool_name": "SchemaTool", "tool_args": {}, "tool_history": [], "thoughts": []}
        result = tool_executor_node(state)

        last_entry = result["tool_history"][-1]
        self.assertTrue(last_entry["from_cache"])

    def test_tool_executor_writes_cache_on_success(self):
        """tool_executor_node 成功执行后写入缓存。"""
        tool_cache.clear()
        state = {"tool_name": "SchemaTool", "tool_args": {}, "tool_history": [], "thoughts": []}
        tool_executor_node(state)
        self.assertIsNotNone(tool_cache.get("SchemaTool", {}))


# ─────────────────────────────────────────────
# 工具调用超时
# ─────────────────────────────────────────────

class TestToolTimeout(unittest.TestCase):
    def setUp(self):
        tool_cache.clear()

    def test_slow_tool_triggers_timeout_error(self):
        def _slow(args):
            time.sleep(0.5)
            return {"ok": True}

        tool = SchemaTool()
        with patch.object(tool, "execute", side_effect=_slow), \
             patch("app.graph.nodes.get_tool_by_name", return_value=tool), \
             patch("app.graph.nodes.TOOL_TIMEOUT_SECONDS", 0.1):
            state = {"tool_name": "SchemaTool", "tool_args": {}, "tool_history": [], "thoughts": []}
            result = tool_executor_node(state)

        tool_result = result.get("tool_result", {})
        self.assertFalse(tool_result.get("ok"))
        self.assertIn("超时", tool_result.get("error", ""))

    def test_fast_tool_completes_successfully(self):
        state = {"tool_name": "SchemaTool", "tool_args": {}, "tool_history": [], "thoughts": []}
        result = tool_executor_node(state)
        self.assertTrue(result["tool_result"].get("ok"))


# ─────────────────────────────────────────────
# 多数据源 / 外部 API 工具
# ─────────────────────────────────────────────

class TestMultiDataSource(unittest.TestCase):
    def test_market_quote_plugin_returns_quotes(self):
        result = MarketQuotePlugin().query({"symbol": "TSLA", "limit": 5})
        self.assertTrue(result["ok"])
        self.assertEqual(len(result["quotes"]), 5)
        self.assertEqual(result["quotes"][0]["symbol"], "TSLA")

    def test_market_quote_plugin_missing_symbol(self):
        result = MarketQuotePlugin().query({})
        self.assertFalse(result["ok"])

    def test_news_sentiment_plugin_returns_summary(self):
        result = NewsSentimentPlugin().query({"query": "特斯拉 新闻"})
        self.assertTrue(result["ok"])
        self.assertIn("sentiment_score", result)
        self.assertIn("summary", result)

    def test_external_api_tool_routes_to_market_quote(self):
        result = ExternalApiTool().execute({"api_name": "MarketQuote", "params": {"symbol": "TSLA", "limit": 3}})
        self.assertTrue(result["ok"])
        self.assertIn("quotes", result)

    def test_external_api_tool_routes_to_news_sentiment(self):
        result = ExternalApiTool().execute({"api_name": "NewsSentiment", "params": {"query": "宁德时代"}})
        self.assertTrue(result["ok"])

    def test_external_api_tool_unknown_source_returns_error(self):
        result = ExternalApiTool().execute({"api_name": "NonExistentAPI", "params": {}})
        self.assertFalse(result["ok"])
        self.assertIn("error", result)

    def test_market_quote_tool_execute(self):
        result = MarketQuoteTool().execute({"symbol": "CATL", "limit": 5})
        self.assertTrue(result["ok"])
        self.assertEqual(len(result["quotes"]), 5)

    def test_news_sentiment_tool_execute(self):
        result = NewsSentimentTool().execute({"query": "宁德时代", "limit": 3})
        self.assertTrue(result["ok"])
        self.assertIsInstance(result["sentiment_score"], float)


# ─────────────────────────────────────────────
# 观察节点（observation_node）
# ─────────────────────────────────────────────

class TestObservationNode(unittest.TestCase):
    def test_raw_query_success_sets_query_ok(self):
        state = {
            "tool_name": "QueryRawStockData",
            "tool_result": {"ok": True, "rows": [{"Name": "特斯拉"}], "count": 1},
            "question": "查询特斯拉",
            "observations": [],
        }
        result = observation_node(state)
        self.assertEqual(result["status"], "query_ok")
        self.assertIsNotNone(result.get("summary"))

    def test_raw_query_failure_sets_query_error(self):
        state = {
            "tool_name": "QueryRawStockData",
            "tool_result": {"ok": False, "error": "SQL error"},
            "question": "查询特斯拉",
            "observations": [],
        }
        result = observation_node(state)
        self.assertEqual(result["status"], "query_error")

    def test_observation_appended_to_list(self):
        state = {
            "tool_name": "QueryRawStockData",
            "tool_result": {"ok": True, "rows": [], "count": 0},
            "question": "test",
            "observations": ["prior observation"],
        }
        result = observation_node(state)
        self.assertEqual(len(result["observations"]), 2)

    def test_aggregate_tool_sets_analysis_status(self):
        state = {
            "tool_name": "QueryAggregateStockData",
            "tool_result": {"ok": True, "stats": {"avg_price": 100}},
            "question": "平均价格",
            "observations": [],
        }
        result = observation_node(state)
        self.assertEqual(result["status"], "analysis_ok")

    def test_unknown_tool_returns_tool_error(self):
        state = {
            "tool_name": "UnknownTool",
            "tool_result": {"ok": False},
            "question": "test",
            "observations": [],
        }
        result = observation_node(state)
        self.assertEqual(result["status"], "tool_error")


# ─────────────────────────────────────────────
# 决策节点（decision_node）
# ─────────────────────────────────────────────

class TestDecisionNode(unittest.TestCase):
    def test_query_ok_decides_summarize(self):
        result = decision_node({"status": "query_ok", "retry_count": 0, "thoughts": []})
        self.assertEqual(result["decision"], "summarize")

    def test_analysis_ok_decides_summarize(self):
        result = decision_node({"status": "analysis_ok", "retry_count": 0, "thoughts": []})
        self.assertEqual(result["decision"], "summarize")

    def test_tool_error_below_max_retries_decides_tool_selector(self):
        result = decision_node({"status": "tool_error", "retry_count": 0, "thoughts": []})
        self.assertEqual(result["decision"], "tool_selector")
        self.assertEqual(result["retry_count"], 1)

    def test_tool_error_at_max_retries_decides_sql_generate(self):
        result = decision_node({"status": "tool_error", "retry_count": MAX_RETRY_COUNT, "thoughts": []})
        self.assertEqual(result["decision"], "sql_generate")

    def test_thought_appended_in_decision(self):
        result = decision_node({"status": "query_ok", "retry_count": 0, "thoughts": ["prior"]})
        self.assertEqual(len(result["thoughts"]), 2)


if __name__ == "__main__":
    unittest.main()
