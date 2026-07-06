# SQLark 前端接口文档

> 基准 URL：`http://127.0.0.1:8000`（可通过启动参数 `--port` 修改）

---

## 1. 页面入口

### `GET /`

返回前端主页面 HTML。

---

## 2. 静态资源

### `GET /static/{filename}`

返回 `static/` 目录下的静态文件（JS、图片等）。

示例：
```
GET /static/lightweight-charts.standalone.production.js
```

---

## 3. 同步聊天

### `POST /api/chat`

同步执行完整 agent 流程，等待所有节点执行完毕后一次性返回结果。网络异常或 SSE 不可用时作为 fallback。

**Request**

```json
{
  "question": "分析宁德时代最近10天的K线形态"
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `question` | string | 是 | 用户提问 |

**Response** `200 OK`

```json
{
  "question": "分析宁德时代最近10天的K线形态",
  "intent": "pattern",
  "plan": {
    "intent": "pattern",
    "field": "LatestPrice",
    "analysis_type": "pattern",
    "execution_mode": "tool",
    "limit": 10
  },
  "sql": "SELECT ...",
  "status": "query_ok",
  "message": "查询成功",
  "retried": false,
  "retry_sql": null,
  "retry_count": 0,
  "summary": "宁德时代近10天出现锤子线形态，短期支撑较强...",
  "thoughts": ["intent_node: 识别为形态分析", "..."],
  "observations": ["PatternAnalysis 返回 ok=True", "..."],
  "tool_history": [
    {
      "tool": "PatternAnalysis",
      "args": { "sql_query": "SELECT ..." },
      "result": { "ok": true, "pattern_result": {} },
      "from_cache": false
    }
  ],
  "tool_name": "PatternAnalysis",
  "tool_args": { "sql_query": "SELECT ..." },
  "tool_result": { "ok": true, "pattern_result": {} },
  "decision": "summarize",
  "query_result": {
    "ok": true,
    "rows": [{ "TradeTime": "2026-06-14", "LatestPrice": 123.45, "..." : "..." }],
    "count": 10
  },
  "analysis_result": null,
  "pattern_result": { "hammer": true, "support": 120.0 },
  "quant_result": null,
  "composite_signal": {
    "score": 45,
    "rating": "偏多",
    "signals": ["出现锤子线", "成交量放大"],
    "components": { "pattern": "bullish", "volume": "expanding" }
  },
  "backtest_result": {
    "strategy": "形态策略",
    "total_return": 8.32,
    "buy_and_hold_return": 5.1,
    "excess_return": 3.22,
    "max_drawdown": 4.5,
    "sharpe": 1.12,
    "win_rate": 62.5,
    "trade_count": 8,
    "win_count": 5,
    "loss_count": 3
  }
}
```

**错误响应**（`question` 为空）

```json
{ "error": "question 不能为空" }
```

---

## 4. SSE 流式聊天

### `POST /api/stream`

逐步推送 agent 各节点的执行结果，使用 [Server-Sent Events](https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events) 协议。每个事件对应 LangGraph 中的一个节点。

**Request**

```json
{
  "question": "分析宁德时代最近10天的K线形态",
  "stream_id": "lx3k9a2f"
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `question` | string | 是 | 用户提问 |
| `stream_id` | string | 否 | 客户端生成的唯一 ID，用于后续调用 `/api/abort` 中止本次流；不传则无法中止 |

**Response**：`Content-Type: text/event-stream`

每个 SSE 事件格式：

```
event: <node_name>
data: <JSON>

```

`data` 是**累积状态**（包含所有已执行节点的输出），字段结构与 `/api/chat` 响应相同。

**可能出现的 event 名称（按执行顺序）**

| event | 说明 |
|-------|------|
| `intent` | 意图识别完成 |
| `planner` | 任务规划完成 |
| `tool_selector` | 工具选择完成 |
| `tool_executor` | 工具执行完成 |
| `observation` | 结果观察完成 |
| `decision` | 决策完成 |
| `sql_generate` | SQL 生成完成（fallback 路径） |
| `sql_execute` | SQL 执行完成 |
| `sql_validate` | SQL 验证完成 |
| `analysis_dispatch` | 分析分发完成 |
| `basic_analysis` | 基础分析完成 |
| `pattern_analysis` | K线形态分析完成 |
| `volume_price_analysis` | 量价分析完成 |
| `volatility_analysis` | 波动率分析完成 |
| `summarize` | 结果汇总完成 |
| `done` | 全部完成，data 中 `status` 为 `"complete"` |
| `aborted` | 被 `/api/abort` 中止，data 为 `{"status": "aborted"}` |
| `error` | 执行异常，data 为 `{"error": "<message>"}` |

**示例事件序列**

```
event: intent
data: {"intent": "pattern", "status": "intent_ok", ...}

event: planner
data: {"intent": "pattern", "plan": {...}, ...}

event: tool_executor
data: {"tool_name": "PatternAnalysis", "tool_result": {...}, ...}

event: summarize
data: {"summary": "宁德时代近10天...", "status": "query_ok", ...}

event: done
data: {"status": "complete", "summary": "...", ...}
```

---

## 5. 中止流式请求

### `POST /api/abort`

中止正在进行的 SSE 流。后端收到请求后设置中止信号，流式线程在下一个节点执行前退出，客户端会收到 `event: aborted`。

**Request**

```json
{ "stream_id": "lx3k9a2f" }
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `stream_id` | string | 是 | 与 `/api/stream` 请求中相同的 ID |

**Response** `200 OK`

```json
{ "ok": true }
```

若 `stream_id` 不存在（已完成或从未注册）：

```json
{ "ok": false }
```

---

## 响应字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| `question` | string | 原始问题 |
| `intent` | string | 识别到的意图：`query` / `analysis` / `pattern` / `volume_price` / `volatility` / `chitchat` |
| `plan` | object\|null | 规划结果，含 `intent`、`field`、`analysis_type`、`execution_mode`、`limit` |
| `sql` | string\|null | 最终执行的 SQL（fallback 路径） |
| `status` | string | 执行状态，见下表 |
| `message` | string | 状态描述文本 |
| `retried` | bool | 是否经历 SQL 重试 |
| `retry_count` | int | ReAct 重试次数 |
| `summary` | string\|null | LLM 生成的最终回复文本 |
| `thoughts` | string[] | 各节点推理日志 |
| `observations` | string[] | 工具执行观察记录 |
| `tool_history` | object[] | 工具调用历史，每条含 `tool`、`args`、`result`、`from_cache` |
| `tool_name` | string\|null | 最后一次调用的工具名 |
| `tool_args` | object\|null | 最后一次工具入参 |
| `tool_result` | object\|null | 最后一次工具结果 |
| `decision` | string\|null | 决策节点输出：`summarize` / `tool_selector` / `sql_generate` |
| `query_result` | object\|null | 原始查询结果，含 `ok`、`rows`（数组）、`count` |
| `analysis_result` | object\|null | 基础分析结果，含 `stats` |
| `pattern_result` | object\|null | K线形态分析结果 |
| `quant_result` | object\|null | 量价/波动率分析结果 |
| `composite_signal` | object\|null | 综合信号评分，含 `score`（-100\~100）、`rating`、`signals`、`components` |
| `backtest_result` | object\|null | 策略回测结果，含 `total_return`、`excess_return`、`max_drawdown`、`sharpe`、`win_rate` 等 |

**`status` 枚举值**

| 值 | 含义 |
|----|------|
| `intent_ok` | 意图识别成功 |
| `tool_selected` | 工具已选择 |
| `tool_executed` | 工具已执行 |
| `query_ok` | 查询成功 |
| `analysis_ok` | 分析成功 |
| `analysis_error` | 分析失败（触发重试或 fallback） |
| `query_error` | 查询失败 |
| `tool_error` | 工具执行异常 |
| `tool_selection_failed` | 工具选择失败 |
| `tool_not_found` | 工具不存在 |
| `complete` | 全流程完成（仅 `done` 事件） |
| `aborted` | 被中止 |
