# Personal Technical Blog

## SQLark —— 用自然语言问股票

最近做了个小项目，想解决一个很具体的问题：看股票数据太麻烦了，每次都得手动跑 SQL 或者翻 Excel，能不能直接用中文问？

于是就有了 SQLark。核心思路不复杂，用 LangGraph 搭了个状态机，让 LLM 先判断你在问啥，再决定是去查数据库还是跑量化分析。问"最近有没有放量突破"这种问题，它会自动跑量价分析、算 RSI、MACD，还顺带帮你回测了一下 MA 金叉策略效果如何。结果直接在网页上用图表展示，K 线、指标子图一起出来。

整体下来感觉 LangGraph 挺好用的，把复杂的多步骤流程拆成一个个节点，逻辑清晰很多。

## 核心功能点

| 功能 | 说明 |
|------|------|
| 自然语言转 SQL | LLM Tool Calling 识别意图，自动生成 SQLite 查询，SELECT-only 安全校验 |
| 6 类意图路由 | query / analysis / pattern / volume_price / volatility / chitchat，各走独立分析链路 |
| K 线形态识别 | 锤子线、吞没形态、启明星、十字星、缺口等，叠加均线交叉与支撑压力位检测 |
| 技术指标计算 | MACD（EMA12/26/9）、RSI（Wilder 平滑，14期）、Bollinger Bands（MA20 ± 2σ） |
| 量价关系分析 | 量价背离、放量突破、OBV 能量潮、换手率异常、缩量盘整 |
| 波动率与风险 | 历史波动率、ATR、偏度/峰度、VaR（95%/99%）、最大回撤、波动率锥 |
| 综合信号评分 | 聚合 7 个维度输出 [-100, +100] 评分与多空评级 |
| 策略回测 | MA5/MA20 金叉策略，输出超额收益、最大回撤、Sharpe、胜率，对比买入持有基准 |
| ReAct 容错循环 | 工具执行失败自动重试（上限 3 次），超限降级走 SQL 兜底路径 |
| SSE 流式输出 | 每个 LangGraph 节点完成后立即推送，前端首屏无需等待全链路结束 |
| 前端指标子图 | RSI / MACD 子图挂载于 K 线图下方，数据在浏览器本地计算，零额外接口 |
| 工具缓存 | Schema 缓存 5min，外部 API 缓存 1min，SQL 查询不缓存 |

---

## 架构是怎么跑起来的

整个系统基于 LangGraph 编译了一个 `StateGraph`，所有节点共享同一个 `AgentState` TypedDict，状态在节点间单向流动，不存在隐式的全局变量。

主路径是一个标准的 **ReAct 循环**：`intent_node` 用 LLM Tool Calling 做意图分类（6 类），命中量化意图后进 `planner_node` 生成结构化执行计划，再由 `tool_selector_node` 选具体工具、`tool_executor_node` 带 20 秒超时保护地执行，`observation_node` 将结果写回状态，`decision_node` 判断是否继续重试。重试上限 3 次，超限后降级走 SQL 生成兜底路径（`sql_generate_node → sql_execute_node → sql_validate_node`），最终汇入 `summarize_node`。

量化分析是整个项目技术密度最高的部分。三条分析支路（pattern / volume_price / volatility）共用同一套指标底层：MACD（EMA12/26 + 9日信号线）、RSI（Wilder 平滑，14期）、Bollinger Bands（MA20 ± 2σ）。在此基础上，`calc_composite_signal()` 聚合 K 线形态、均线交叉、量价背离等 7 个维度，输出 [-100, +100] 的综合评分。量价和波动率分析还会调用 `backtest_ma_cross()`，跑 MA5/MA20 金叉策略回测，输出超额收益、最大回撤、逐笔 Sharpe 和胜率，与买入持有基准做对比。

工具层抽象了 `DataSourcePlugin` 接口，SQLite、模拟行情、模拟舆情三种数据源可插拔替换，稳定工具结果走 TTL 缓存（Schema 5min，外部 API 1min），SQL 查询不缓存。

Web 层用 FastAPI + SSE 做流式推送，每个 LangGraph 节点完成后立即向前端推送当前累积状态，首屏响应无需等待全链路结束。前端 RSI/MACD 子图在浏览器本地计算序列数据，不新增任何后端接口。
