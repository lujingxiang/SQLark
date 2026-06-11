# Dev Log

## 2026-06-07 Bug Fix：ReAct 路径量化结果双层嵌套

`observation_node` 将工具返回 `{"ok": True, "quant_result": {...}}` 整体赋给状态，导致前端拿到双层嵌套数据，实际分析内容无法渲染。同步修复了 ReAct 路径下 `composite_signal` 和 `backtest_result` 未提升到状态顶层的问题。修复：解包取 `tool_result.get(result_field, {})`，并在成功时提升两个字段。

---

## 2026-06-07 Bug Fix：SQLite 不支持 STDDEV

提问"波动情况"时 LLM 生成含 `STDDEV()` 的 SQL，SQLite 不支持导致连续报错。在 `agent_system`、`nl2sql_system`、`tool_selection_system` 三处提示词中明确禁用该函数，并引导波动计算走 `PythonDataAnalysis` 工具。

---

## 2026-06-07 量化特征深化（Step 1–5）

**目标：** 将量化分析模块从指标展示升级为"指标计算 → 综合评分 → 策略回测"完整链路。

### 后端（`quant_analysis.py` / `pattern.py`）
- 新增 MACD、RSI（Wilder平滑）、布林带三个指标函数
- 新增 `calc_composite_signal()`：聚合 K线形态、均线交叉、RSI、MACD、布林带、量价背离、放量突破 7 个维度，输出 [-100, +100] 评分与评级
- 新增 `backtest_ma_cross()`：MA5/MA20 金叉策略回测，输出总收益率、买入持有对比、超额收益、最大回撤、Sharpe、胜率
- `run_volume_price_analysis` 和 `run_volatility_analysis` 均接入上述指标与回测

### 图状态（`state.py` / `nodes.py` / `web_server.py`）
- `AgentState` 新增 `composite_signal`、`backtest_result` 字段
- 三个量化节点（pattern / volume_price / volatility）将两个字段提升至状态顶层并序列化输出

### 前端（`index.html`）
- 新增综合评分卡：彩色进度条 + 评级标签 + 信号列表
- 新增 RSI(14) 子图：紫色折线 + 30/70 分界线，120px
- 新增 MACD(12,26,9) 子图：DIF/DEA 折线 + 绿红柱，100px
- 新增回测卡片：超额收益、最大回撤、Sharpe、胜率、策略 vs 买入持有对比
- 所有子图从 `query_result.rows` 前端本地计算，无额外接口
