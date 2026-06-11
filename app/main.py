"""SQLark 入口：支持 CLI 交互和 Web 服务。"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
VENV_SITE_PACKAGES = ROOT_DIR / ".venv" / "Lib" / "site-packages"
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))
if VENV_SITE_PACKAGES.exists() and str(VENV_SITE_PACKAGES) not in sys.path:
    sys.path.insert(0, str(VENV_SITE_PACKAGES))

from app.graph.graph import get_graph


def pretty_print_result(result: dict) -> None:
    """格式化输出图执行结果。"""
    print("\n问题：")
    print(result.get("question", ""))

    print("\n意图：")
    print(result.get("intent", ""))

    print("\n任务规划：")
    print(result.get("plan", {}))

    print("\n生成SQL：")
    print(result.get("sql", ""))

    if result.get("retried"):
        print("\n是否触发重试：是")
        if result.get("retry_sql"):
            print("重试后的SQL：")
            print(result["retry_sql"])
        print(f"重试次数：{result.get('retry_count', 0)}")
    else:
        print("\n是否触发重试：否")

    print("\n执行状态：")
    print(result.get("status", ""))
    print(result.get("message", ""))

    query_result = result.get("query_result", {})
    if not query_result.get("ok"):
        print("\n查询失败：")
        print(query_result.get("error", ""))
        return

    if result.get("status") == "empty_result":
        print("\n没有查询到数据。")
        return

    intent = result.get("intent", "")
    if intent == "query":
        count = query_result.get("count", 0)
        print(f"\n查询成功，共返回 {count} 条数据：")
        for row in query_result.get("rows", [])[:10]:
            print(row)
        if count > 10:
            print("...（仅显示前 10 条）")
        return

    # 分析类结果
    for key in ("analysis_result", "pattern_result", "quant_result"):
        analysis_result = result.get(key)
        if analysis_result and isinstance(analysis_result, dict):
            if not analysis_result.get("ok", True):
                print(f"\n{key} 失败：")
                print(analysis_result.get("error", "未知错误"))
            else:
                print(f"\n{key}：")
                print(analysis_result)

    if result.get("summary"):
        print("\n分析结论：")
        print(result["summary"])


def main() -> None:
    parser = argparse.ArgumentParser(description="SQLark - 股票数据自然语言查询与分析")
    parser.add_argument("--web", action="store_true", help="启动 Web 界面")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    if args.web:
        from app.web_server import run_web_server
        run_web_server(host=args.host, port=args.port)
        return

    question = input("请输入问题：").strip()
    if not question:
        print("问题不能为空")
        return

    graph = get_graph()
    result = graph.invoke({"question": question})
    pretty_print_result(result)


if __name__ == "__main__":
    main()
