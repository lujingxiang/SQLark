"""量化分析工具集：量价关系 + 波动率与统计。"""

from __future__ import annotations

import math
import statistics
from typing import Any, Optional


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


def _get_paired_values(data: list[dict], field1: str, field2: str) -> tuple[list[float], list[float]]:
    """提取两个字段的配对数值。"""
    v1, v2 = [], []
    for row in data:
        val1 = row.get(field1)
        val2 = row.get(field2)
        if val1 is None or val2 is None:
            continue
        try:
            v1.append(float(val1))
            v2.append(float(val2))
        except (TypeError, ValueError):
            continue
    return v1, v2


# ==================== 基础统计分析 ====================

def analyze_basic_stats(data: list[dict], field: str) -> dict:
    """基础统计分析。"""
    values = _get_values(data, field)
    if not values:
        return {"error": "没有有效数据"}

    sorted_values = sorted(values)
    median_val = statistics.median(values)
    p90_index = max(0, int(round(len(sorted_values) * 0.9)) - 1)
    p90_val = sorted_values[p90_index]

    return {
        "analysis_type": "basic", "field": field, "count": len(values),
        "mean": round(statistics.mean(values), 4),
        "median": round(median_val, 4),
        "max": round(max(values), 4), "min": round(min(values), 4),
        "p90": round(p90_val, 4),
        "range": round(max(values) - min(values), 4),
        "first_value": round(values[0], 4), "last_value": round(values[-1], 4),
    }


def analyze_volatility_basic(data: list[dict], field: str) -> dict:
    """基础波动分析。"""
    values = _get_values(data, field)
    if len(values) < 2:
        return {"error": "数据不足，无法计算波动"}

    stdev = statistics.stdev(values)
    mean_val = statistics.mean(values)
    coefficient = abs(stdev / mean_val) if mean_val else None

    return {
        "analysis_type": "volatility", "field": field, "count": len(values),
        "mean": round(mean_val, 4), "stdev": round(stdev, 4),
        "cv": round(coefficient, 4) if coefficient is not None else None,
        "max": round(max(values), 4), "min": round(min(values), 4),
        "range": round(max(values) - min(values), 4),
    }


def analyze_trend(data: list[dict], field: str) -> dict:
    """趋势分析。"""
    values = _get_values(data, field)
    if len(values) < 2:
        return {"error": "数据不足，无法分析趋势"}

    first_value = values[0]
    last_value = values[-1]
    change = last_value - first_value
    change_rate = (change / first_value * 100) if first_value else None

    up_days = sum(1 for p, c in zip(values, values[1:]) if c > p)
    down_days = sum(1 for p, c in zip(values, values[1:]) if c < p)

    trend = "up" if change > 0 else "down" if change < 0 else "flat"

    return {
        "analysis_type": "trend", "field": field, "count": len(values),
        "first_value": round(first_value, 4), "last_value": round(last_value, 4),
        "change": round(change, 4),
        "change_rate": round(change_rate, 4) if change_rate is not None else None,
        "trend": trend,
        "max": round(max(values), 4), "min": round(min(values), 4),
        "up_days": up_days, "down_days": down_days,
    }


def analyze_anomaly(data: list[dict], field: str) -> dict:
    """异常检测（Z-score 方法）。"""
    values = _get_values(data, field)
    if len(values) < 3:
        return {"error": "数据不足，无法检测异常"}

    mean_val = statistics.mean(values)
    stdev = statistics.stdev(values)
    if stdev == 0:
        return {
            "analysis_type": "anomaly", "field": field, "count": len(values),
            "mean": round(mean_val, 4), "stdev": 0, "anomaly_count": 0, "anomalies": [],
        }

    anomalies = []
    for i, row in enumerate(data):
        value = row.get(field)
        if value is None:
            continue
        try:
            v = float(value)
        except (TypeError, ValueError):
            continue
        z_score = abs((v - mean_val) / stdev)
        if z_score > 2:
            anomalies.append({
                "index": i, "value": round(v, 4),
                "TradeTime": row.get("TradeTime"), "z_score": round(z_score, 4),
            })

    return {
        "analysis_type": "anomaly", "field": field, "count": len(values),
        "mean": round(mean_val, 4), "stdev": round(stdev, 4),
        "anomaly_count": len(anomalies), "anomalies": anomalies[:10],
    }


def analyze_count(data: list[dict]) -> dict:
    """计数分析。"""
    return {"analysis_type": "count", "count": len(data)}


def analyze_comparison(data: list[dict], field: str) -> dict:
    """对比分析。"""
    values = _get_values(data, field)
    if len(values) < 2:
        return {"error": "数据不足，无法做对比分析"}

    first_value = values[0]
    last_value = values[-1]
    delta = last_value - first_value
    delta_rate = (delta / first_value * 100) if first_value else None

    return {
        "analysis_type": "comparison", "field": field, "count": len(values),
        "first_value": round(first_value, 4), "last_value": round(last_value, 4),
        "delta": round(delta, 4),
        "delta_rate": round(delta_rate, 4) if delta_rate is not None else None,
        "direction": "up" if delta > 0 else "down" if delta < 0 else "flat",
    }


def run_analysis(data: list[dict], field: Optional[str], analysis_type: str) -> dict:
    """执行基础分析（统一入口）。"""
    dispatch = {
        "count": lambda: analyze_count(data),
        "basic": lambda: analyze_basic_stats(data, field or "LatestPrice"),
        "volatility": lambda: analyze_volatility_basic(data, field or "LatestPrice"),
        "trend": lambda: analyze_trend(data, field or "LatestPrice"),
        "anomaly": lambda: analyze_anomaly(data, field or "LatestPrice"),
        "comparison": lambda: analyze_comparison(data, field or "LatestPrice"),
    }
    handler = dispatch.get(analysis_type)
    if handler is None:
        return {"error": f"不支持的分析类型: {analysis_type}"}
    return handler()


# ==================== 量价关系分析 ====================

def analyze_volume_price_divergence(data: list[dict]) -> dict[str, Any]:
    """量价背离分析：价格创新高但成交量萎缩。"""
    prices = _get_values(data, "LatestPrice")
    volumes = _get_values(data, "Volume")
    if len(prices) < 5 or len(volumes) < 5:
        return {"error": "数据不足，至少需要5条记录"}

    min_len = min(len(prices), len(volumes))
    prices = prices[:min_len]
    volumes = volumes[:min_len]

    window = min(5, min_len)
    recent_prices = prices[-window:]
    recent_volumes = volumes[-window:]

    price_trend = recent_prices[-1] - recent_prices[0]
    volume_trend = sum(recent_volumes[1:]) / (len(recent_volumes) - 1) - recent_volumes[0] if len(recent_volumes) > 1 else 0

    is_bullish_divergence = price_trend > 0 and volume_trend < 0
    is_bearish_divergence = price_trend < 0 and volume_trend > 0

    vol_mean = statistics.mean(volumes)
    vol_stdev = statistics.stdev(volumes) if len(volumes) > 1 else 0

    return {
        "analysis_type": "volume_price_divergence",
        "price_trend": "上涨" if price_trend > 0 else "下跌" if price_trend < 0 else "持平",
        "volume_trend": "放量" if volume_trend > 0 else "缩量" if volume_trend < 0 else "持平",
        "is_bullish_divergence": is_bullish_divergence,
        "is_bearish_divergence": is_bearish_divergence,
        "divergence_signal": (
            "顶背离（价格涨量缩，可能回调）" if is_bullish_divergence
            else "底背离（价格跌量增，可能反弹）" if is_bearish_divergence
            else "无量价背离"
        ),
        "avg_volume": round(vol_mean, 4),
        "volume_volatility": round(vol_stdev / vol_mean * 100, 4) if vol_mean else None,
    }


def analyze_volume_breakout(data: list[dict]) -> dict[str, Any]:
    """放量突破检测：成交量突破阈值 + 价格突破。"""
    prices = _get_values(data, "LatestPrice")
    volumes = _get_values(data, "Volume")
    if len(prices) < 10 or len(volumes) < 10:
        return {"error": "数据不足，至少需要10条记录"}

    min_len = min(len(prices), len(volumes))
    prices = prices[:min_len]
    volumes = volumes[:min_len]

    vol_mean = statistics.mean(volumes)
    vol_stdev = statistics.stdev(volumes) if len(volumes) > 1 else 0
    vol_threshold = vol_mean + 2 * vol_stdev

    price_high = max(prices[:-1]) if len(prices) > 1 else prices[0]

    breakouts = []
    for i in range(1, min_len):
        if volumes[i] > vol_threshold and prices[i] > price_high:
            breakouts.append({
                "index": i,
                "volume": round(volumes[i], 4),
                "price": round(prices[i], 4),
                "volume_ratio": round(volumes[i] / vol_mean, 2) if vol_mean else None,
            })

    return {
        "analysis_type": "volume_breakout",
        "avg_volume": round(vol_mean, 4),
        "volume_threshold_2sigma": round(vol_threshold, 4),
        "breakout_count": len(breakouts),
        "breakouts": breakouts[-5:],
        "latest_price_vs_high": (
            "突破前高" if prices[-1] > price_high
            else "低于前高"
        ),
    }


def analyze_volume_consolidation(data: list[dict]) -> dict[str, Any]:
    """缩量盘整检测：成交量持续低位 + 价格窄幅震荡。"""
    prices = _get_values(data, "LatestPrice")
    volumes = _get_values(data, "Volume")
    if len(prices) < 5 or len(volumes) < 5:
        return {"error": "数据不足，至少需要5条记录"}

    min_len = min(len(prices), len(volumes))
    prices = prices[:min_len]
    volumes = volumes[:min_len]

    window = min(5, min_len)
    recent_prices = prices[-window:]
    recent_volumes = volumes[-window:]

    vol_mean = statistics.mean(volumes)
    vol_stdev = statistics.stdev(volumes) if len(volumes) > 1 else 0

    recent_vol_ratio = statistics.mean(recent_volumes) / vol_mean if vol_mean else 0
    price_range = max(recent_prices) - min(recent_prices)
    price_cv = statistics.stdev(recent_prices) / statistics.mean(recent_prices) * 100 if statistics.mean(recent_prices) else 0

    is_consolidation = recent_vol_ratio < 0.7 and price_cv < 2.0

    return {
        "analysis_type": "volume_consolidation",
        "recent_volume_ratio": round(recent_vol_ratio, 4),
        "price_cv": round(price_cv, 4),
        "price_range": round(price_range, 4),
        "is_consolidation": is_consolidation,
        "signal": "缩量盘整中" if is_consolidation else "非盘整状态",
    }


def analyze_obv(data: list[dict]) -> dict[str, Any]:
    """OBV（能量潮）指标计算。"""
    prices = _get_values(data, "LatestPrice")
    volumes = _get_values(data, "Volume")
    if len(prices) < 3 or len(volumes) < 3:
        return {"error": "数据不足，至少需要3条记录"}

    min_len = min(len(prices), len(volumes))
    prices = prices[:min_len]
    volumes = volumes[:min_len]

    obv = [0.0]
    for i in range(1, min_len):
        if prices[i] > prices[i - 1]:
            obv.append(obv[-1] + volumes[i])
        elif prices[i] < prices[i - 1]:
            obv.append(obv[-1] - volumes[i])
        else:
            obv.append(obv[-1])

    obv_trend = "上升" if obv[-1] > obv[0] else "下降" if obv[-1] < obv[0] else "持平"

    return {
        "analysis_type": "obv",
        "obv_first": round(obv[0], 4),
        "obv_last": round(obv[-1], 4),
        "obv_trend": obv_trend,
        "obv_change": round(obv[-1] - obv[0], 4),
    }


def analyze_turnover_anomaly(data: list[dict]) -> dict[str, Any]:
    """换手率异常检测：成交量偏离历史均值 > 2σ。"""
    volumes = _get_values(data, "Volume")
    if len(volumes) < 5:
        return {"error": "数据不足，至少需要5条记录"}

    vol_mean = statistics.mean(volumes)
    vol_stdev = statistics.stdev(volumes) if len(volumes) > 1 else 0
    if vol_stdev == 0:
        return {
            "analysis_type": "turnover_anomaly",
            "avg_volume": round(vol_mean, 4), "anomaly_count": 0, "anomalies": [],
        }

    anomalies = []
    for i, vol in enumerate(volumes):
        z_score = (vol - vol_mean) / vol_stdev
        if abs(z_score) > 2:
            anomalies.append({
                "index": i, "volume": round(vol, 4),
                "z_score": round(z_score, 4),
                "direction": "放量" if z_score > 0 else "缩量",
            })

    return {
        "analysis_type": "turnover_anomaly",
        "avg_volume": round(vol_mean, 4),
        "volume_stdev": round(vol_stdev, 4),
        "anomaly_count": len(anomalies),
        "anomalies": anomalies[-5:],
        "latest_volume_zscore": round((volumes[-1] - vol_mean) / vol_stdev, 4),
    }


def backtest_ma_cross(
    data: list[dict],
    field: str = "LatestPrice",
    fast: int = 5,
    slow: int = 20,
) -> dict[str, Any]:
    """MA金叉/死叉策略回测：金叉买入，死叉卖出，返回收益率、回撤、Sharpe等指标。"""
    values = _get_values(data, field)
    n = len(values)
    if n < slow + 1:
        return {"error": f"数据不足，回测至少需要 {slow + 1} 条记录，当前 {n} 条"}

    def _sma(vals: list[float], period: int) -> list[Optional[float]]:
        return [
            sum(vals[i - period + 1: i + 1]) / period if i >= period - 1 else None
            for i in range(len(vals))
        ]

    fast_ma = _sma(values, fast)
    slow_ma = _sma(values, slow)

    trades: list[dict] = []
    in_position: Optional[dict] = None

    for i in range(1, n):
        if fast_ma[i] is None or slow_ma[i] is None:
            continue
        if fast_ma[i - 1] is None or slow_ma[i - 1] is None:
            continue
        prev_diff = fast_ma[i - 1] - slow_ma[i - 1]  # type: ignore[operator]
        curr_diff = fast_ma[i] - slow_ma[i]            # type: ignore[operator]

        if prev_diff <= 0 < curr_diff:  # 金叉：买入
            if in_position is None:
                in_position = {"entry_price": values[i]}
        elif prev_diff >= 0 > curr_diff:  # 死叉：卖出
            if in_position is not None:
                ret = (values[i] - in_position["entry_price"]) / in_position["entry_price"]
                trades.append({"entry": round(in_position["entry_price"], 4),
                                "exit": round(values[i], 4),
                                "return_pct": round(ret * 100, 2),
                                "win": ret > 0})
                in_position = None

    if in_position is not None:  # 持仓到末尾
        ret = (values[-1] - in_position["entry_price"]) / in_position["entry_price"]
        trades.append({"entry": round(in_position["entry_price"], 4),
                        "exit": round(values[-1], 4),
                        "return_pct": round(ret * 100, 2),
                        "win": ret > 0,
                        "open": True})

    if not trades:
        return {"error": "回测期间无交易信号，数据样本量可能不足", "data_points": n}

    # 策略复利收益
    compound = 1.0
    for t in trades:
        compound *= 1 + t["return_pct"] / 100
    total_return = round((compound - 1) * 100, 2)

    # 买入持有收益（从慢线启动点起算）
    bah_return = round((values[-1] - values[slow - 1]) / values[slow - 1] * 100, 2)

    # 最大回撤（基于逐笔权益曲线）
    equity = [1.0]
    for t in trades:
        equity.append(equity[-1] * (1 + t["return_pct"] / 100))
    peak = equity[0]
    max_dd = 0.0
    for v in equity:
        if v > peak:
            peak = v
        dd = (peak - v) / peak
        if dd > max_dd:
            max_dd = dd

    # 逐笔 Sharpe（无风险利率=0）
    rets = [t["return_pct"] / 100 for t in trades]
    if len(rets) > 1:
        mean_r = sum(rets) / len(rets)
        std_r = math.sqrt(sum((r - mean_r) ** 2 for r in rets) / (len(rets) - 1))
        sharpe = round(mean_r / std_r, 2) if std_r > 0 else 0.0
    else:
        sharpe = round(1.0 if rets[0] > 0 else -1.0, 2) if rets else 0.0

    wins = sum(1 for t in trades if t["win"])

    return {
        "strategy": f"MA{fast}/MA{slow} 金叉策略",
        "fast_period": fast,
        "slow_period": slow,
        "total_return": total_return,
        "buy_and_hold_return": bah_return,
        "excess_return": round(total_return - bah_return, 2),
        "max_drawdown": round(max_dd * 100, 2),
        "sharpe": sharpe,
        "win_rate": round(wins / len(trades) * 100, 2),
        "trade_count": len(trades),
        "win_count": wins,
        "loss_count": len(trades) - wins,
        "data_points": n,
    }


def run_volume_price_analysis(data: list[dict]) -> dict[str, Any]:
    """执行完整的量价关系分析，含技术指标与综合信号评分。"""
    from app.tools.pattern import run_pattern_analysis

    divergence = analyze_volume_price_divergence(data)
    breakout = analyze_volume_breakout(data)
    pattern_res = run_pattern_analysis(data)
    macd_res = calc_macd(data)
    rsi_res = calc_rsi(data)
    boll_res = calc_bollinger_bands(data)

    return {
        "divergence": divergence,
        "breakout": breakout,
        "consolidation": analyze_volume_consolidation(data),
        "obv": analyze_obv(data),
        "turnover_anomaly": analyze_turnover_anomaly(data),
        "macd": macd_res,
        "rsi": rsi_res,
        "bollinger_bands": boll_res,
        "composite_signal": calc_composite_signal(
            kline_patterns=pattern_res.get("kline_patterns", []),
            ma_crosses=pattern_res.get("ma_crosses", []),
            macd_result=macd_res,
            rsi_result=rsi_res,
            bollinger_result=boll_res,
            divergence_result=divergence,
            breakout_result=breakout,
        ),
        "backtest": backtest_ma_cross(data),
        "data_points": len(data),
    }


# ==================== 波动率与统计特征 ====================

def calc_historical_volatility(data: list[dict], field: str = "LatestPrice",
                                trading_days: int = 252) -> dict[str, Any]:
    """历史波动率：日收益率标准差 × √252。"""
    values = _get_values(data, field)
    if len(values) < 2:
        return {"error": "数据不足，至少需要2条记录计算波动率"}

    returns = [(values[i] - values[i - 1]) / values[i - 1] for i in range(1, len(values)) if values[i - 1] != 0]
    if not returns:
        return {"error": "无法计算收益率"}

    daily_vol = statistics.stdev(returns) if len(returns) > 1 else 0
    annualized_vol = daily_vol * math.sqrt(trading_days)

    return {
        "analysis_type": "historical_volatility",
        "field": field,
        "daily_volatility": round(daily_vol, 6),
        "annualized_volatility": round(annualized_vol, 6),
        "annualized_volatility_pct": f"{round(annualized_vol * 100, 2)}%",
        "data_points": len(values),
        "return_count": len(returns),
        "avg_return": round(statistics.mean(returns), 6),
    }


def calc_atr(data: list[dict], period: int = 14) -> dict[str, Any]:
    """ATR（真实波幅均值）。"""
    if len(data) < 2:
        return {"error": "数据不足，至少需要2条记录计算ATR"}

    true_ranges = []
    for i in range(1, len(data)):
        try:
            high = float(data[i].get("HighPrice", 0))
            low = float(data[i].get("LowPrice", 0))
            prev_close = float(data[i - 1].get("LatestPrice", 0))
        except (TypeError, ValueError):
            continue

        tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
        true_ranges.append(tr)

    if not true_ranges:
        return {"error": "无法计算真实波幅"}

    atr_value = statistics.mean(true_ranges[-period:]) if len(true_ranges) >= period else statistics.mean(true_ranges)

    return {
        "analysis_type": "atr",
        "atr": round(atr_value, 4),
        "period": period,
        "max_tr": round(max(true_ranges), 4),
        "min_tr": round(min(true_ranges), 4),
        "avg_tr": round(statistics.mean(true_ranges), 4),
    }


def calc_skewness_kurtosis(data: list[dict], field: str = "LatestPrice") -> dict[str, Any]:
    """偏度/峰度：收益率分布特征。"""
    values = _get_values(data, field)
    if len(values) < 4:
        return {"error": "数据不足，至少需要4条记录"}

    returns = [(values[i] - values[i - 1]) / values[i - 1] for i in range(1, len(values)) if values[i - 1] != 0]
    if len(returns) < 3:
        return {"error": "收益率数据不足"}

    mean_ret = statistics.mean(returns)
    stdev_ret = statistics.stdev(returns) if len(returns) > 1 else 0
    if stdev_ret == 0:
        return {"error": "收益率标准差为0"}

    n = len(returns)
    m3 = sum((r - mean_ret) ** 3 for r in returns) / n
    m4 = sum((r - mean_ret) ** 4 for r in returns) / n
    skewness = m3 / (stdev_ret ** 3)
    kurtosis = m4 / (stdev_ret ** 4) - 3  # 超额峰度

    return {
        "analysis_type": "skewness_kurtosis",
        "field": field,
        "skewness": round(skewness, 4),
        "kurtosis": round(kurtosis, 4),
        "distribution_shape": (
            "右偏厚尾" if skewness > 0.5 and kurtosis > 1
            else "左偏厚尾" if skewness < -0.5 and kurtosis > 1
            else "近似正态" if abs(skewness) < 0.5 and abs(kurtosis) < 1
            else "右偏" if skewness > 0.5
            else "左偏" if skewness < -0.5
            else "厚尾" if kurtosis > 1
            else "薄尾" if kurtosis < -1
            else "轻度偏离正态"
        ),
        "mean_return": round(mean_ret, 6),
        "stdev_return": round(stdev_ret, 6),
    }


def calc_var(data: list[dict], field: str = "LatestPrice",
             confidence: float = 0.95) -> dict[str, Any]:
    """VaR（在险价值）：分位数法。"""
    values = _get_values(data, field)
    if len(values) < 10:
        return {"error": "数据不足，至少需要10条记录"}

    returns = [(values[i] - values[i - 1]) / values[i - 1] for i in range(1, len(values)) if values[i - 1] != 0]
    if not returns:
        return {"error": "无法计算收益率"}

    sorted_returns = sorted(returns)
    index_95 = max(0, int(len(sorted_returns) * 0.05) - 1)
    index_99 = max(0, int(len(sorted_returns) * 0.01) - 1)

    var_95 = sorted_returns[index_95]
    var_99 = sorted_returns[index_99]

    return {
        "analysis_type": "var",
        "field": field,
        "var_95": round(var_95, 6),
        "var_99": round(var_99, 6),
        "var_95_pct": f"{round(var_95 * 100, 2)}%",
        "var_99_pct": f"{round(var_99 * 100, 2)}%",
        "interpretation": f"在95%置信度下，日最大损失不超过 {abs(round(var_95 * 100, 2))}%",
    }


def calc_max_drawdown(data: list[dict], field: str = "LatestPrice") -> dict[str, Any]:
    """最大回撤：峰值到谷底最大跌幅。"""
    values = _get_values(data, field)
    if len(values) < 2:
        return {"error": "数据不足，至少需要2条记录"}

    peak = values[0]
    max_dd = 0.0
    max_dd_start = 0
    max_dd_end = 0
    peak_index = 0

    for i in range(1, len(values)):
        if values[i] > peak:
            peak = values[i]
            peak_index = i
        dd = (peak - values[i]) / peak if peak != 0 else 0
        if dd > max_dd:
            max_dd = dd
            max_dd_start = peak_index
            max_dd_end = i

    return {
        "analysis_type": "max_drawdown",
        "field": field,
        "max_drawdown": round(max_dd, 6),
        "max_drawdown_pct": f"{round(max_dd * 100, 2)}%",
        "peak_value": round(values[max_dd_start], 4),
        "trough_value": round(values[max_dd_end], 4),
        "peak_index": max_dd_start,
        "trough_index": max_dd_end,
    }


def calc_volatility_cone(data: list[dict], field: str = "LatestPrice") -> dict[str, Any]:
    """波动率锥：不同周期波动率分位数。"""
    values = _get_values(data, field)
    if len(values) < 10:
        return {"error": "数据不足，至少需要10条记录"}

    periods = [5, 10, 20, 30]
    cone = {}

    for period in periods:
        if len(values) < period + 1:
            continue
        rolling_vols = []
        for start in range(len(values) - period):
            window = values[start:start + period + 1]
            returns = [(window[i] - window[i - 1]) / window[i - 1]
                       for i in range(1, len(window)) if window[i - 1] != 0]
            if len(returns) > 1:
                rolling_vols.append(statistics.stdev(returns) * math.sqrt(252))

        if rolling_vols:
            sorted_vols = sorted(rolling_vols)
            cone[str(period)] = {
                "p25": round(sorted_vols[max(0, int(len(sorted_vols) * 0.25) - 1)], 6),
                "p50": round(sorted_vols[max(0, int(len(sorted_vols) * 0.50) - 1)], 6),
                "p75": round(sorted_vols[max(0, int(len(sorted_vols) * 0.75) - 1)], 6),
                "current": round(rolling_vols[-1], 6),
            }

    return {
        "analysis_type": "volatility_cone",
        "field": field,
        "cone": cone,
    }


# ==================== 技术指标 ====================

def _calc_ema(values: list[float], period: int) -> list[float | None]:
    """计算 EMA，前 period-1 个位置返回 None。"""
    result: list[float | None] = [None] * len(values)
    if len(values) < period:
        return result
    result[period - 1] = sum(values[:period]) / period
    k = 2.0 / (period + 1)
    for i in range(period, len(values)):
        result[i] = values[i] * k + result[i - 1] * (1 - k)
    return result


def calc_macd(data: list[dict], field: str = "LatestPrice",
              fast: int = 12, slow: int = 26, signal: int = 9) -> dict[str, Any]:
    """MACD 指标：DIF / DEA / 柱状图，输出最新信号与趋势。"""
    values = _get_values(data, field)
    min_len = slow + signal
    if len(values) < min_len:
        return {"error": f"数据不足，MACD 至少需要 {min_len} 条记录"}

    ema_fast = _calc_ema(values, fast)
    ema_slow = _calc_ema(values, slow)

    dif_list: list[float] = []
    dif_indices: list[int] = []
    for i in range(len(values)):
        if ema_fast[i] is not None and ema_slow[i] is not None:
            dif_list.append(ema_fast[i] - ema_slow[i])
            dif_indices.append(i)

    dea_raw = _calc_ema(dif_list, signal)

    valid_tuples: list[tuple[float, float, float]] = []
    for j, raw_dea in enumerate(dea_raw):
        if raw_dea is not None:
            dif_val = dif_list[j]
            valid_tuples.append((dif_val, raw_dea, (dif_val - raw_dea) * 2))

    if not valid_tuples:
        return {"error": "MACD 计算失败，有效数据不足"}

    last_dif, last_dea, last_hist = valid_tuples[-1]

    cross_signal = "无信号"
    if len(valid_tuples) >= 2:
        prev_dif, prev_dea, _ = valid_tuples[-2]
        if prev_dif <= prev_dea and last_dif > last_dea:
            cross_signal = "金叉（看涨）"
        elif prev_dif >= prev_dea and last_dif < last_dea:
            cross_signal = "死叉（看跌）"

    prev_hist = valid_tuples[-2][2] if len(valid_tuples) >= 2 else None
    hist_trend = None
    if prev_hist is not None:
        hist_trend = "扩张" if abs(last_hist) > abs(prev_hist) else "收缩"

    return {
        "analysis_type": "macd",
        "dif": round(last_dif, 6),
        "dea": round(last_dea, 6),
        "macd_hist": round(last_hist, 6),
        "cross_signal": cross_signal,
        "zero_position": "零轴上方（多头区间）" if last_dif > 0 else "零轴下方（空头区间）",
        "hist_trend": hist_trend,
        "data_points": len(values),
    }


def calc_rsi(data: list[dict], field: str = "LatestPrice", period: int = 14) -> dict[str, Any]:
    """RSI 相对强弱指数（Wilder 平滑法）。"""
    values = _get_values(data, field)
    if len(values) < period + 1:
        return {"error": f"数据不足，RSI 至少需要 {period + 1} 条记录"}

    deltas = [values[i] - values[i - 1] for i in range(1, len(values))]
    gains = [max(d, 0.0) for d in deltas]
    losses = [max(-d, 0.0) for d in deltas]

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    rsi_series: list[float] = []
    for i in range(period, len(deltas)):
        rsi_series.append(100.0 if avg_loss == 0 else 100 - 100 / (1 + avg_gain / avg_loss))
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period

    if not rsi_series:
        return {"error": "RSI 计算失败"}

    latest = round(rsi_series[-1], 2)
    prev = round(rsi_series[-2], 2) if len(rsi_series) >= 2 else None

    if latest >= 70:
        zone = "超买区（>70，注意回调风险）"
    elif latest <= 30:
        zone = "超卖区（<30，关注反弹机会）"
    elif latest >= 60:
        zone = "强势区（60-70）"
    elif latest <= 40:
        zone = "弱势区（30-40）"
    else:
        zone = "中性区（40-60）"

    return {
        "analysis_type": "rsi",
        "rsi": latest,
        "prev_rsi": prev,
        "zone": zone,
        "trend": ("上升" if latest > prev else "下降" if latest < prev else "持平") if prev is not None else None,
        "period": period,
        "data_points": len(values),
    }


def calc_bollinger_bands(data: list[dict], field: str = "LatestPrice",
                         period: int = 20, num_std: float = 2.0) -> dict[str, Any]:
    """布林带：中轨 MA20 ± 2σ，输出当前价格位置与带宽状态。"""
    values = _get_values(data, field)
    if len(values) < period:
        return {"error": f"数据不足，布林带至少需要 {period} 条记录"}

    window = values[-period:]
    mid = statistics.mean(window)
    std = statistics.stdev(window)
    upper = mid + num_std * std
    lower = mid - num_std * std
    latest = values[-1]

    band_width = upper - lower
    pct_b = (latest - lower) / band_width if band_width > 0 else 0.5

    squeeze = False
    if len(values) >= period * 2:
        prev_std = statistics.stdev(values[-period * 2:-period])
        squeeze = std < prev_std * 0.7

    if latest > upper:
        position = "突破上轨（超买，注意回调）"
    elif latest < lower:
        position = "突破下轨（超卖，关注反弹）"
    elif pct_b > 0.8:
        position = "上轨附近（偏强）"
    elif pct_b < 0.2:
        position = "下轨附近（偏弱）"
    else:
        position = "带内运行（中性）"

    return {
        "analysis_type": "bollinger_bands",
        "field": field,
        "upper": round(upper, 4),
        "middle": round(mid, 4),
        "lower": round(lower, 4),
        "latest_price": round(latest, 4),
        "pct_b": round(pct_b, 4),
        "band_width": round(band_width, 4),
        "position": position,
        "squeeze": squeeze,
        "squeeze_signal": "带宽收窄（蓄势待发）" if squeeze else "带宽正常",
        "period": period,
    }


# ==================== 综合信号评分 ====================

def calc_composite_signal(
    kline_patterns: list,
    ma_crosses: list,
    macd_result: dict,
    rsi_result: dict,
    bollinger_result: dict,
    divergence_result: dict,
    breakout_result: dict,
) -> dict[str, Any]:
    """综合信号评分 [-100, +100]，聚合7个维度多空信号，输出评级与信号列表。"""
    score = 0
    signals: list[str] = []

    # 1. K线形态（最近3个，每个±15分）
    for p in kline_patterns[-3:]:
        direction = p.get("direction", "")
        if direction == "看涨":
            score += 15
            signals.append(f"K线看涨：{p.get('type', '')}")
        elif direction == "看跌":
            score -= 15
            signals.append(f"K线看跌：{p.get('type', '')}")

    # 2. 均线交叉（最近一次，±20分）
    if ma_crosses:
        cross_type = ma_crosses[-1].get("type", "")
        if cross_type == "金叉":
            score += 20
            signals.append("MA金叉（看涨）")
        elif cross_type == "死叉":
            score -= 20
            signals.append("MA死叉（看跌）")

    # 3. RSI（超买超卖±15分，强弱区±5分）
    if "error" not in rsi_result:
        rsi_val = rsi_result.get("rsi", 50)
        if rsi_val >= 70:
            score -= 15
            signals.append(f"RSI超买（{rsi_val}，注意回调）")
        elif rsi_val <= 30:
            score += 15
            signals.append(f"RSI超卖（{rsi_val}，关注反弹）")
        elif rsi_val >= 60:
            score += 5
            signals.append(f"RSI强势区（{rsi_val}）")
        elif rsi_val <= 40:
            score -= 5
            signals.append(f"RSI弱势区（{rsi_val}）")

    # 4. MACD（金叉死叉±20分，柱状趋势±5分）
    if "error" not in macd_result:
        cross = macd_result.get("cross_signal", "")
        hist = macd_result.get("macd_hist", 0)
        hist_trend = macd_result.get("hist_trend")
        if "金叉" in cross:
            score += 20
            signals.append("MACD金叉（看涨）")
        elif "死叉" in cross:
            score -= 20
            signals.append("MACD死叉（看跌）")
        if hist_trend == "扩张":
            if hist > 0:
                score += 5
                signals.append("MACD红柱扩张（多头增强）")
            elif hist < 0:
                score -= 5
                signals.append("MACD绿柱扩张（空头增强）")

    # 5. 布林带（突破上下轨±10分）
    if "error" not in bollinger_result:
        position = bollinger_result.get("position", "")
        if "突破上轨" in position:
            score -= 10
            signals.append("价格突破布林带上轨（超买）")
        elif "突破下轨" in position:
            score += 10
            signals.append("价格突破布林带下轨（超卖）")
        if bollinger_result.get("squeeze"):
            signals.append("布林带收窄（蓄势待发，等待方向突破）")

    # 6. 量价背离（±15分）
    if "error" not in divergence_result:
        div_signal = divergence_result.get("divergence_signal", "")
        if "顶背离" in div_signal:
            score -= 15
            signals.append("量价顶背离（价涨量缩，看跌）")
        elif "底背离" in div_signal:
            score += 15
            signals.append("量价底背离（价跌量增，看涨）")

    # 7. 放量突破（+10分）
    if "error" not in breakout_result:
        if breakout_result.get("breakout_count", 0) > 0:
            if "突破前高" in breakout_result.get("latest_price_vs_high", ""):
                score += 10
                signals.append("放量突破前高（看涨）")

    score = max(-100, min(100, score))

    if score >= 60:
        rating = "强烈看涨"
    elif score >= 30:
        rating = "看涨"
    elif score > -30:
        rating = "中性"
    elif score > -60:
        rating = "看跌"
    else:
        rating = "强烈看跌"

    bullish_k = len([p for p in kline_patterns[-3:] if p.get("direction") == "看涨"])
    bearish_k = len([p for p in kline_patterns[-3:] if p.get("direction") == "看跌"])

    return {
        "score": score,
        "rating": rating,
        "signals": signals,
        "signal_count": len(signals),
        "components": {
            "kline": f"{bullish_k}涨/{bearish_k}跌",
            "ma_cross": ma_crosses[-1].get("type", "无") if ma_crosses else "无",
            "rsi": rsi_result.get("rsi", "N/A") if "error" not in rsi_result else "N/A",
            "macd": macd_result.get("cross_signal", "无信号") if "error" not in macd_result else "N/A",
            "bollinger": bollinger_result.get("position", "N/A") if "error" not in bollinger_result else "N/A",
            "volume_price": divergence_result.get("divergence_signal", "N/A") if "error" not in divergence_result else "N/A",
        },
    }


def run_volatility_analysis(data: list[dict], field: str = "LatestPrice") -> dict[str, Any]:
    """执行完整的波动率与技术指标分析，含综合信号评分。"""
    from app.tools.pattern import run_pattern_analysis

    macd_res = calc_macd(data, field)
    rsi_res = calc_rsi(data, field)
    boll_res = calc_bollinger_bands(data, field)
    pattern_res = run_pattern_analysis(data, field)

    return {
        "historical_volatility": calc_historical_volatility(data, field),
        "atr": calc_atr(data),
        "skewness_kurtosis": calc_skewness_kurtosis(data, field),
        "var": calc_var(data, field),
        "max_drawdown": calc_max_drawdown(data, field),
        "volatility_cone": calc_volatility_cone(data, field),
        "macd": macd_res,
        "rsi": rsi_res,
        "bollinger_bands": boll_res,
        "composite_signal": calc_composite_signal(
            kline_patterns=pattern_res.get("kline_patterns", []),
            ma_crosses=pattern_res.get("ma_crosses", []),
            macd_result=macd_res,
            rsi_result=rsi_res,
            bollinger_result=boll_res,
            divergence_result=analyze_volume_price_divergence(data),
            breakout_result=analyze_volume_breakout(data),
        ),
        "backtest": backtest_ma_cross(data, field),
        "data_points": len(data),
    }
