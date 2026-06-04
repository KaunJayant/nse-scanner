"""
NSE Volatility Scanner — Trade Parameter Calculator
Entry, Stop Loss, Target, Position Sizing, R:R, Brokerage.
"""

import math
from backend.config import (
    STOP_LOSS_MULTIPLIER, TARGET_MULTIPLIER, CAPITAL_PER_TRADE,
    MAX_RISK_PCT, MIN_RR_RATIO, SLIPPAGE_NIFTY50, SLIPPAGE_OTHER,
    STT_SELL_PCT, EXCHANGE_TXN_PCT, GST_PCT, SEBI_CHARGES_PER_CRORE,
    RSI_OVERBOUGHT, RSI_OVERSOLD, CIRCUIT_BANDS, CIRCUIT_PROXIMITY_PCT,
)


def calculate_trade_params(
    cmp: float,
    atr: float,
    rsi: float,
    gap_pct: float,
    is_nifty50: bool,
    signal_type: str,
    day_high: float = 0,
    day_low: float = 0,
) -> dict:
    """
    Calculate all trade parameters for a signal.
    Returns dict with entry, stop_loss, target, quantity, flags, etc.
    """
    slippage = SLIPPAGE_NIFTY50 if is_nifty50 else SLIPPAGE_OTHER

    if signal_type == "BUY":
        entry = round(cmp * (1 + slippage), 2)
        stop_loss = round(entry - (atr * STOP_LOSS_MULTIPLIER), 2)
        target = round(entry + (atr * TARGET_MULTIPLIER), 2)
    elif signal_type == "SELL":
        entry = round(cmp * (1 - slippage), 2)
        stop_loss = round(entry + (atr * STOP_LOSS_MULTIPLIER), 2)
        target = round(entry - (atr * TARGET_MULTIPLIER), 2)
    else:
        # WATCH — compute as if BUY for reference
        entry = round(cmp * (1 + slippage), 2)
        stop_loss = round(entry - (atr * STOP_LOSS_MULTIPLIER), 2)
        target = round(entry + (atr * TARGET_MULTIPLIER), 2)

    risk_per_share = round(abs(entry - stop_loss), 2)
    reward_per_share = round(abs(target - entry), 2)

    rr_ratio = round(reward_per_share / risk_per_share, 2) if risk_per_share > 0 else 0.0

    max_loss = CAPITAL_PER_TRADE * MAX_RISK_PCT
    quantity = math.floor(max_loss / risk_per_share) if risk_per_share > 0 else 0

    # Brokerage estimate (Zerodha)
    trade_value = entry * quantity if quantity > 0 else 0
    brokerage = min(20, trade_value * 0.0003)  # ₹20 or 0.03% whichever lower
    stt = trade_value * STT_SELL_PCT  # Only on sell side
    exchange_charges = trade_value * EXCHANGE_TXN_PCT * 2  # Both sides
    gst = (brokerage + exchange_charges) * GST_PCT
    sebi = (trade_value * 2) / 10_000_000 * SEBI_CHARGES_PER_CRORE
    brokerage_estimate = round(brokerage * 2 + stt + exchange_charges + gst + sebi, 2)

    # Flags
    flags = []
    if abs(gap_pct) > 1.0:
        flags.append("GAP RISK")
    if rsi > RSI_OVERBOUGHT:
        flags.append("HIGH RSI")
    if rsi < RSI_OVERSOLD:
        flags.append("LOW RSI")
    # Circuit proximity check
    if cmp > 0 and day_high > 0 and day_low > 0:
        for band in CIRCUIT_BANDS:
            upper_circuit = cmp * (1 + band)
            lower_circuit = cmp * (1 - band)
            if day_high >= upper_circuit * (1 - CIRCUIT_PROXIMITY_PCT):
                flags.append(f"CIRCUIT NEAR {int(band*100)}%")
                break
            if day_low <= lower_circuit * (1 + CIRCUIT_PROXIMITY_PCT):
                flags.append(f"CIRCUIT NEAR {int(band*100)}%")
                break

    return {
        "entry": entry,
        "stop_loss": stop_loss,
        "target": target,
        "risk_per_share": risk_per_share,
        "reward_per_share": reward_per_share,
        "rr_ratio": rr_ratio,
        "quantity": quantity,
        "max_loss": round(max_loss, 2),
        "brokerage_estimate": brokerage_estimate,
        "flags": flags,
    }
