"""SQL 执行器，整合安全检查与查询执行。"""

from __future__ import annotations

import sqlite3
from typing import Any, Optional

from app.db.schema import DB_PATH

FORBIDDEN_KEYWORDS = frozenset([
    "insert", "update", "delete", "drop", "alter",
    "truncate", "attach", "pragma", "create", "replace",
])


def _validate_sql(sql: str) -> tuple[bool, str]:
    """校验 SQL 安全性，返回 (是否安全, 原因)。"""
    sql_lower = sql.strip().lower()

    if sql_lower.startswith("--"):
        return False, "模型未能生成有效SQL"

    if not sql_lower.startswith("select"):
        return False, "SQL 不是 SELECT 查询"

    if ";" in sql_lower[:-1]:
        return False, "SQL 包含多条语句"

    for keyword in FORBIDDEN_KEYWORDS:
        if keyword in sql_lower:
            return False, f"SQL 包含危险关键字: {keyword}"

    return True, "OK"


def execute_sql(sql: str) -> list[dict[str, Any]]:
    """执行只读 SQL 查询，返回字典列表。"""
    cleaned_sql = sql.strip()
    if not cleaned_sql.lower().startswith("select"):
        raise ValueError("只允许执行 SELECT 查询")

    if ";" in cleaned_sql[:-1]:
        raise ValueError("禁止执行多条 SQL 语句")

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        cursor = conn.cursor()
        cursor.execute(cleaned_sql)
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()


def safe_execute(sql: str, *, allow_aggregate: bool = True) -> dict:
    """安全执行 SQL，返回统一格式结果。"""
    is_safe, reason = _validate_sql(sql)
    if not is_safe:
        return {"ok": False, "error": f"SQL校验失败: {reason}"}

    try:
        rows = execute_sql(sql)
        return {"ok": True, "count": len(rows), "rows": rows}
    except Exception as exc:
        return {"ok": False, "error": f"查询执行失败: {exc}"}


def safe_execute_aggregate(sql: str) -> dict:
    """安全执行聚合 SQL，返回聚合结果。"""
    is_safe, reason = _validate_sql(sql)
    if not is_safe:
        return {"ok": False, "error": f"聚合SQL校验失败: {reason}"}

    if not sql.strip().lower().startswith("select"):
        return {"ok": False, "error": "聚合SQL必须是 SELECT"}

    try:
        rows = execute_sql(sql)
        if not rows:
            return {"ok": False, "error": "聚合查询无结果"}
        return {"ok": True, "stats": rows[0]}
    except Exception as exc:
        return {"ok": False, "error": f"聚合执行失败: {exc}"}


def get_latest_trade_time() -> Optional[str]:
    """获取最新交易时间。"""
    conn = sqlite3.connect(DB_PATH)
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT MAX(TradeTime) FROM StockData")
        row = cursor.fetchone()
        return row[0] if row and row[0] else None
    finally:
        conn.close()
