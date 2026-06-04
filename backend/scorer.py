"""
NSE Volatility Scanner — Scoring Engine
Normalizes indicators and computes composite scores.
"""

import numpy as np
from typing import List, Dict
from backend.config import (
    WEIGHT_ATR, WEIGHT_VOLUME, WEIGHT_GAP, WEIGHT_RSI, WEIGHT_MATERIALITY,
    RSI_OVERBOUGHT, RSI_OVERSOLD, NIFTY_TREND_THRESHOLD,
)


def normalize_to_score(values: List[float], higher_is_better: bool = True) -> List[float]:
    """
    Normalize a list of values to 0-10 scale using percentile ranking.
    """
    if not values or len(values) == 0:
        return [0.0] * len(values)

    arr = np.array(values, dtype=float)
    valid_mask = ~np.isnan(arr) & ~np.isinf(arr)

    if valid_mask.sum() == 0:
        return [0.0] * len(values)

    scores = np.zeros(len(values))
    valid_vals = arr[valid_mask]

    if valid_vals.max() == valid_vals.min():
        scores[valid_mask] = 5.0
    else:
        # Percentile-based normalization
        for i in range(len(values)):
            if valid_mask[i]:
                percentile = np.sum(valid_vals <= arr[i]) / len(valid_vals)
                scores[i] = percentile * 10.0

    if not higher_is_better:
        scores[valid_mask] = 10.0 - scores[valid_mask]

    return [round(s, 2) for s in scores]


def calculate_rsi_penalty(rsi: float) -> float:
    """
    RSI penalty: reduce score for extreme RSI values.
    RSI > 70: penalty proportional to how overbought
    RSI < 30: penalty proportional to how oversold
    Returns a factor 0.0 to 1.0 (1.0 = no penalty)
    """
    if rsi > RSI_OVERBOUGHT:
        # Linear penalty from 70 (no penalty) to 100 (max penalty)
        penalty = (rsi - RSI_OVERBOUGHT) / (100 - RSI_OVERBOUGHT)
        return max(0.3, 1.0 - penalty * 0.7)
    elif rsi < RSI_OVERSOLD:
        # Linear penalty from 30 (no penalty) to 0 (max penalty)
        penalty = (RSI_OVERSOLD - rsi) / RSI_OVERSOLD
        return max(0.3, 1.0 - penalty * 0.7)
    return 1.0


def determine_signal_type(
    pct_change: float,
    gap_pct: float,
    volume_spike: float,
    rsi: float,
    nifty_pct_change: float,
) -> str:
    """
    Determine signal type: BUY, SELL, or WATCH.
    """
    # Trend filter hard gate
    if nifty_pct_change < -NIFTY_TREND_THRESHOLD * 100:
        # Nifty down > 1%, suppress BUY
        if pct_change > 0 and gap_pct > 0:
            return "WATCH"  # Don't BUY against market
    elif nifty_pct_change > NIFTY_TREND_THRESHOLD * 100:
        # Nifty up > 1%, suppress SELL
        if pct_change < 0 and gap_pct < 0:
            return "WATCH"  # Don't SELL against market

    # Direction determination
    bullish_signals = 0
    bearish_signals = 0

    if pct_change > 0.5:
        bullish_signals += 1
    elif pct_change < -0.5:
        bearish_signals += 1

    if gap_pct > 0.3:
        bullish_signals += 1
    elif gap_pct < -0.3:
        bearish_signals += 1

    if volume_spike > 1.5:
        # Volume confirms the direction
        if pct_change > 0:
            bullish_signals += 1
        elif pct_change < 0:
            bearish_signals += 1

    if rsi > RSI_OVERBOUGHT:
        bearish_signals += 1  # Overbought = potential reversal
    elif rsi < RSI_OVERSOLD:
        bullish_signals += 1  # Oversold = potential bounce

    if bullish_signals >= 2:
        return "BUY"
    elif bearish_signals >= 2:
        return "SELL"
    return "WATCH"


def score_stocks(stocks_data: List[dict], nifty_pct_change: float = 0.0) -> List[dict]:
    """
    Score all stocks and return sorted list with composite scores.
    stocks_data: list of dicts with technical indicator values.
    """
    if not stocks_data:
        return []

    # Extract values for normalization
    atr_pcts = [s.get("atr_pct", 0) for s in stocks_data]
    vol_spikes = [s.get("volume_spike", 0) for s in stocks_data]
    gap_pcts = [abs(s.get("gap_pct", 0)) for s in stocks_data]

    # Normalize each component to 0-10
    atr_scores = normalize_to_score(atr_pcts, higher_is_better=True)
    vol_scores = normalize_to_score(vol_spikes, higher_is_better=True)
    gap_scores = normalize_to_score(gap_pcts, higher_is_better=True)

    # Phase 2: Materiality is now active.
    # Original: ATR 30%, Vol 25%, Gap 20%, RSI 5%, Materiality 20%
    # No redistribution needed, use exact weights.
    w_atr = WEIGHT_ATR
    w_vol = WEIGHT_VOLUME
    w_gap = WEIGHT_GAP
    w_rsi = WEIGHT_RSI
    w_mat = WEIGHT_MATERIALITY

    scored = []
    for i, stock in enumerate(stocks_data):
        rsi = stock.get("rsi", 50)

        # RSI score: mid-range RSI is neutral, extremes get penalized
        rsi_factor = calculate_rsi_penalty(rsi)

        # Materiality score (0-10) based on AI
        ai_mat = stock.get("materiality", 0.0)
        mat_score = ai_mat * 10.0

        # Composite score (0-10)
        raw_score = (
            atr_scores[i] * w_atr +
            vol_scores[i] * w_vol +
            gap_scores[i] * w_gap +
            mat_score * w_mat
        )
        # Apply RSI as a multiplicative penalty
        combined_score = round(raw_score * rsi_factor, 2)

        # Signal type
        signal_type = determine_signal_type(
            stock.get("pct_change", 0),
            stock.get("gap_pct", 0),
            stock.get("volume_spike", 0),
            rsi,
            nifty_pct_change,
        )

        scored.append({
            **stock,
            "atr_score": atr_scores[i],
            "volume_score": vol_scores[i],
            "gap_score": gap_scores[i],
            "rsi_score": round(rsi_factor * 10, 2),
            "materiality_score": round(mat_score, 2),
            "combined_score": combined_score,
            "signal_type": signal_type,
        })

    # Sort by combined score descending
    scored.sort(key=lambda x: x["combined_score"], reverse=True)

    # Assign ranks
    for i, stock in enumerate(scored):
        stock["rank"] = i + 1

    return scored
