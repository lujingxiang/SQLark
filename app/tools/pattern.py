"""价格形态特征识别工具集。"""

from __future__ import annotations

from typing import Any


def _get_values(data: list[dict], field: str) -> list[float]:
    """从数据行中提取指定字段的浮点数值。"""
    values = []
    for row in data:
        value = row.get(field)
        if value is None:
            continue
        try:
            values.append(float(value))
        except (TypeError, ValueError):
            continue
    return values


def _get_ohlc(data: list[dict]) -> list[dict[str, float]]:
    """提取 OHLC 数据序列。"""
    ohlc_list = []
    for row in data:
        try:
            ohlc_list.append({
                "open": float(row.get("OpenPrice", 0)),
                "high": float(row.get("HighPrice", 0)),
                "low": float(row.get("LowPrice", 0)),
                "close": float(row.get("LatestPrice", 0)),
                "time": row.get("TradeTime", ""),
            })
        except (TypeError, ValueError):
            continue
    return ohlc_list


# ==================== K线形态识别 ====================

def detect_hammer(ohlc: list[dict[str, float]]) -> list[dict[str, Any]]:
    """检测锤子线形态：实体小、下影线长、上影线极短。"""
    patterns = []
    for i, bar in enumerate(ohlc):
        body = abs(bar["close"] - bar["open"])
        total_range = bar["high"] - bar["low"]
        if total_range == 0:
            continue
        upper_shadow = bar["high"] - max(bar["open"], bar["close"])
        lower_shadow = min(bar["open"], bar["close"]) - bar["low"]
        body_ratio = body / total_range
        lower_shadow_ratio = lower_shadow / total_range

        if body_ratio < 0.3 and lower_shadow_ratio > 0.6 and upper_shadow < body * 0.5:
            patterns.append({
                "index": i, "time": bar["time"], "type": "锤子线",
                "direction": "看涨" if bar["close"] > bar["open"] else "看跌",
                "close": round(bar["close"], 2),
            })
    return patterns


def detect_engulfing(ohlc: list[dict[str, float]]) -> list[dict[str, Any]]:
    """检测吞没形态：前一根K线实体被后一根完全包裹。"""
    patterns = []
    for i in range(1, len(ohlc)):
        prev = ohlc[i - 1]
        curr = ohlc[i]
        prev_body_start = min(prev["open"], prev["close"])
        prev_body_end = max(prev["open"], prev["close"])
        curr_body_start = min(curr["open"], curr["close"])
        curr_body_end = max(curr["open"], curr["close"])

        if curr_body_start < prev_body_start and curr_body_end > prev_body_end:
            direction = "看涨" if curr["close"] > curr["open"] else "看跌"
            patterns.append({
                "index": i, "time": curr["time"], "type": "吞没形态",
                "direction": direction,
                "close": round(curr["close"], 2),
            })
    return patterns


def detect_doji(ohlc: list[dict[str, float]]) -> list[dict[str, Any]]:
    """检测十字星形态：开盘价与收盘价几乎相等。"""
    patterns = []
    for i, bar in enumerate(ohlc):
        body = abs(bar["close"] - bar["open"])
        total_range = bar["high"] - bar["low"]
        if total_range == 0:
            continue
        if body / total_range < 0.05:
            patterns.append({
                "index": i, "time": bar["time"], "type": "十字星",
                "direction": "犹豫",
                "close": round(bar["close"], 2),
            })
    return patterns


def detect_morning_star(ohlc: list[dict[str, float]]) -> list[dict[str, Any]]:
    """检测启明星形态：大阴线 + 小实体 + 大阳线。"""
    patterns = []
    for i in range(2, len(ohlc)):
        first = ohlc[i - 2]
        second = ohlc[i - 1]
        third = ohlc[i]
        first_body = abs(first["close"] - first["open"])
        second_body = abs(second["close"] - second["open"])
        third_body = abs(third["close"] - third["open"])

        is_first_bearish = first["close"] < first["open"]
        is_third_bullish = third["close"] > third["open"]
        is_second_small = second_body < first_body * 0.3

        if is_first_bearish and is_second_small and is_third_bullish and third_body > second_body * 2:
            patterns.append({
                "index": i, "time": third["time"], "type": "启明星",
                "direction": "看涨",
                "close": round(third["close"], 2),
            })
    return patterns


def detect_dark_cloud(ohlc: list[dict[str, float]]) -> list[dict[str, Any]]:
    """检测乌云盖顶形态：大阳线 + 高开低收阴线。"""
    patterns = []
    for i in range(1, len(ohlc)):
        prev = ohlc[i - 1]
        curr = ohlc[i]
        prev_body = abs(prev["close"] - prev["open"])
        curr_body = abs(curr["close"] - curr["open"])

        is_prev_bullish = prev["close"] > prev["open"]
        is_curr_bearish = curr["close"] < curr["open"]
        opens_above = curr["open"] > prev["close"]
        closes_below_mid = curr["close"] < (prev["open"] + prev["close"]) / 2

        if is_prev_bullish and is_curr_bearish and opens_above and closes_below_mid and curr_body > prev_body * 0.5:
            patterns.append({
                "index": i, "time": curr["time"], "type": "乌云盖顶",
                "direction": "看跌",
                "close": round(curr["close"], 2),
            })
    return patterns


def detect_all_patterns(ohlc: list[dict[str, float]]) -> list[dict[str, Any]]:
    """检测所有K线形态。"""
    all_patterns = []
    all_patterns.extend(detect_hammer(ohlc))
    all_patterns.extend(detect_engulfing(ohlc))
    all_patterns.extend(detect_doji(ohlc))
    all_patterns.extend(detect_morning_star(ohlc))
    all_patterns.extend(detect_dark_cloud(ohlc))
    all_patterns.sort(key=lambda p: p["index"])
    return all_patterns


# ==================== 均线交叉 ====================

def detect_ma_cross(data: list[dict], field: str = "LatestPrice",
                    short_period: int = 5, long_period: int = 20) -> list[dict[str, Any]]:
    """检测均线金叉/死叉。"""
    values = _get_values(data, field)
    if len(values) < long_period + 1:
        return []

    short_ma = []
    long_ma = []
    for i in range(len(values)):
        if i >= short_period - 1:
            short_ma.append(sum(values[i - short_period + 1:i + 1]) / short_period)
        else:
            short_ma.append(None)
        if i >= long_period - 1:
            long_ma.append(sum(values[i - long_period + 1:i + 1]) / long_period)
        else:
            long_ma.append(None)

    crosses = []
    for i in range(1, len(values)):
        if short_ma[i] is None or long_ma[i] is None or short_ma[i - 1] is None or long_ma[i - 1] is None:
            continue
        prev_diff = short_ma[i - 1] - long_ma[i - 1]
        curr_diff = short_ma[i] - long_ma[i]
        time_val = data[i].get("TradeTime", "") if i < len(data) else ""

        if prev_diff <= 0 and curr_diff > 0:
            crosses.append({
                "index": i, "time": time_val, "type": "金叉",
                "short_ma": round(short_ma[i], 4), "long_ma": round(long_ma[i], 4),
            })
        elif prev_diff >= 0 and curr_diff < 0:
            crosses.append({
                "index": i, "time": time_val, "type": "死叉",
                "short_ma": round(short_ma[i], 4), "long_ma": round(long_ma[i], 4),
            })

    return crosses


# ==================== 支撑/压力位 ====================

def detect_support_resistance(data: list[dict], field: str = "LatestPrice",
                              window: int = 5) -> dict[str, Any]:
    """检测支撑位和压力位。"""
    values = _get_values(data, field)
    if len(values) < window * 2:
        return {"error": "数据不足，无法识别支撑压力位"}

    local_mins = []
    local_maxs = []
    for i in range(window, len(values) - window):
        is_min = all(values[i] <= values[i + j] for j in range(-window, window + 1) if j != 0)
        is_max = all(values[i] >= values[i + j] for j in range(-window, window + 1) if j != 0)
        if is_min:
            local_mins.append({"value": round(values[i], 4), "index": i})
        if is_max:
            local_maxs.append({"value": round(values[i], 4), "index": i})

    support = round(min(m["value"] for m in local_mins[-3:]), 4) if len(local_mins) >= 1 else None
    resistance = round(max(m["value"] for m in local_maxs[-3:]), 4) if len(local_maxs) >= 1 else None

    return {
        "support": support,
        "resistance": resistance,
        "local_mins": local_mins[-5:],
        "local_maxs": local_maxs[-5:],
    }


# ==================== 缺口识别 ====================

def detect_gaps(ohlc: list[dict[str, float]]) -> list[dict[str, Any]]:
    """检测跳空缺口。"""
    gaps = []
    for i in range(1, len(ohlc)):
        prev_close = ohlc[i - 1]["close"]
        curr_open = ohlc[i]["open"]
        gap_up = curr_open - prev_close
        if gap_up > 0:
            gaps.append({
                "index": i, "time": ohlc[i]["time"], "type": "跳空高开",
                "gap_size": round(gap_up, 4),
            })
        elif gap_up < 0:
            gaps.append({
                "index": i, "time": ohlc[i]["time"], "type": "跳空低开",
                "gap_size": round(abs(gap_up), 4),
            })
    return gaps


# ==================== 统一入口 ====================

def run_pattern_analysis(data: list[dict], field: str = "LatestPrice") -> dict[str, Any]:
    """执行完整的形态分析，含技术指标与综合信号评分。"""
    ohlc = _get_ohlc(data)
    if len(ohlc) < 3:
        return {"error": "数据不足，至少需要3条记录才能进行形态分析"}

    kline_patterns = detect_all_patterns(ohlc)
    ma_crosses = detect_ma_cross(data, field)
    sr_levels = detect_support_resistance(data, field)
    gaps = detect_gaps(ohlc)

    from app.tools.quant_analysis import (
        calc_composite_signal, calc_macd, calc_rsi, calc_bollinger_bands,
        analyze_volume_price_divergence, analyze_volume_breakout,
    )
    macd_res = calc_macd(data, field)
    rsi_res = calc_rsi(data, field)
    boll_res = calc_bollinger_bands(data, field)

    return {
        "kline_patterns": kline_patterns,
        "kline_pattern_count": len(kline_patterns),
        "ma_crosses": ma_crosses,
        "ma_cross_count": len(ma_crosses),
        "support_resistance": sr_levels,
        "gaps": gaps,
        "gap_count": len(gaps),
        "macd": macd_res,
        "rsi": rsi_res,
        "bollinger_bands": boll_res,
        "composite_signal": calc_composite_signal(
            kline_patterns=kline_patterns,
            ma_crosses=ma_crosses,
            macd_result=macd_res,
            rsi_result=rsi_res,
            bollinger_result=boll_res,
            divergence_result=analyze_volume_price_divergence(data),
            breakout_result=analyze_volume_breakout(data),
        ),
        "data_points": len(data),
    }
