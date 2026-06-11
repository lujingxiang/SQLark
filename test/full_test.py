"""全量测试脚本：20 个问题，由简到难，覆盖 5 种意图。"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
VENV_SITE_PACKAGES = ROOT_DIR / ".venv" / "Lib" / "site-packages"
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))
if VENV_SITE_PACKAGES.exists() and str(VENV_SITE_PACKAGES) not in sys.path:
    sys.path.insert(0, str(VENV_SITE_PACKAGES))

from app.graph.graph import get_graph

# ==================== 20 个测试问题 ====================
# 难度递进：基础查询 → 聚合分析 → 形态识别 → 量价关系 → 波动率统计 → 综合复杂

TEST_CASES = [
    # ── Level 1：基础查询（query）──
    {
        "id": 1,
        "question": "查看最新的5条股票数据",
        "expected_intent": "query",
        "difficulty": 1,
        "category": "基础查询",
    },
    {
        "id": 2,
        "question": "今天开盘价是多少",
        "expected_intent": "query",
        "difficulty": 1,
        "category": "基础查询",
    },
    {
        "id": 3,
        "question": "最近一条数据的成交量是多少",
        "expected_intent": "query",
        "difficulty": 1,
        "category": "基础查询",
    },
    {
        "id": 4,
        "question": "显示昨天所有的行情数据",
        "expected_intent": "query",
        "difficulty": 2,
        "category": "基础查询(时间)",
    },

    # ── Level 2：聚合分析（analysis）──
    {
        "id": 5,
        "question": "最近7天的平均成交量是多少",
        "expected_intent": "analysis",
        "difficulty": 2,
        "category": "聚合分析",
    },
    {
        "id": 6,
        "question": "今天最高价和最低价分别是多少",
        "expected_intent": "analysis",
        "difficulty": 2,
        "category": "聚合分析",
    },
    {
        "id": 7,
        "question": "统计一下总共有多少条行情数据",
        "expected_intent": "analysis",
        "difficulty": 2,
        "category": "聚合分析",
    },
    {
        "id": 8,
        "question": "分析一下最近3天价格的趋势",
        "expected_intent": "analysis",
        "difficulty": 3,
        "category": "趋势分析",
    },

    # ── Level 3：价格形态特征（pattern）──
    {
        "id": 9,
        "question": "最近有没有出现锤子线形态",
        "expected_intent": "pattern",
        "difficulty": 3,
        "category": "K线形态",
    },
    {
        "id": 10,
        "question": "分析最近的K线形态，看看有没有吞没形态",
        "expected_intent": "pattern",
        "difficulty": 3,
        "category": "K线形态",
    },
    {
        "id": 11,
        "question": "5日均线和10日均线有没有金叉或死叉",
        "expected_intent": "pattern",
        "difficulty": 4,
        "category": "均线交叉",
    },
    {
        "id": 12,
        "question": "最近的支撑位和压力位在哪里",
        "expected_intent": "pattern",
        "difficulty": 4,
        "category": "支撑压力",
    },

    # ── Level 4：量价关系（volume_price）──
    {
        "id": 13,
        "question": "最近有没有量价背离的情况",
        "expected_intent": "volume_price",
        "difficulty": 4,
        "category": "量价背离",
    },
    {
        "id": 14,
        "question": "分析一下最近的放量突破和缩量盘整",
        "expected_intent": "volume_price",
        "difficulty": 4,
        "category": "放量/缩量",
    },
    {
        "id": 15,
        "question": "OBV指标最近的表现如何",
        "expected_intent": "volume_price",
        "difficulty": 5,
        "category": "OBV指标",
    },
    {
        "id": 16,
        "question": "最近换手率有没有异常",
        "expected_intent": "volume_price",
        "difficulty": 5,
        "category": "换手率异常",
    },

    # ── Level 5：波动率与统计（volatility）──
    {
        "id": 17,
        "question": "计算最近的历史波动率",
        "expected_intent": "volatility",
        "difficulty": 5,
        "category": "历史波动率",
    },
    {
        "id": 18,
        "question": "分析一下ATR和最大回撤",
        "expected_intent": "volatility",
        "difficulty": 5,
        "category": "ATR/回撤",
    },

    # ── Level 6：综合复杂 ──
    {
        "id": 19,
        "question": "综合分析最近的K线形态、量价关系和波动率，给出一个全面的市场判断",
        "expected_intent": "pattern",
        "difficulty": 6,
        "category": "综合分析",
    },
    {
        "id": 20,
        "question": "最近三天市场波动加大了吗？从波动率、量价关系和价格形态三个角度分析",
        "expected_intent": "volatility",
        "difficulty": 6,
        "category": "综合分析",
    },
]


def evaluate_result(case: dict, result: dict) -> dict:
    """评估单个测试结果。"""
    evaluation = {
        "id": case["id"],
        "question": case["question"],
        "expected_intent": case["expected_intent"],
        "difficulty": case["difficulty"],
        "category": case["category"],
    }

    # 实际意图
    actual_intent = result.get("intent", "")
    evaluation["actual_intent"] = actual_intent
    evaluation["intent_match"] = actual_intent == case["expected_intent"]

    # 执行状态
    status = result.get("status", "")
    evaluation["status"] = status
    evaluation["is_success"] = status in ("query_ok", "analysis_ok", "empty_result")

    # SQL
    evaluation["sql"] = result.get("sql", "")
    evaluation["has_valid_sql"] = bool(result.get("sql", "").strip()) and not result["sql"].strip().startswith("--")

    # 重试
    evaluation["retried"] = result.get("retried", False)
    evaluation["retry_count"] = result.get("retry_count", 0)

    # 数据行数
    query_result = result.get("query_result", {})
    evaluation["row_count"] = query_result.get("count", 0) if query_result.get("ok") else 0

    # 分析结果
    evaluation["has_analysis"] = bool(result.get("analysis_result") or result.get("pattern_result") or result.get("quant_result"))

    # 总结
    evaluation["has_summary"] = bool(result.get("summary"))
    evaluation["summary"] = result.get("summary", "")[:200] if result.get("summary") else ""

    # 错误信息
    evaluation["error_message"] = result.get("message", "") if not evaluation["is_success"] else ""

    return evaluation


def main():
    graph = get_graph()
    results = []
    total = len(TEST_CASES)

    print("=" * 70)
    print(f"SQLark 全量测试 - 共 {total} 个用例")
    print("=" * 70)

    for i, case in enumerate(TEST_CASES, start=1):
        print(f"\n[{i}/{total}] Q{case['id']}: {case['question']}")
        print(f"  期望意图: {case['expected_intent']} | 难度: {'★' * case['difficulty']}")
        start_time = time.time()

        try:
            result = graph.invoke({"question": case["question"]})
            elapsed = time.time() - start_time
            evaluation = evaluate_result(case, result)
            evaluation["elapsed_seconds"] = round(elapsed, 2)
            evaluation["exception"] = None

            intent_mark = "Y" if evaluation["intent_match"] else "N"
            success_mark = "Y" if evaluation["is_success"] else "N"
            print(f"  意图: {evaluation['actual_intent']} {intent_mark} | 状态: {evaluation['status']} {success_mark} | 耗时: {elapsed:.1f}s")
            if evaluation["retried"]:
                print(f"  重试: {evaluation['retry_count']}次")
            if evaluation["row_count"]:
                print(f"  数据: {evaluation['row_count']}行")
            if not evaluation["is_success"]:
                print(f"  错误: {evaluation['error_message']}")

        except Exception as e:
            elapsed = time.time() - start_time
            evaluation = {
                "id": case["id"],
                "question": case["question"],
                "expected_intent": case["expected_intent"],
                "difficulty": case["difficulty"],
                "category": case["category"],
                "actual_intent": "",
                "intent_match": False,
                "status": "exception",
                "is_success": False,
                "sql": "",
                "has_valid_sql": False,
                "retried": False,
                "retry_count": 0,
                "row_count": 0,
                "has_analysis": False,
                "has_summary": False,
                "summary": "",
                "error_message": str(e),
                "elapsed_seconds": round(elapsed, 2),
                "exception": str(e),
            }
            print(f"  异常: {e}")

        results.append(evaluation)

    # ==================== 汇总统计 ====================
    print("\n" + "=" * 70)
    print("汇总统计")
    print("=" * 70)

    success_count = sum(1 for r in results if r["is_success"])
    intent_match_count = sum(1 for r in results if r["intent_match"])
    avg_elapsed = sum(r["elapsed_seconds"] for r in results) / total if total else 0

    print(f"总用例数: {total}")
    print(f"执行成功: {success_count}/{total} ({success_count/total:.0%})")
    print(f"意图匹配: {intent_match_count}/{total} ({intent_match_count/total:.0%})")
    print(f"平均耗时: {avg_elapsed:.1f}s")

    # 按类别统计
    print("\n按类别统计:")
    categories = {}
    for r in results:
        cat = r["category"]
        if cat not in categories:
            categories[cat] = {"total": 0, "success": 0, "intent_match": 0}
        categories[cat]["total"] += 1
        if r["is_success"]:
            categories[cat]["success"] += 1
        if r["intent_match"]:
            categories[cat]["intent_match"] += 1

    for cat, stats in categories.items():
        print(f"  {cat}: 成功 {stats['success']}/{stats['total']}, 意图匹配 {stats['intent_match']}/{stats['total']}")

    # 按难度统计
    print("\n按难度统计:")
    difficulties = {}
    for r in results:
        d = r["difficulty"]
        if d not in difficulties:
            difficulties[d] = {"total": 0, "success": 0}
        difficulties[d]["total"] += 1
        if r["is_success"]:
            difficulties[d]["success"] += 1

    for d in sorted(difficulties.keys()):
        stats = difficulties[d]
        stars = "★" * d
        print(f"  难度{stars}: 成功 {stats['success']}/{stats['total']}")

    # 保存 JSON 结果
    output_path = ROOT_DIR / "test" / "test_results.json"
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2, default=str)
    print(f"\n详细结果已保存到: {output_path}")


if __name__ == "__main__":
    main()
