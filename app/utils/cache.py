"""工具结果内存缓存，TTL 到期后自动失效。

仅缓存结果稳定的工具（Schema、外部 API 模拟）；
SQL 查询类工具数据随时变化，不纳入缓存。
"""
from __future__ import annotations

import hashlib
import json
import time
from typing import Any, Optional

_store: dict[str, tuple[Any, float]] = {}

# 各工具的 TTL（秒）；不在此字典中的工具不缓存
_TTL_BY_TOOL: dict[str, int] = {
    "SchemaTool": 300,        # 5 分钟：表结构基本不变
    "MarketQuoteTool": 60,    # 1 分钟：模拟行情数据
    "NewsSentimentTool": 60,  # 1 分钟：模拟舆情数据
    "ExternalApiTool": 60,    # 1 分钟：模拟外部接口
}


def _key(tool_name: str, args: dict) -> str:
    payload = json.dumps({"t": tool_name, "a": args}, sort_keys=True, ensure_ascii=False)
    return hashlib.md5(payload.encode()).hexdigest()


def get(tool_name: str, args: dict) -> Optional[Any]:
    """取缓存；未命中或已过期返回 None。"""
    if tool_name not in _TTL_BY_TOOL:
        return None
    k = _key(tool_name, args)
    entry = _store.get(k)
    if not entry:
        return None
    value, expires_at = entry
    if time.time() > expires_at:
        del _store[k]
        return None
    return value


def put(tool_name: str, args: dict, result: Any) -> None:
    """写入缓存；工具不在 TTL 字典中时静默跳过。"""
    ttl = _TTL_BY_TOOL.get(tool_name)
    if ttl is None:
        return
    k = _key(tool_name, args)
    _store[k] = (result, time.time() + ttl)


def clear() -> None:
    """清空所有缓存（测试用）。"""
    _store.clear()


def size() -> int:
    return len(_store)
