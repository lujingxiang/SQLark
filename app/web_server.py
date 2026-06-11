"""FastAPI Web 服务，支持 SSE 流式输出。"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

ROOT_DIR = Path(__file__).resolve().parents[1]
VENV_SITE_PACKAGES = ROOT_DIR / ".venv" / "Lib" / "site-packages"
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))
if VENV_SITE_PACKAGES.exists() and str(VENV_SITE_PACKAGES) not in sys.path:
    sys.path.insert(0, str(VENV_SITE_PACKAGES))

from app.graph.graph import get_graph

INDEX_HTML = ROOT_DIR / "static" / "index.html"

app = FastAPI(title="SQLark", version="2.0")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("sqlark")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    question: str


def _serialize_state(state: dict) -> dict:
    """将图状态序列化为可 JSON 化的字典。"""
    result = {
        "question": state.get("question"),
        "intent": state.get("intent"),
        "plan": state.get("plan"),
        "sql": state.get("sql"),
        "status": state.get("status"),
        "message": state.get("message"),
        "retried": state.get("retried", False),
        "retry_sql": state.get("retry_sql"),
        "retry_count": state.get("retry_count", 0),
        "summary": state.get("summary"),
        "thoughts": state.get("thoughts", []),
        "observations": state.get("observations", []),
        "tool_history": state.get("tool_history", []),
        "tool_name": state.get("tool_name"),
        "tool_args": state.get("tool_args"),
        "tool_result": state.get("tool_result"),
        "decision": state.get("decision"),
    }

    query_result = state.get("query_result")
    if query_result:
        result["query_result"] = query_result

    for key in ("analysis_result", "pattern_result", "quant_result"):
        value = state.get(key)
        if value:
            result[key] = value

    composite = state.get("composite_signal")
    if composite:
        result["composite_signal"] = composite

    backtest = state.get("backtest_result")
    if backtest:
        result["backtest_result"] = backtest

    return result


@app.get("/")
async def index():
    return FileResponse(INDEX_HTML)


@app.post("/api/chat")
async def chat(request: ChatRequest):
    """同步聊天接口。"""
    question = request.question.strip()
    if not question:
        logger.warning("Chat api failed: empty question")
        return {"error": "question 不能为空"}

    graph = get_graph()
    result = graph.invoke({"question": question})
    logger.info("Chat api: question=%s status=%s message=%s", question, result.get("status"), result.get("message"))
    return _serialize_state(result)


@app.post("/api/stream")
async def stream_chat(request: ChatRequest):
    """SSE 流式聊天接口，逐步推送图执行过程。"""
    question = request.question.strip()
    if not question:
        async def error_gen():
            yield {"event": "error", "data": json.dumps({"error": "question 不能为空"}, ensure_ascii=False)}
        return EventSourceResponse(error_gen())

    graph = get_graph()

    async def event_generator():
        loop = asyncio.get_event_loop()

        def _run_stream():
            """在独立线程中运行同步的 graph.stream，避免阻塞事件循环。"""
            return list(graph.stream({"question": question}))

        events = await loop.run_in_executor(None, _run_stream)

        # 累积完整状态，确保每个事件都包含所有节点的输出
        accumulated_state: dict = {}

        for event in events:
            for node_name, state_update in event.items():
                if isinstance(state_update, dict):
                    accumulated_state.update(state_update)

                yield {
                    "event": node_name,
                    "data": json.dumps(
                        _serialize_state(accumulated_state),
                        ensure_ascii=False, default=str,
                    ),
                }

        logger.info("Stream api completed: question=%s status=%s message=%s", question, accumulated_state.get("status"), accumulated_state.get("message"))
        yield {"event": "done", "data": json.dumps({**accumulated_state, "status": "complete"}, ensure_ascii=False, default=str)}

    return EventSourceResponse(event_generator())


def run_web_server(host: str = "127.0.0.1", port: int = 8000) -> None:
    """启动 Web 服务。"""
    import uvicorn
    print(f"SQLark Web UI running at http://{host}:{port}")
    uvicorn.run(app, host=host, port=port, log_level="info")
