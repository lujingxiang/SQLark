"""统一 LLM 调用模块。"""

from __future__ import annotations

import os

import httpx
from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from app.tools.agent_tools import build_langchain_tools

_ENV_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "configs", ".env")
load_dotenv(dotenv_path=_ENV_PATH)

_HTTP_CLIENT = httpx.Client(timeout=30.0, trust_env=False)

_LLM_INSTANCE: ChatOpenAI | None = None


def get_llm() -> ChatOpenAI:
    """获取单例 LLM 实例。"""
    global _LLM_INSTANCE
    if _LLM_INSTANCE is not None:
        return _LLM_INSTANCE

    api_key = os.getenv("ZAI_API_KEY")
    if not api_key:
        raise ValueError("未找到 ZAI_API_KEY，请检查 configs/.env 是否配置正确")

    _LLM_INSTANCE = ChatOpenAI(
        model="glm-4-flash",
        temperature=0,
        openai_api_key=api_key,
        openai_api_base="https://open.bigmodel.cn/api/paas/v4/",
        http_client=_HTTP_CLIENT,
    )
    return _LLM_INSTANCE


def invoke_llm(system_prompt: str, human_prompt: str) -> str:
    """调用 LLM 并返回文本结果。"""
    llm = get_llm()
    response = llm.invoke([
        SystemMessage(content=system_prompt),
        HumanMessage(content=human_prompt),
    ])
    return response.content.strip()


def invoke_with_tools(system_prompt: str, human_prompt: str, tools: list) -> tuple[str, list[dict[str, any]]]:
    """调用 LLM 并支持工具调用，返回文本结果和工具调用记录。"""
    llm = get_llm()
    llm_with_tools = llm.bind_tools(tools)
    result = llm_with_tools.invoke([
        SystemMessage(content=system_prompt),
        HumanMessage(content=human_prompt),
    ])

    tool_calls = []
    raw_calls = []
    if hasattr(result, "tool_calls") and result.tool_calls:
        raw_calls = result.tool_calls
    elif hasattr(result, "tool_call") and result.tool_call:
        raw_calls = [result.tool_call]

    for call in raw_calls:
        if isinstance(call, dict):
            name = call.get("name")
            args = call.get("arguments") or call.get("args") or {}
        else:
            name = getattr(call, "name", None)
            args = getattr(call, "arguments", None) or getattr(call, "args", None) or {}
        if name:
            tool_calls.append({"name": name, "args": args})

    content = result.content.strip() if result.content else ""
    return content, tool_calls
