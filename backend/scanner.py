"""
NSE Volatility Scanner — Main Scanner Orchestrator
Coordinates data fetch → indicators → scoring → trade params → signals.
"""

import logging
import time
from datetime import datetime
from typing import List, Optional

from backend.config import DASHBOARD_TOP_N
from backend.signal import Signal, ScanResult
from backend.data_fetcher import load_stock_universe, fetch_stock_data, get_stock_info
from backend.technical import compute_all_indicators
from backend.scorer import score_stocks
from backend.trade_params import calculate_trade_params
from backend.market_overview import get_market_overview
from backend.news_feed import fetch_news
from backend.ai_analyzer import analyze_news_batch
from backend.database import (
    init_db, log_signals, log_scan,
    log_ai_prediction, evaluate_predictions, get_ai_accuracy,
)

logger = logging.getLogger(__name__)

# Cache for last scan result
_last_scan: Optional[ScanResult] = None


def run_scan(force_refresh: bool = False, top_n: int = DASHBOARD_TOP_N) -> ScanResult:
    """
    Run a complete scan cycle.
    1. Fetch market overview
    2. Fetch OHLCV data for all stocks
    3. Compute technical indicators
    4. Score and rank
    5. Calculate trade parameters for top N
    6. Return ScanResult
    """
    global _last_scan
    start_time = time.time()
    errors = []

    logger.info("Starting scan cycle...")

    # Initialize DB
    init_db()

    # 1. Market overview
    try:
        market_overview = get_market_overview()
        nifty_pct = market_overview.nifty50_pct_change
        logger.info(f"Market: Nifty {market_overview.nifty50_price} ({nifty_pct:+.2f}%) | Trend: {market_overview.trend_filter}")
    except Exception as e:
        logger.error(f"Market overview error: {e}")
        errors.append(f"Market overview: {str(e)}")
        market_overview = None
        nifty_pct = 0.0

    # 2. Fetch stock data
    try:
        stock_data = fetch_stock_data(force_refresh=force_refresh)
        logger.info(f"Fetched data for {len(stock_data)} stocks")
    except Exception as e:
        logger.error(f"Data fetch error: {e}")
        errors.append(f"Data fetch: {str(e)}")
        stock_data = {}

    if not stock_data:
        result = ScanResult(
            errors=errors + ["No stock data available"],
            scan_timestamp=datetime.now().isoformat(),
            scan_duration_ms=int((time.time() - start_time) * 1000),
        )
        _last_scan = result
        return result

    # 3. Compute indicators
    universe = load_stock_universe()
    universe_map = {s["symbol"]: s for s in universe}
    stocks_with_indicators = []

    # 2.5 Fetch News & AI Analysis (Phase 2)
    news = []
    ai_results = {}
    try:
        news = fetch_news()
        universe_company_map = {s["symbol"]: s.get("company", s["symbol"]) for s in universe}
        ai_results = analyze_news_batch(news, universe_company_map)
        
        # Attach AI metadata back to news items
        for n in news:
            for symbol, ai_data in ai_results.items():
                if ai_data["headline"] == n.headline:
                    n.symbol = symbol
                    n.direction = ai_data["direction"]
                    n.materiality = ai_data["materiality"]
                    break

    except Exception as e:
        logger.error(f"News/AI error: {e}")
        errors.append(f"News/AI: {str(e)}")

    # 2.6 Log AI predictions for the feedback loop
    for symbol, ai_data in ai_results.items():
        try:
            # Get the current price for this stock
            if symbol in stock_data and not stock_data[symbol].empty:
                cmp = float(stock_data[symbol]["Close"].iloc[-1])
                log_ai_prediction(
                    symbol=symbol,
                    headline=ai_data["headline"],
                    direction=ai_data["direction"],
                    materiality=ai_data["materiality"],
                    price_at_prediction=cmp,
                )
        except Exception as e:
            logger.debug(f"Failed to log AI prediction for {symbol}: {e}")

    # 2.7 Evaluate past predictions against current prices (feedback loop)
    try:
        evaluate_predictions(stock_data)
        accuracy = get_ai_accuracy()
        if accuracy["total_evaluated"] > 0:
            logger.info(
                f"AI Feedback Loop: {accuracy['accuracy_pct']}% accuracy "
                f"({accuracy['correct']}/{accuracy['total_evaluated']} correct)"
            )
    except Exception as e:
        logger.debug(f"Prediction evaluation error: {e}")

    for symbol, df in stock_data.items():
        try:
            indicators = compute_all_indicators(df)
            if indicators:
                info = universe_map.get(symbol, {})
                indicators["symbol"] = symbol
                indicators["company"] = info.get("company", symbol)
                indicators["sector"] = info.get("sector", "Unknown")
                indicators["is_nifty50"] = info.get("is_nifty50", False)
                
                # Inject AI sentiment if available
                if symbol in ai_results:
                    indicators["direction"] = ai_results[symbol]["direction"]
                    indicators["materiality"] = ai_results[symbol]["materiality"]
                    indicators["headline"] = ai_results[symbol]["headline"]
                else:
                    indicators["direction"] = "NEUTRAL"
                    indicators["materiality"] = 0.0
                    indicators["headline"] = ""
                    
                stocks_with_indicators.append(indicators)
        except Exception as e:
            logger.debug(f"Indicator error for {symbol}: {e}")

    logger.info(f"Computed indicators & AI for {len(stocks_with_indicators)} stocks")

    # 4. Score and rank
    scored = score_stocks(stocks_with_indicators, nifty_pct)

    # 5. Build Signal objects for top N
    signals: List[Signal] = []
    for stock in scored[:top_n]:
        # Calculate trade parameters
        trade = calculate_trade_params(
            cmp=stock["cmp"],
            atr=stock["atr"],
            rsi=stock["rsi"],
            gap_pct=stock["gap_pct"],
            is_nifty50=stock.get("is_nifty50", False),
            signal_type=stock["signal_type"],
            day_high=stock.get("day_high", 0),
            day_low=stock.get("day_low", 0),
        )

        signal = Signal(
            rank=stock["rank"],
            symbol=stock["symbol"],
            company=stock["company"],
            sector=stock["sector"],
            cmp=stock["cmp"],
            prev_close=stock["prev_close"],
            day_open=stock["day_open"],
            day_high=stock["day_high"],
            day_low=stock["day_low"],
            volume=stock["volume"],
            pct_change=stock["pct_change"],
            atr=stock["atr"],
            atr_pct=stock["atr_pct"],
            volume_spike=stock["volume_spike"],
            gap_pct=stock["gap_pct"],
            rsi=stock["rsi"],
            atr_score=stock.get("atr_score", 0),
            volume_score=stock.get("volume_score", 0),
            gap_score=stock.get("gap_score", 0),
            rsi_score=stock.get("rsi_score", 0),
            materiality_score=stock.get("materiality_score", 0),
            combined_score=stock["combined_score"],
            direction=stock.get("direction", "NEUTRAL"),
            materiality=stock.get("materiality", 0.0),
            headline=stock.get("headline", ""),
            signal_type=stock["signal_type"],
            entry=trade["entry"],
            stop_loss=trade["stop_loss"],
            target=trade["target"],
            risk_per_share=trade["risk_per_share"],
            reward_per_share=trade["reward_per_share"],
            rr_ratio=trade["rr_ratio"],
            quantity=trade["quantity"],
            max_loss=trade["max_loss"],
            brokerage_estimate=trade["brokerage_estimate"],
            flags=trade["flags"],
            is_nifty50=stock.get("is_nifty50", False),
            timestamp=datetime.now().isoformat(),
        )
        signals.append(signal)

    # 6. Log to database
    try:
        log_signals(signals)
        top_stock = signals[0].symbol if signals else "N/A"
        top_score = signals[0].combined_score if signals else 0.0
        log_scan(len(stocks_with_indicators),
                 int((time.time() - start_time) * 1000),
                 top_stock, top_score)
    except Exception as e:
        logger.error(f"Database logging error: {e}")
        errors.append(f"DB logging: {str(e)}")

    duration_ms = int((time.time() - start_time) * 1000)
    logger.info(f"Scan complete: {len(signals)} signals in {duration_ms}ms")

    result = ScanResult(
        signals=signals,
        market_overview=market_overview,
        news=news,
        scan_timestamp=datetime.now().isoformat(),
        scan_duration_ms=duration_ms,
        stocks_scanned=len(stocks_with_indicators),
        errors=errors,
    )
    _last_scan = result
    return result


def get_last_scan() -> Optional[ScanResult]:
    """Return the last scan result from cache."""
    return _last_scan
