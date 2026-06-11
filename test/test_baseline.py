"""Baseline tests for SQLark core components."""

from __future__ import annotations

import unittest

from app.graph.graph import get_graph
from app.graph.nodes import _parse_time_range, _rule_based_intent, decision_node, planner_node, route_after_decision
from app.tools.agent_tools import (
    ExternalApiTool,
    QueryRawStockDataTool,
    QueryAggregateStockDataTool,
    PythonDataAnalysisTool,
    PatternAnalysisTool,
    VolumePriceAnalysisTool,
    VolatilityAnalysisTool,
    SchemaTool,
    get_default_tools,
)
from app.tools.data_source import get_data_source_by_name


class TestGraphBaseline(unittest.TestCase):
    def test_graph_can_build(self):
        graph = get_graph()
        self.assertIsNotNone(graph)
        self.assertTrue(hasattr(graph, "invoke"))

    def test_parse_time_range_recent_5_days(self):
        result = _parse_time_range("查看宁德时代最近5天的价格")
        self.assertIsNotNone(result)
        self.assertEqual(result["keyword"], "最近5天")
        self.assertEqual(result["granularity"], "day")

    def test_parse_time_range_today(self):
        result = _parse_time_range("今天的交易数据")
        self.assertIsNotNone(result)
        self.assertEqual(result["keyword"], "today")

    def test_rule_based_intent_chitchat(self):
        self.assertEqual(_rule_based_intent("你好"), "chitchat")
        self.assertEqual(_rule_based_intent("这是什么？"), "chitchat")

    def test_rule_based_intent_pattern(self):
        self.assertEqual(_rule_based_intent("分析最近的K线形态"), "pattern")

    def test_default_tool_registry(self):
        tools = get_default_tools()
        tool_names = [tool.name for tool in tools]
        expected = {
            "QueryRawStockData",
            "QueryAggregateStockData",
            "PythonDataAnalysis",
            "PatternAnalysis",
            "VolumePriceAnalysis",
            "VolatilityAnalysis",
            "SchemaTool",
            "MarketQuoteTool",
            "NewsSentimentTool",
        }
        self.assertTrue(expected.issubset(set(tool_names)))

    def test_tool_function_schema(self):
        tool = QueryRawStockDataTool()
        schema = tool.function_schema()
        self.assertEqual(schema["name"], "QueryRawStockData")
        self.assertIn("description", schema)
        self.assertIn("parameters", schema)
        self.assertIn("sql_query", schema["parameters"]["properties"])

    def test_schema_tool_returns_schema_text(self):
        schema_output = SchemaTool().execute({})
        self.assertIsInstance(schema_output, dict)
        self.assertIn("schema_text", schema_output)

    def test_data_source_registry(self):
        ds = get_data_source_by_name("sqlite_default")
        self.assertIsNotNone(ds)
        self.assertIn("StockData", ds.schema())

    def test_external_api_tool_schema(self):
        schema = ExternalApiTool().function_schema()
        self.assertEqual(schema["name"], "ExternalApiTool")
        self.assertIn("api_name", schema["parameters"]["properties"])

    def test_planner_node_outputs_plan(self):
        state = {"question": "查询最近3天宁德时代的成交量趋势"}
        result = planner_node(state)
        self.assertIsInstance(result, dict)
        self.assertIn("plan", result)
        self.assertEqual(result["status"], "planned")
        self.assertIn("intent", result["plan"])

    def test_decision_node_retries_tool_selection(self):
        state = {"status": "tool_error", "retry_count": 0, "thoughts": []}
        result = decision_node(state)
        self.assertEqual(result["decision"], "tool_selector")
        self.assertEqual(result["retry_count"], 1)

    def test_route_after_decision_to_sql_generate(self):
        state = {"decision": "sql_generate"}
        self.assertEqual(route_after_decision(state), "sql_generate")


class TestToolExecutionShapes(unittest.TestCase):
    def test_query_aggregate_tool_schema(self):
        schema = QueryAggregateStockDataTool().function_schema()
        self.assertEqual(schema["name"], "QueryAggregateStockData")
        self.assertIn("sql_query", schema["parameters"]["properties"])

    def test_python_analysis_tool_schema(self):
        schema = PythonDataAnalysisTool().function_schema()
        self.assertEqual(schema["name"], "PythonDataAnalysis")
        self.assertIn("analysis_type", schema["parameters"]["properties"])

    def test_pattern_analysis_tool_schema(self):
        schema = PatternAnalysisTool().function_schema()
        self.assertEqual(schema["name"], "PatternAnalysis")
        self.assertIn("sql_query", schema["parameters"]["properties"])

    def test_volume_price_tool_schema(self):
        schema = VolumePriceAnalysisTool().function_schema()
        self.assertEqual(schema["name"], "VolumePriceAnalysis")
        self.assertIn("sql_query", schema["parameters"]["properties"])

    def test_volatility_tool_schema(self):
        schema = VolatilityAnalysisTool().function_schema()
        self.assertEqual(schema["name"], "VolatilityAnalysis")
        self.assertIn("sql_query", schema["parameters"]["properties"])


if __name__ == "__main__":
    unittest.main()
