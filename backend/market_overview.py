"""
NSE Volatility Scanner — Market Overview
Fetches Nifty 50, Bank Nifty, India VIX data.
"""

import logging
from datetime import datetime
from backend.signal import MarketOverview
from backend.data_fetcher import fetch_index_data

logger = logging.getLogger(__name__)


def _safe_float(val):
    """Safely extract a float from a pandas value (handles Series, scalar, etc.)."""
    try:
        if hasattr(val, 'iloc'):
            return float(val.iloc[0])
        return float(val)
    except (IndexError, TypeError, ValueError):
        return 0.0


def get_market_overview() -> MarketOverview:
    """Fetch current market overview data."""
    overview = MarketOverview()
    overview.timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Nifty 50
    try:
        nifty_data = fetch_index_data("^NSEI", days=5)
        if nifty_data is not None and len(nifty_data) >= 2:
            price = _safe_float(nifty_data["Close"].iloc[-1])
            prev_price = _safe_float(nifty_data["Close"].iloc[-2])
            if prev_price > 0:
                overview.nifty50_price = round(price, 2)
                overview.nifty50_change = round(price - prev_price, 2)
                overview.nifty50_pct_change = round(((price - prev_price) / prev_price) * 100, 2)
    except Exception as e:
        logger.error(f"Error fetching Nifty 50: {e}")

    # Bank Nifty
    try:
        bank_data = fetch_index_data("^NSEBANK", days=5)
        if bank_data is not None and len(bank_data) >= 2:
            price = _safe_float(bank_data["Close"].iloc[-1])
            prev_price = _safe_float(bank_data["Close"].iloc[-2])
            if prev_price > 0:
                overview.bank_nifty_price = round(price, 2)
                overview.bank_nifty_change = round(price - prev_price, 2)
                overview.bank_nifty_pct_change = round(((price - prev_price) / prev_price) * 100, 2)
    except Exception as e:
        logger.error(f"Error fetching Bank Nifty: {e}")

    # India VIX
    try:
        vix_data = fetch_index_data("^INDIAVIX", days=5)
        if vix_data is not None and len(vix_data) >= 2:
            price = _safe_float(vix_data["Close"].iloc[-1])
            prev_price = _safe_float(vix_data["Close"].iloc[-2])
            if prev_price > 0:
                overview.india_vix = round(price, 2)
                overview.india_vix_change = round(price - prev_price, 2)
                overview.india_vix_pct_change = round(((price - prev_price) / prev_price) * 100, 2)
    except Exception as e:
        logger.error(f"Error fetching India VIX: {e}")

    # Trend filter
    if overview.nifty50_pct_change > 1.0:
        overview.trend_filter = "BULLISH"
    elif overview.nifty50_pct_change < -1.0:
        overview.trend_filter = "BEARISH"
    else:
        overview.trend_filter = "NEUTRAL"

    # Market status
    now = datetime.now()
    current_minutes = now.hour * 60 + now.minute
    if 555 <= current_minutes <= 930 and now.weekday() < 5:  # 9:15 - 15:30
        overview.market_status = "OPEN"
    elif 540 <= current_minutes < 555 and now.weekday() < 5:  # 9:00 - 9:15
        overview.market_status = "PRE-MARKET"
    else:
        overview.market_status = "CLOSED"

    return overview
