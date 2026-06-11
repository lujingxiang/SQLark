import os
import sqlite3
from typing import Any, Dict, List, Optional

from app.db.schema import DB_PATH


def get_connection() -> sqlite3.Connection:
    return sqlite3.connect(DB_PATH)


def execute_query(sql: str) -> List[Dict[str, Any]]:
    """
    Execute a read-only SQL query and return rows as dictionaries.
    """
    cleaned_sql = sql.strip()
    if not cleaned_sql.lower().startswith("select"):
        raise ValueError("只允许执行 SELECT 查询")

    if ";" in cleaned_sql[:-1]:
        raise ValueError("禁止执行多条 SQL 语句")

    conn = get_connection()
    conn.row_factory = sqlite3.Row

    try:
        cursor = conn.cursor()
        cursor.execute(cleaned_sql)
        rows = cursor.fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def get_latest_trade_time() -> Optional[str]:
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT MAX(TradeTime) FROM StockData")
        row = cursor.fetchone()
        return row[0] if row and row[0] else None
    finally:
        conn.close()
