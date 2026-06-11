"""批量测试：使用 LangGraph 图执行测试用例。"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
VENV_SITE_PACKAGES = ROOT_DIR / ".venv" / "Lib" / "site-packages"
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))
if VENV_SITE_PACKAGES.exists() and str(VENV_SITE_PACKAGES) not in sys.path:
    sys.path.insert(0, str(VENV_SITE_PACKAGES))

from app.graph.graph import get_graph

QUESTIONS_PATH = ROOT_DIR / "questions.json"


def main():
    if not QUESTIONS_PATH.exists():
        print(f"测试文件不存在: {QUESTIONS_PATH}")
        return

    with QUESTIONS_PATH.open("r", encoding="utf-8") as f:
        cases = json.load(f)

    graph = get_graph()
    total = len(cases)
    success = 0

    for i, case in enumerate(cases, start=1):
        question = case["question"]
        print(f"\n===== 用例 {i}/{total} =====")
        print("问题：", question)

        try:
            result = graph.invoke({"question": question})
            print("意图：", result.get("intent", ""))
            print("状态：", result.get("status", ""))
            print("原始SQL：", result.get("sql", ""))

            if result.get("retried"):
                print("是否重试：是")
                print("重试后SQL：", result.get("retry_sql", ""))

            if result.get("status") in ("query_ok", "analysis_ok", "empty_result"):
                success += 1
            else:
                print("错误：", result.get("message", ""))
        except Exception as e:
            print("执行异常：", e)

    print("\n===== 测试完成 =====")
    print(f"总用例数：{total}")
    print(f"成功数：{success}")
    print(f"成功率：{success / total:.2%}" if total else "无测试用例")


if __name__ == "__main__":
    main()
