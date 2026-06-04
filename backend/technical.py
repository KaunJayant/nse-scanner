"""
NSE Volatility Scanner — Technical Indicators
ATR, Volume Spike, Gap %, and RSI calculators.
"""

import numpy as np
import pandas as pd
from backend.config import ATR_PERIOD, VOLUME_AVG_PERIOD, RSI_PERIOD


def calculate_true_range(df: pd.DataFrame) -> pd.Series:
    high = df["High"]
    low = df["Low"]
    prev_close = df["Close"].shift(1)
    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()
    return pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)


def calculate_atr(df: pd.DataFrame, period: int = ATR_PERIOD) -> pd.Series:
    """ATR using Wilder's smoothing."""
    tr = calculate_true_range(df)
    atr = pd.Series(index=df.index, dtype=float)
    atr[:] = np.nan
    if len(tr) < period:
        return atr
    atr.iloc[period - 1] = tr.iloc[:period].mean()
    for i in range(period, len(tr)):
        atr.iloc[i] = ((atr.iloc[i - 1] * (period - 1)) + tr.iloc[i]) / period
    return atr


def calculate_atr_pct(atr_value: float, cmp: float) -> float:
    if cmp <= 0:
        return 0.0
    return (atr_value / cmp) * 100


def calculate_volume_spike(current_volume: float, avg_volume_20d: float) -> float:
    if avg_volume_20d <= 0:
        return 0.0
    return current_volume / avg_volume_20d


def calculate_avg_volume(df: pd.DataFrame, period: int = VOLUME_AVG_PERIOD) -> float:
    if len(df) < period:
        return df["Volume"].mean() if len(df) > 0 else 0.0
    return df["Volume"].iloc[-period:].mean()


def calculate_gap_pct(today_open: float, prev_close: float) -> float:
    if prev_close <= 0:
        return 0.0
    return ((today_open - prev_close) / prev_close) * 100


def calculate_rsi(df: pd.DataFrame, period: int = RSI_PERIOD) -> pd.Series:
    """RSI using Wilder's smoothing."""
    delta = df["Close"].diff()
    gain = delta.where(delta > 0, 0.0)
    loss = (-delta).where(delta < 0, 0.0)
    rsi = pd.Series(index=df.index, dtype=float)
    rsi[:] = np.nan
    if len(df) < period + 1:
        return rsi
    avg_gain = gain.iloc[1:period + 1].mean()
    avg_loss = loss.iloc[1:period + 1].mean()
    if avg_loss == 0:
        rsi.iloc[period] = 100.0
    else:
        rs = avg_gain / avg_loss
        rsi.iloc[period] = 100 - (100 / (1 + rs))
    for i in range(period + 1, len(df)):
        avg_gain = ((avg_gain * (period - 1)) + gain.iloc[i]) / period
        avg_loss = ((avg_loss * (period - 1)) + loss.iloc[i]) / period
        if avg_loss == 0:
            rsi.iloc[i] = 100.0
        else:
            rs = avg_gain / avg_loss
            rsi.iloc[i] = 100 - (100 / (1 + rs))
    return rsi


def compute_all_indicators(df: pd.DataFrame) -> dict:
    """Compute all indicators for a stock's OHLCV DataFrame. Returns latest values."""
    if df is None or len(df) < ATR_PERIOD + 1:
        return None
    atr_series = calculate_atr(df)
    rsi_series = calculate_rsi(df)
    latest = df.iloc[-1]
    prev = df.iloc[-2] if len(df) >= 2 else latest
    atr_val = atr_series.iloc[-1] if not pd.isna(atr_series.iloc[-1]) else 0.0
    rsi_val = rsi_series.iloc[-1] if not pd.isna(rsi_series.iloc[-1]) else 50.0
    cmp = latest["Close"]
    avg_vol = calculate_avg_volume(df.iloc[:-1])
    return {
        "cmp": round(cmp, 2),
        "prev_close": round(prev["Close"], 2),
        "day_open": round(latest["Open"], 2),
        "day_high": round(latest["High"], 2),
        "day_low": round(latest["Low"], 2),
        "volume": int(latest["Volume"]),
        "pct_change": round(((cmp - prev["Close"]) / prev["Close"]) * 100, 2) if prev["Close"] > 0 else 0.0,
        "atr": round(atr_val, 2),
        "atr_pct": round(calculate_atr_pct(atr_val, cmp), 2),
        "volume_spike": round(calculate_volume_spike(latest["Volume"], avg_vol), 2),
        "gap_pct": round(calculate_gap_pct(latest["Open"], prev["Close"]), 2),
        "rsi": round(rsi_val, 2),
    }
