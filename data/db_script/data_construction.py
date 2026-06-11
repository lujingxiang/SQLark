import sqlite3
import random
from datetime import datetime, timedelta

DB_PATH = r"D:\App_data\SQLark\DB\SQLark.db"
TABLE_NAME = "StockData"

def ensure_table(conn):
    conn.execute(f"""
    CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
        Code TEXT PRIMARY KEY,
        Name TEXT,
        LatestPrice REAL,
        ChangeAmount REAL,
        ChangePercent REAL,
        BuyPrice REAL,
        SellPrice REAL,
        PrevClose REAL,
        OpenPrice REAL,
        HighPrice REAL,
        LowPrice REAL,
        Volume INTEGER,
        Turnover REAL,
        TradeTime TEXT
    )
    """)
    conn.commit()

def generate_data(n=1000):
    rows = []

    stock_code = "300750"
    stock_name = "宁德时代"

    # 从当前时间往前推，生成1000条5分钟级别数据
    start_time = datetime.now() - timedelta(minutes=5 * (n - 1))

    prev_close = 182.50

    for i in range(n):
        trade_time = start_time + timedelta(minutes=5 * i)

        open_price = round(prev_close + random.uniform(-1.5, 1.5), 2)
        high_price = round(open_price + random.uniform(0, 2.5), 2)
        low_price = round(open_price - random.uniform(0, 2.5), 2)

        if low_price < 0:
            low_price = 0.01

        latest_price = round(random.uniform(low_price, high_price), 2)
        change_amount = round(latest_price - prev_close, 2)
        change_percent = round((change_amount / prev_close) * 100, 2) if prev_close != 0 else 0

        buy_price = round(latest_price - random.uniform(0, 0.5), 2)
        sell_price = round(latest_price + random.uniform(0, 0.5), 2)

        volume = random.randint(1000, 500000)   # 成交量/手
        turnover = round(volume * latest_price / 10000, 2)  # 成交额/万

        # 为了让主键不冲突，这里用 代码_时间 作为唯一主键值
        code = f"{stock_code}_{trade_time.strftime('%Y%m%d%H%M')}"

        rows.append((
            code,
            stock_name,
            latest_price,
            change_amount,
            change_percent,
            buy_price,
            sell_price,
            prev_close,
            open_price,
            high_price,
            low_price,
            volume,
            turnover,
            trade_time.strftime("%Y-%m-%d %H:%M:%S")
        ))

        prev_close = latest_price

    return rows

def insert_data(conn, rows):
    conn.executemany(f"""
    INSERT INTO {TABLE_NAME} (
        Code, Name, LatestPrice, ChangeAmount, ChangePercent,
        BuyPrice, SellPrice, PrevClose, OpenPrice, HighPrice, LowPrice,
        Volume, Turnover, TradeTime
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, rows)
    conn.commit()

def main():
    conn = sqlite3.connect(DB_PATH)
    try:
        ensure_table(conn)
        rows = generate_data(1000)
        insert_data(conn, rows)
        print(f"成功插入 {len(rows)} 条数据到 {TABLE_NAME}")
    finally:
        conn.close()

if __name__ == "__main__":
    main()