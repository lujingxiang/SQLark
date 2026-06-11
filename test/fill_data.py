"""数据补齐脚本：从最后一条数据(2026-03-18 11:49:13)补齐到 2026-05-08 16:01:13。

时间规律：
  - 5分钟间隔，秒数固定 :13
  - 每天 00:04:13 ~ 23:59:13，共 288 条/天
  - 含周末（原数据 3/15 是周日，3/16 是周一，说明不做交易日过滤）

模拟策略：
  - 价格：几何布朗运动(GBM)，基于宁德时代真实波动率参数
  - 成交量：对数正态分布 + 日内U型模式（开盘收盘高、午间低）
  - 其他字段：基于 LatestPrice 推导
"""

from __future__ import annotations

import math
import random
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

DB_PATH = Path(__file__).resolve().parents[1] / "data" / "DB" / "SQLark.db"

# ── 时间参数 ──
INTERVAL_MINUTES = 5
SECONDS_SUFFIX = 13  # 固定秒数

START_TIME = datetime(2026, 3, 18, 11, 54, SECONDS_SUFFIX)  # 11:49 + 5min
END_TIME = datetime(2026, 5, 8, 16, 1, SECONDS_SUFFIX)

# ── 股票信息 ──
CODE = "300750"
NAME = "宁德时代"

# ── 模拟参数 ──
DAILY_VOLATILITY = 0.022  # 日波动率 ~2.2%（宁德时代典型值）
BAR_VOLATILITY = DAILY_VOLATILITY / math.sqrt(288)  # 每根5分钟K线的波动率
DRIFT_DAILY = 0.0003  # 日漂移率（轻微上涨趋势）
DRIFT_BAR = DRIFT_DAILY / 288
MEAN_VOLUME = 254000  # 平均成交量
VOLUME_STD_RATIO = 0.6  # 成交量变异系数

# 开盘价与前收的跳空概率
GAP_PROBABILITY = 0.3
GAP_MAX_PERCENT = 0.015  # 最大跳空1.5%


def generate_5min_times(start: datetime, end: datetime) -> list[datetime]:
    """生成5分钟间隔的时间序列，跳过已存在数据的最后一条。"""
    times = []
    current = start
    while current <= end:
        times.append(current)
        current += timedelta(minutes=INTERVAL_MINUTES)
    return times


def simulate_volume(hour: int, base_volume: float) -> int:
    """生成带日内U型模式的成交量。"""
    # 日内模式：开盘和收盘量大，午间量小
    intraday_multiplier = {
        0: 0.5, 1: 0.3, 2: 0.2, 3: 0.2, 4: 0.2, 5: 0.15,
        6: 0.15, 7: 0.2, 8: 0.7, 9: 1.8, 10: 1.5, 11: 1.2,
        12: 0.4, 13: 1.3, 14: 1.4, 15: 1.6, 16: 1.0,
        17: 0.6, 18: 0.4, 19: 0.3, 20: 0.3, 21: 0.25,
        22: 0.2, 23: 0.3,
    }
    multiplier = intraday_multiplier.get(hour, 0.5)
    vol = base_volume * multiplier * random.lognormvariate(0, VOLUME_STD_RATIO)
    return max(100, int(vol))


def simulate_bar(
    prev_close: float,
    prev_settle: float,
    is_new_day: bool,
    hour: int,
) -> dict:
    """模拟一根5分钟K线。"""
    # 跳空处理
    if is_new_day and random.random() < GAP_PROBABILITY:
        gap_pct = random.gauss(0, GAP_MAX_PERCENT / 2)
        open_price = round(prev_close * (1 + gap_pct), 2)
    else:
        open_price = round(prev_settle, 2)

    # 几何布朗运动
    log_return = random.gauss(DRIFT_BAR, BAR_VOLATILITY)
    close_price = round(open_price * math.exp(log_return), 2)

    # 高低价
    price_range = abs(close_price - open_price)
    high_extra = abs(random.gauss(0, BAR_VOLATILITY * open_price * 0.5))
    low_extra = abs(random.gauss(0, BAR_VOLATILITY * open_price * 0.5))
    high_price = round(max(open_price, close_price) + high_extra, 2)
    low_price = round(min(open_price, close_price) - low_extra, 2)

    # 确保高低价合理
    low_price = max(low_price, round(high_price * 0.95, 2))
    if high_price <= low_price:
        high_price = round(low_price + 0.01, 2)

    # 买卖价
    spread = round(random.uniform(0.05, 0.35), 2)
    buy_price = round(close_price - spread / 2, 2)
    sell_price = round(close_price + spread / 2, 2)

    # 涨跌
    change_amount = round(close_price - prev_close, 2)
    change_percent = round((change_amount / prev_close) * 100, 4) if prev_close else 0

    # 成交量
    volume = simulate_volume(hour, MEAN_VOLUME)
    turnover = round(close_price * volume / 10000, 2)  # 万元

    return {
        "Code": CODE,
        "Name": NAME,
        "LatestPrice": close_price,
        "ChangeAmount": change_amount,
        "ChangePercent": change_percent,
        "BuyPrice": buy_price,
        "SellPrice": sell_price,
        "PrevClose": round(prev_close, 2),
        "OpenPrice": open_price,
        "HighPrice": high_price,
        "LowPrice": low_price,
        "Volume": volume,
        "Turnover": turnover,
    }


def main():
    print(f"数据库: {DB_PATH}")
    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.cursor()

    # 获取最后一条数据
    cur.execute("SELECT LatestPrice, TradeTime FROM StockData ORDER BY TradeTime DESC LIMIT 1")
    last_row = cur.fetchone()
    if not last_row:
        print("数据库无数据，退出")
        return

    last_price = last_row[0]
    last_time_str = last_row[1]
    print(f"最后一条: 价格={last_price}, 时间={last_time_str}")

    # 生成时间序列
    times = generate_5min_times(START_TIME, END_TIME)
    print(f"需要生成: {len(times)} 条数据")

    if not times:
        print("无需生成")
        conn.close()
        return

    # 逐条模拟
    prev_close = last_price
    prev_settle = last_price
    current_date: Optional[str] = None
    day_open_prev_close = last_price  # 跨日前的昨收

    inserted = 0
    batch = []

    for t in times:
        date_str = t.strftime("%Y-%m-%d")
        time_str = t.strftime("%Y-%m-%d %H:%M:%S")
        hour = t.hour

        # 检测跨日
        is_new_day = (date_str != current_date)
        if is_new_day:
            current_date = date_str
            day_open_prev_close = prev_settle

        bar = simulate_bar(
            prev_close=day_open_prev_close if is_new_day else prev_close,
            prev_settle=prev_settle,
            is_new_day=is_new_day,
            hour=hour,
        )
        bar["TradeTime"] = time_str

        batch.append((
            bar["Code"], bar["Name"], bar["LatestPrice"], bar["ChangeAmount"],
            bar["ChangePercent"], bar["BuyPrice"], bar["SellPrice"], bar["PrevClose"],
            bar["OpenPrice"], bar["HighPrice"], bar["LowPrice"],
            bar["Volume"], bar["Turnover"], bar["TradeTime"],
        ))

        prev_settle = bar["LatestPrice"]
        if is_new_day:
            day_open_prev_close = prev_settle
        prev_close = bar["LatestPrice"]

        # 每 500 条批量插入
        if len(batch) >= 500:
            cur.executemany(
                "INSERT INTO StockData "
                "(Code, Name, LatestPrice, ChangeAmount, ChangePercent, "
                "BuyPrice, SellPrice, PrevClose, OpenPrice, HighPrice, "
                "LowPrice, Volume, Turnover, TradeTime) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                batch,
            )
            inserted += len(batch)
            print(f"  已插入 {inserted}/{len(times)} ...")
            batch = []

    # 剩余数据
    if batch:
        cur.executemany(
            "INSERT INTO StockData "
            "(Code, Name, LatestPrice, ChangeAmount, ChangePercent, "
            "BuyPrice, SellPrice, PrevClose, OpenPrice, HighPrice, "
            "LowPrice, Volume, Turnover, TradeTime) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            batch,
        )
        inserted += len(batch)

    conn.commit()

    # 验证
    cur.execute("SELECT COUNT(*) FROM StockData")
    total = cur.fetchone()[0]
    cur.execute("SELECT MAX(TradeTime) FROM StockData")
    new_max = cur.fetchone()[0]
    cur.execute("SELECT MIN(LatestPrice), MAX(LatestPrice), AVG(LatestPrice) FROM StockData")
    price_stats = cur.fetchone()

    print(f"\n插入完成!")
    print(f"  新增: {inserted} 条")
    print(f"  总数: {total} 条")
    print(f"  最新时间: {new_max}")
    print(f"  价格范围: {price_stats[0]:.2f} ~ {price_stats[1]:.2f}, 均价: {price_stats[2]:.2f}")

    conn.close()


if __name__ == "__main__":
    random.seed(42)  # 固定种子，可复现
    main()
