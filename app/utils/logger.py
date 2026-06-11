"""结构化日志辅助：记录工具调用、决策路径、节点耗时。"""
from __future__ import annotations

import logging

_logger = logging.getLogger("sqlark")


def log_tool_call(tool_name: str, args: dict, result: dict, elapsed_ms: float) -> None:
    ok = result.get("ok", False)
    err = result.get("error", "")
    count = result.get("count", "")
    parts = [f"tool={tool_name}", f"ok={ok}", f"elapsed_ms={elapsed_ms:.0f}"]
    if count != "":
        parts.append(f"count={count}")
    if err:
        parts.append(f"error={err}")
    _logger.info("TOOL_CALL %s", " ".join(parts))


def log_decision(decision: str, status: str, retry_count: int) -> None:
    _logger.info("DECISION next=%s status=%s retry=%d", decision, status, retry_count)
