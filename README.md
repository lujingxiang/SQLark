# SQLark

> 自然语言驱动的股票数据查询与量化分析智能体

用中文提问，SQLark 自动完成意图识别 → 工具调度 → SQL 生成执行 → 量化分析 → 图表渲染全流程。

![截图](images/屏幕截图%202026-06-07%20231500.png)

---

## 功能

| 意图 | 示例提问 | 输出 |
|------|---------|------|
| 原始查询 | 查询宁德时代最新 50 条 K 线 | K 线图 + 数据表格 |
| 统计分析 | 分析特斯拉近 100 条数据的波动情况 | 统计卡片 + 趋势结论 |
| K 线形态 | 识别宁德时代近 80 条 K 线的形态特征 | K 线图 + RSI/MACD + 综合评分 |
| 量价关系 | 分析宁德时代近 100 条数据的量价关系 | K 线图 + 指标子图 + 回测卡片 |
| 波动率 | 计算特斯拉近 150 条数据的历史波动率和最大回撤 | K 线图 + 指标子图 + 风险报告 |
| 闲聊 | 你好 | 文字回复 |

---

## 技术栈

- **智能体框架** — LangGraph StateGraph（ReAct 循环 + SQL 回退路径）
- **LLM** — 智谱 GLM-4-Flash（工具调用 + NL2SQL）
- **后端** — FastAPI + SSE 流式推送
- **数据库** — SQLite（宁德时代 300750 / 特斯拉 TSLA，5 分钟 K 线，约 2 万条）
- **前端** — Vanilla JS + LightweightCharts（K 线 / RSI / MACD / 布林带）

---

## 快速启动

**1. 安装依赖**

```bash
pip install -r requirements.txt
```

**2. 配置 API Key**

在 `configs/.env` 写入：

```
ZAI_API_KEY=your_zhipu_api_key
```

**3. 启动**

```bash
# Web UI（访问 http://127.0.0.1:8000）
python app/main.py --web

# CLI 交互模式
python app/main.py
```

**4. 运行测试**

```bash
python -m unittest test.test_baseline test.test_advanced
```

> **注意：** `app/db/schema.py` 中 `DB_PATH` 为绝对路径，移动项目后需手动更新。

---

## 项目结构

```
SQLark/
├── app/
│   ├── config/        # YAML 配置（提示词、意图关键词、Few-shot 示例）
│   ├── db/            # SQLite 工具与 schema
│   ├── graph/         # LangGraph 节点与状态定义
│   ├── llm/           # LLM 单例封装
│   ├── tools/         # 9 个工具（数据查询/聚合/分析/形态/量价/波动率等）
│   ├── utils/         # TTL 缓存等工具函数
│   ├── main.py        # 入口（CLI / Web 两用）
│   └── web_server.py  # FastAPI 服务
├── configs/           # .env / prompts.yaml / semantic.yaml / examples.yaml
├── data/DB/           # SQLark.db 数据文件
├── static/            # 前端单页 index.html
└── test/              # 单元测试 & 批量测试
```

---

## 执行流程

```
意图识别 → 规划 → 工具选择 → 工具执行 → 观测 → 决策
                                                  ├─ 成功 → 汇总
                                                  ├─ 重试 → 工具选择（最多循环）
                                                  └─ 失败 → SQL 生成 → SQL 执行 → 校验 → 分析 → 汇总
```

SQL 校验层自动拦截非 `SELECT` 语句，支持最多 3 次自动重试。

---

## License

MIT
