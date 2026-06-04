"""
NSE Volatility Scanner — Data Fetcher
yfinance wrapper for fetching OHLCV data for all stocks.
Uses individual Ticker downloads for reliability with yfinance 1.3+.
"""

import json
import time
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional

import pandas as pd
import yfinance as yf

from backend.config import (
    STOCK_UNIVERSE_FILE, HISTORICAL_DAYS,
    YFINANCE_BATCH_SIZE, YFINANCE_BATCH_DELAY,
)

logger = logging.getLogger(__name__)

# Cache for stock data
_data_cache: Dict[str, pd.DataFrame] = {}
_cache_timestamp: Optional[datetime] = None
_universe_cache: Optional[List[dict]] = None


def load_stock_universe() -> List[dict]:
    """Load stock universe from JSON file."""
    global _universe_cache
    if _universe_cache is not None:
        return _universe_cache
    with open(STOCK_UNIVERSE_FILE, "r") as f:
        _universe_cache = json.load(f)
    logger.info(f"Loaded {len(_universe_cache)} stocks from universe file")
    return _universe_cache


def get_yf_ticker(symbol: str) -> str:
    """Convert NSE symbol to yfinance ticker format. yfinance handles M&M.NS natively."""
    return f"{symbol}.NS"


def fetch_stock_data(
    symbols: Optional[List[str]] = None,
    days: int = HISTORICAL_DAYS,
    force_refresh: bool = False,
) -> Dict[str, pd.DataFrame]:
    """
    Fetch OHLCV data for all stocks.
    Uses batch yf.download with MultiIndex column parsing for yfinance 1.3+.
    """
    global _data_cache, _cache_timestamp

    # Use cache if fresh (< 3 minutes old) and not forced
    if (
        not force_refresh
        and _cache_timestamp
        and (datetime.now() - _cache_timestamp).total_seconds() < 180
        and _data_cache
    ):
        logger.info("Using cached data")
        return _data_cache

    if symbols is None:
        universe = load_stock_universe()
        symbols = [s["symbol"] for s in universe]

    end_date = datetime.now()
    start_date = end_date - timedelta(days=days)
    start_str = start_date.strftime("%Y-%m-%d")
    end_str = end_date.strftime("%Y-%m-%d")

    all_data: Dict[str, pd.DataFrame] = {}
    failed: List[str] = []

    # Process in batches
    for i in range(0, len(symbols), YFINANCE_BATCH_SIZE):
        batch = symbols[i:i + YFINANCE_BATCH_SIZE]
        tickers = [get_yf_ticker(s) for s in batch]

        logger.info(f"Fetching batch {i // YFINANCE_BATCH_SIZE + 1}: {len(batch)} stocks")

        try:
            data = yf.download(
                tickers,
                start=start_str,
                end=end_str,
                progress=False,
                threads=True,
                auto_adjust=True,
            )

            if data.empty:
                failed.extend(batch)
                continue

            # yfinance 1.3+ returns MultiIndex columns: (Price, Ticker)
            if isinstance(data.columns, pd.MultiIndex):
                # Get available tickers from the downloaded data
                if data.columns.nlevels == 2:
                    available_tickers = data.columns.get_level_values(1).unique().tolist()
                else:
                    available_tickers = data.columns.get_level_values(0).unique().tolist()

                for sym, yf_ticker in zip(batch, tickers):
                    try:
                        # Try to extract this ticker's data
                        # Columns are like (Close, RELIANCE.NS), (Open, RELIANCE.NS), etc.
                        if data.columns.nlevels == 2:
                            # Check if ticker is in level 1
                            if yf_ticker in available_tickers:
                                stock_df = data.xs(yf_ticker, axis=1, level=1).copy()
                            else:
                                failed.append(sym)
                                continue
                        else:
                            stock_df = data[yf_ticker].copy()

                        stock_df = stock_df.dropna(subset=["Close"])
                        if len(stock_df) > 0:
                            all_data[sym] = stock_df
                        else:
                            failed.append(sym)
                    except (KeyError, TypeError, ValueError) as e:
                        failed.append(sym)
            else:
                # Single ticker returned (no MultiIndex)
                if len(batch) == 1:
                    stock_df = data.dropna(subset=["Close"])
                    if len(stock_df) > 0:
                        all_data[batch[0]] = stock_df
                    else:
                        failed.append(batch[0])
                else:
                    # Shouldn't happen, but handle gracefully
                    failed.extend(batch)

        except Exception as e:
            logger.error(f"Batch download error: {e}")
            failed.extend(batch)

        # Delay between batches
        if i + YFINANCE_BATCH_SIZE < len(symbols):
            time.sleep(YFINANCE_BATCH_DELAY)

    if failed:
        logger.warning(f"Failed: {len(failed)} stocks (e.g. {failed[:5]})")

    logger.info(f"Successfully fetched data for {len(all_data)}/{len(symbols)} stocks")

    _data_cache = all_data
    _cache_timestamp = datetime.now()
    return all_data


def fetch_index_data(ticker: str, days: int = 5) -> Optional[pd.DataFrame]:
    """Fetch data for a market index (e.g., ^NSEI, ^NSEBANK)."""
    try:
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)
        data = yf.download(
            ticker,
            start=start_date.strftime("%Y-%m-%d"),
            end=end_date.strftime("%Y-%m-%d"),
            progress=False,
            auto_adjust=True,
        )
        if not data.empty:
            # Flatten MultiIndex columns if present
            if isinstance(data.columns, pd.MultiIndex):
                data.columns = data.columns.get_level_values(0)
            return data
    except Exception as e:
        logger.error(f"Error fetching index {ticker}: {e}")
    return None


def get_stock_info(symbol: str) -> dict:
    """Get stock info from the universe file."""
    universe = load_stock_universe()
    for stock in universe:
        if stock["symbol"] == symbol:
            return stock
    return {"symbol": symbol, "company": symbol, "sector": "Unknown", "is_nifty50": False}


def clear_cache():
    """Clear the data cache."""
    global _data_cache, _cache_timestamp
    _data_cache = {}
    _cache_timestamp = None
