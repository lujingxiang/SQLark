# SQLark 全量测试报告

> 测试时间：2026-05-08  
> 测试用例：20 个，难度 ★~★★★★★★  
> 数据库：1000 条宁德时代 5 分钟行情数据

---

## 一、总体数据

| 指标 | 结果 |
|------|------|
| 执行成功率 | **20/20 (100%)** |
| 意图匹配率 | **15/20 (75%)** |
| 空结果率 | **8/20 (40%)** |
| 平均耗时 | **5.4s** |
| SQL 自纠重试 | 0 次（无 SQL 错误触发） |

---

## 二、逐条结果

| # | 问题 | 期望意图 | 实际意图 | 状态 | 数据行 | 耗时 |
|---|------|---------|---------|------|--------|------|
| 1 | 查看最新的5条股票数据 | query | query ✅ | query_ok | 5 | 2.1s |
| 2 | 今天开盘价是多少 | query | query ✅ | empty_result | 0 | 6.9s |
| 3 | 最近一条数据的成交量是多少 | query | query ✅ | query_ok | 1 | 1.9s |
| 4 | 显示昨天所有的行情数据 | query | query ✅ | empty_result | 0 | 2.9s |
| 5 | 最近7天的平均成交量是多少 | analysis | analysis ✅ | empty_result | 0 | 2.5s |
| 6 | 今天最高价和最低价分别是多少 | analysis | **query** ❌ | empty_result | 0 | 5.1s |
| 7 | 统计一下总共有多少条行情数据 | analysis | analysis ✅ | analysis_ok | 0 | 3.9s |
| 8 | 分析一下最近3天价格的趋势 | analysis | analysis ✅ | empty_result | 0 | 3.4s |
| 9 | 最近有没有出现锤子线形态 | pattern | pattern ✅ | empty_result | 0 | 2.1s |
| 10 | 分析最近的K线形态，看看有没有吞没形态 | pattern | pattern ✅ | analysis_ok | 10 | 13.3s |
| 11 | 5日均线和10日均线有没有金叉或死叉 | pattern | **query** ❌ | query_ok | 1 | 5.5s |
| 12 | 最近的支撑位和压力位在哪里 | pattern | pattern ✅ | analysis_ok | 1 | 5.0s |
| 13 | 最近有没有量价背离的情况 | volume_price | volume_price ✅ | analysis_ok | 100 | 8.5s |
| 14 | 分析一下最近的放量突破和缩量盘整 | volume_price | volume_price ✅ | analysis_ok | 100 | 13.6s |
| 15 | OBV指标最近的表现如何 | volume_price | volume_price ✅ | analysis_ok | 100 | 9.1s |
| 16 | 最近换手率有没有异常 | volume_price | **query** ❌ | query_ok | 1 | 3.9s |
| 17 | 计算最近的历史波动率 | volatility | volatility ✅ | analysis_ok | 1 | 6.0s |
| 18 | 分析一下ATR和最大回撤 | volatility | **query** ❌ | query_ok | 1000 | 2.2s |
| 19 | 综合分析最近的K线形态、量价关系和波动率 | pattern | **analysis** ❌ | analysis_ok | 100 | 7.2s |
| 20 | 最近三天市场波动加大了吗？从波动率、量价关系和价格形态三个角度分析 | volatility | volatility ✅ | empty_result | 0 | 3.1s |

---

## 三、按类别统计

| 类别 | 成功率 | 意图匹配 | 典型问题 |
|------|--------|---------|---------|
| 基础查询 | 3/3 (100%) | 3/3 | - |
| 基础查询(时间) | 1/1 (100%) | 1/1 | 时间条件产生空结果 |
| 聚合分析 | 3/3 (100%) | 2/3 | Q6 "最高价和最低价" 被误判为查询 |
| 趋势分析 | 1/1 (100%) | 1/1 | `datetime('now')` 时区问题 |
| K线形态 | 2/2 (100%) | 2/2 | - |
| 均线交叉 | 1/1 (100%) | 0/1 | Q11 LLM 未识别"金叉/死叉" |
| 支撑压力 | 1/1 (100%) | 1/1 | SQL 只取1行，分析不充分 |
| 量价背离 | 1/1 (100%) | 1/1 | - |
| 放量/缩量 | 1/1 (100%) | 1/1 | - |
| OBV指标 | 1/1 (100%) | 1/1 | - |
| 换手率异常 | 1/1 (100%) | 0/1 | Q16 LLM 未识别"换手率" |
| 历史波动率 | 1/1 (100%) | 1/1 | SQL 只取1行，无法计算 |
| ATR/回撤 | 1/1 (100%) | 0/1 | Q18 LLM 未识别"ATR" |
| 综合分析 | 2/2 (100%) | 1/2 | 不支持多意图 |

---

## 四、短板分析

### 🔴 短板 1：时区问题导致 40% 空结果（最严重）

**现象**：8 个用例返回 `empty_result`，其中 6 个是时间条件导致。

**根因**：LLM 生成 SQL 使用 `datetime('now')`，这是 UTC 时间。而数据库中的 `TradeTime` 是北京时间 (CST, UTC+8)。当 LLM 生成如下 SQL 时：

```sql
-- LLM 生成的（UTC）
SELECT * FROM StockData WHERE TradeTime >= datetime('now', '-7 days')

-- 实际需要（CST）
SELECT * FROM StockData WHERE TradeTime >= datetime('now', '+8 hours', '-7 days')
```

在当前测试环境（数据库最新数据是 2026-03-18），`datetime('now')` 返回的是 2026-05-08 UTC，而数据截止到 2026-03-18，因此所有"最近 N 天"的查询全部空结果。

**修复建议**：
1. 在 `sql_generate_node` 的 `extra_rule` 中注入当前数据库最新时间：`当前数据库最新交易时间为 {latest_trade_time}，请基于此时间计算时间范围，不要使用 datetime('now')`
2. 在 `sql_executor.py` 中对 SQL 后处理，自动替换 `datetime('now')` 为实际最新时间

---

### 🔴 短板 2：意图识别对专业术语覆盖不足

**现象**：5 个意图不匹配中，4 个是 LLM Tool Calling 未选择正确的工具。

| 问题 | 期望 | 实际 | 原因 |
|------|------|------|------|
| Q6: 最高价和最低价 | analysis | query | "最高/最低"被理解为查询而非聚合 |
| Q11: 金叉/死叉 | pattern | query | LLM 不认识"金叉/死叉"专业术语 |
| Q16: 换手率异常 | volume_price | query | LLM 不认识"换手率"属于量价 |
| Q18: ATR和最大回撤 | volatility | query | LLM 不认识"ATR"属于波动率 |

**根因**：Tool Calling 的工具描述（`PatternAnalysis`, `VolatilityAnalysis` 等）中没有列举足够的触发词。LLM 遇到不熟悉的专业术语时，会退回到最安全的 `QueryRawStockData`。

**修复建议**：
1. 在各 Tool Schema 的 `description` 中增加更多触发词，如：
   - `PatternAnalysis`：增加"金叉、死叉、均线交叉、均线突破"
   - `VolatilityAnalysis`：增加"ATR、平均真实范围、最大回撤、回撤、在险价值"
   - `VolumePriceAnalysis`：增加"换手率、量能异常、资金流向"
2. 在 `agent_system` 提示词中增加意图-关键词映射说明
3. 强化规则兜底：`_rule_based_intent` 中补充"金叉/死叉" → pattern，"ATR/回撤" → volatility，"换手率" → volume_price

---

### 🟡 短板 3：量化分析 SQL 取数不足

**现象**：Q12、Q17 的 SQL 只取了 1 行数据，导致形态分析和波动率分析无法生效。

| 问题 | SQL | 取数行 | 后果 |
|------|-----|--------|------|
| Q12: 支撑位和压力位 | `SELECT LowPrice, HighPrice ... LIMIT 1` | 1 | 需至少 3 条才能分析 |
| Q17: 历史波动率 | `SELECT LatestPrice ... LIMIT 1` | 1 | 需至少 20+ 条才能计算 |

**根因**：LLM 对量化分析需要多少数据缺乏认知，默认只取 1 条。`sql_generate_node` 的 `extra_rule` 虽然有 `LIMIT {limit}` 提示，但 Tool Calling 生成 SQL 时绕过了这个限制。

**修复建议**：
1. 在 `PatternAnalysis`、`VolatilityAnalysis`、`VolumePriceAnalysis` 的 schema `description` 中明确写明"SQL 查询必须返回至少 20 条数据，建议 LIMIT 50~200"
2. 在 `sql_execute_node` 中增加数据量检查：如果意图是量化分析但取数 < 10 行，自动调大 LIMIT 重新执行

---

### 🟡 短板 4：不支持多意图综合分析

**现象**：Q19 提到"K线形态、量价关系和波动率"，但系统只能路由到一个分析节点，最终走了 `analysis`（基础分析）。

**根因**：当前图结构是单意图路由，`route_analysis_dispatch` 只能选一个节点。用户要求多维度分析时，系统无法同时调用多个分析节点并汇总。

**修复建议**：
1. 在 `intent_node` 中新增 `IntentType.COMPREHENSIVE`（综合分析），当检测到多个意图关键词时触发
2. 新增 `comprehensive_node`，内部依次调用 `run_pattern_analysis` + `run_volume_price_analysis` + `run_volatility_analysis`，然后汇总
3. 或者改造图为"扇出-汇聚"模式：一个意图分发到多个并行分析节点，最后在 `summarize` 汇总

---

### 🟡 短板 5：总结质量不稳定

**现象**：
- 查询类结果总结过于简单（"查询成功，共返回 5 条数据"），没有对数据内容做解读
- Q12 "支撑位和压力位"的分析结论是"数据不足无法分析"，但实际取了 1 行且没有尝试取更多
- 分析总结依赖 LLM 生成，耗时占比大（Q10 耗时 13.3s，其中总结约占 8s）

**修复建议**：
1. 查询类结果增加简单的统计摘要（最高/最低/平均）
2. 当量化分析因数据不足失败时，自动尝试扩大查询范围
3. 考虑用模板化总结替代 LLM 总结，降低延迟

---

### 🟢 亮点

| 维度 | 表现 |
|------|------|
| 基础查询 | 意图识别准确，SQL 生成正确 |
| 量价分析 | 3/4 意图正确，分析结论专业（"顶背离信号"） |
| K线形态 | 识别吞没形态、乌云盖顶、锤子线等，结论可信 |
| SQL 自纠 | 无 SQL 语法错误，未触发重试 |
| 系统稳定性 | 20/20 无异常，零 crash |

---

## 五、优先修复清单

| 优先级 | 短板 | 预计收益 | 难度 |
|--------|------|---------|------|
| P0 | 时区/时间基准问题 | 消除 40% 空结果 | 低 |
| P0 | 意图识别补充专业术语 | 提升 20% 意图匹配 | 低 |
| P1 | 量化分析 SQL 取数下限 | 提升分析成功率 | 中 |
| P2 | 多意图综合分析 | 支持复杂问题 | 中 |
| P3 | 总结质量优化 | 提升用户体验 | 中 |
