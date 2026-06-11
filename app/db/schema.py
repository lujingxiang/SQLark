# schema.py

DB_PATH = r"D:/App_data/SQLark/data\DB\SQLark.db"


SCHEMA_TEXT = """
数据库名称: SQLark.db

表名: StockData
表说明: 股票5分钟行情数据表，用于存储某只股票在不同时间点的行情信息。

字段说明:
- Code: 股票代码，字符串，例如 300750
- Name: 股票名称，字符串，例如 宁德时代
- LatestPrice: 最新价，浮点数
- ChangeAmount: 涨跌额，浮点数
- ChangePercent: 涨跌幅，浮点数
- BuyPrice: 买入价，浮点数
- SellPrice: 卖出价，浮点数
- PrevClose: 昨收价，浮点数
- OpenPrice: 今开价，浮点数
- HighPrice: 最高价，浮点数
- LowPrice: 最低价，浮点数
- Volume: 成交量（手），整数
- Turnover: 成交额（万），浮点数
- TradeTime: 交易时间，字符串或日期时间类型，格式类似 2026-03-18 09:35:00

表名: StockData_15min
表说明: 股票15分钟聚合行情数据表，基于 StockData 的 5 分钟数据按 15 分钟区间聚合生成。

字段说明:
- Code: 股票代码，字符串
- Name: 股票名称，字符串
- TradeTime: 15分钟时间区间起点，格式类似 2026-03-18 09:30:00
- OpenPrice: 区间开盘价，浮点数
- HighPrice: 区间最高价，浮点数
- LowPrice: 区间最低价，浮点数
- ClosePrice: 区间收盘价，浮点数
- Volume: 区间成交量（手），整数
- Turnover: 区间成交额（万），浮点数

使用规则:
1. 只允许查询 StockData 或 StockData_15min 表
2. 默认使用 SQLite 语法
3. 时间排序通常使用 TradeTime
4. 查询最新数据时，使用 ORDER BY TradeTime DESC
5. 除非用户明确要求全部数据，否则建议加 LIMIT
"""

TABLES = {
    "StockData": {
        "description": "股票5分钟行情数据表",
        "fields": {
            "Code": "股票代码",
            "Name": "股票名称",
            "LatestPrice": "最新价",
            "ChangeAmount": "涨跌额",
            "ChangePercent": "涨跌幅",
            "BuyPrice": "买入价",
            "SellPrice": "卖出价",
            "PrevClose": "昨收",
            "OpenPrice": "今开",
            "HighPrice": "最高",
            "LowPrice": "最低",
            "Volume": "成交量（手）",
            "Turnover": "成交额（万）",
            "TradeTime": "交易时间"
        }
    },
    "StockData_15min": {
        "description": "股票15分钟聚合行情数据表",
        "fields": {
            "Code": "股票代码",
            "Name": "股票名称",
            "TradeTime": "15分钟时间区间起点",
            "OpenPrice": "区间开盘价",
            "HighPrice": "区间最高价",
            "LowPrice": "区间最低价",
            "ClosePrice": "区间收盘价",
            "Volume": "区间成交量（手）",
            "Turnover": "区间成交额（万）"
        }
    }
}


def get_schema_text() -> str:
    return SCHEMA_TEXT


def get_table_names() -> list[str]:
    return list(TABLES.keys())


def get_table_info(table_name: str) -> dict:
    return TABLES.get(table_name, {})