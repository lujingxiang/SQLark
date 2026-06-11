"""
生成特斯拉 (TSLA) 模拟 5 分钟行情数据，插入 StockData 表。
- 5000 条，从今天向前推算交易日（美股 9:30-16:00 ET，78 根/天）
- 价格用几何布朗运动模拟，参数参考 TSLA 历史波动率
"""

from __future__ import annotations

import math
import random
import sqlite3
from datetime import date, datetime, timedelta

DB_PATH = r"D:/App_data/SQLark/data/DB/SQLark.db"

CODE = "TSLA"
NAME = "特斯拉"
TARGET_ROWS = 5000

# TSLA 参数
START_PRICE = 285.0       # 起始收盘价（USD）
DAILY_VOL = 0.030         # 日波动率 3%
DAILY_DRIFT = 0.0001      # 微小正漂移
BAR_PER_DAY = 78          # 9:30~15:55，每 5 分钟一根
AVG_DAILY_VOLUME = 90_000_000   # 日均成交量（股）


def is_trading_day(d: date) -> bool:
    """简单判断：排除周末（不处理美国节假日）。"""
    return d.weekday() < 5


def trading_days_before(end: date, n: int) -> list[date]:
    """从 end 向前取 n 个交易日，返回从早到晚排序。"""
    days = []
    cur = end
    while len(days) < n:
        if is_trading_day(cur):
            days.append(cur)
        cur -= timedelta(days=1)
    return list(reversed(days))


def bar_timestamps(d: date) -> list[datetime]:
    """生成当天 78 根 5 分钟 K 线的时间戳（9:30-15:55 ET）。"""
    bars = []
    t = datetime(d.year, d.month, d.day, 9, 30)
    for _ in range(BAR_PER_DAY):
        bars.append(t)
        t += timedelta(minutes=5)
    return bars


def simulate_day(open_price: float, daily_vol: float) -> list[dict]:
    """模拟一天 78 根 K 线，返回 dict 列表。"""
    intraday_vol = daily_vol / math.sqrt(BAR_PER_DAY)
    price = open_price
    rows = []

    # 日内成交量按 U 型分布（开盘/收盘量大）
    weights = []
    for i in range(BAR_PER_DAY):
        pos = i / (BAR_PER_DAY - 1)
        w = 1.5 - math.cos(pos * math.pi)  # U 型权重 0.5~2.5
        weights.append(w)
    total_w = sum(weights)

    prev_close = open_price
    for i in range(BAR_PER_DAY):
        # 几何布朗运动
        r = random.gauss(DAILY_DRIFT / BAR_PER_DAY, intraday_vol)
        new_price = price * math.exp(r)

        bar_open = price
        bar_close = new_price
        high = max(bar_open, bar_close) * (1 + abs(random.gauss(0, intraday_vol * 0.4)))
        low = min(bar_open, bar_close) * (1 - abs(random.gauss(0, intraday_vol * 0.4)))

        bar_vol = int(AVG_DAILY_VOLUME * weights[i] / total_w * random.uniform(0.85, 1.15))
        turnover = round(bar_close * bar_vol / 10000, 2)  # 万 USD

        spread = round(bar_close * 0.0002, 2)
        buy_price = round(bar_close - spread, 2)
        sell_price = round(bar_close + spread, 2)

        change_amount = round(bar_close - prev_close, 4)
        change_pct = round(change_amount / prev_close * 100, 4) if prev_close else 0

        rows.append({
            "open": round(bar_open, 4),
            "high": round(high, 4),
            "low": round(low, 4),
            "close": round(bar_close, 4),
            "buy": buy_price,
            "sell": sell_price,
            "prev_close": round(prev_close, 4),
            "change_amount": change_amount,
            "change_pct": change_pct,
            "volume": bar_vol,
            "turnover": turnover,
        })

        prev_close = bar_close
        price = new_price

    return rows


def main():
    random.seed(42)

    # 需要多少天
    days_needed = math.ceil(TARGET_ROWS / BAR_PER_DAY)  # 65 天
    today = date(2026, 5, 29)
    trade_days = trading_days_before(today, days_needed)

    # 从最早一天往前推算每天开盘价（从 START_PRICE 向前随机游走）
    day_opens = [START_PRICE]
    for _ in range(len(trade_days) - 1):
        prev = day_opens[0]
        r = random.gauss(DAILY_DRIFT, DAILY_VOL)
        day_opens.insert(0, round(prev * math.exp(-r), 4))

    # 生成所有 K 线
    all_bars: list[tuple] = []
    for day, open_price in zip(trade_days, day_opens):
        timestamps = bar_timestamps(day)
        day_rows = simulate_day(open_price, DAILY_VOL)
        for ts, row in zip(timestamps, day_rows):
            all_bars.append((
                CODE,
                NAME,
                row["close"],
                row["change_amount"],
                row["change_pct"],
                row["buy"],
                row["sell"],
                row["prev_close"],
                row["open"],
                row["high"],
                row["low"],
                row["volume"],
                row["turnover"],
                ts.strftime("%Y-%m-%d %H:%M:%S"),
            ))

    # 取最新 5000 条
    all_bars = all_bars[-TARGET_ROWS:]

    # 插入 SQLite
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # 先清除旧的 TSLA 数据（如有）
    cursor.execute("DELETE FROM StockData WHERE Code = ?", (CODE,))
    deleted = cursor.rowcount

    cursor.executemany(
        """INSERT INTO StockData
           (Code, Name, LatestPrice, ChangeAmount, ChangePercent,
            BuyPrice, SellPrice, PrevClose, OpenPrice, HighPrice,
            LowPrice, Volume, Turnover, TradeTime)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        all_bars,
    )
    conn.commit()

    cursor.execute("SELECT COUNT(*) FROM StockData WHERE Code = ?", (CODE,))
    count = cursor.fetchone()[0]
    conn.close()

    if deleted:
        print(f"已清除旧 TSLA 数据 {deleted} 条")
    print(f"成功插入 {count} 条 TSLA 数据")
    print(f"时间范围：{all_bars[0][13]} ~ {all_bars[-1][13]}")
    print(f"价格范围：${min(b[2] for b in all_bars):.2f} ~ ${max(b[2] for b in all_bars):.2f}")


if __name__ == "__main__":
    main()
