"""
NSE Volatility Scanner — Configuration
All settings, thresholds, and scoring weights.
Loaded from environment variables where applicable.
"""

import os
from dotenv import load_dotenv
from pathlib import Path

# Load .env from project root
_env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(_env_path)

# ─── Paths ────────────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
FRONTEND_DIR = PROJECT_ROOT / "frontend"
STOCK_UNIVERSE_FILE = DATA_DIR / "stock_universe.json"
DB_PATH = DATA_DIR / "scanner.db"

# ─── Dashboard ────────────────────────────────────────────────────────────────
DASHBOARD_PORT = int(os.getenv("PORT", os.getenv("DASHBOARD_PORT", "8000")))
DASHBOARD_TOP_N = 15  # Number of top stocks to display

# ─── Scoring Weights (must sum to 1.0) ────────────────────────────────────────
# When materiality (news) data is available:
WEIGHT_ATR = 0.30
WEIGHT_VOLUME = 0.25
WEIGHT_GAP = 0.20
WEIGHT_RSI = 0.05
WEIGHT_MATERIALITY = 0.20

# When NO news is available (redistribute materiality proportionally):
# ATR, Volume, Gap, RSI get their share of the 0.20 materiality weight
# Redistribution is handled dynamically in scorer.py

# ─── Technical Parameters ─────────────────────────────────────────────────────
ATR_PERIOD = 14            # Wilder's 14-period ATR
VOLUME_AVG_PERIOD = 20     # 20-day average volume for spike calculation
RSI_PERIOD = 14            # 14-period RSI
RSI_OVERBOUGHT = 70        # RSI > 70 = overbought penalty
RSI_OVERSOLD = 30          # RSI < 30 = oversold penalty

# ─── Trade Parameters ─────────────────────────────────────────────────────────
STOP_LOSS_MULTIPLIER = 1.5       # SL = Entry - (ATR × 1.5)
TARGET_MULTIPLIER = 3.0          # Target = Entry + (ATR × 3.0)
CAPITAL_PER_TRADE = 50_000       # ₹50,000 per trade
MAX_RISK_PCT = 0.02              # 2% max risk per trade
MIN_RR_RATIO = 2.0               # Minimum Risk:Reward ratio to qualify
SLIPPAGE_NIFTY50 = 0.003         # 0.3% slippage for Nifty 50 stocks
SLIPPAGE_OTHER = 0.005           # 0.5% slippage for other stocks

# ─── Brokerage Costs (Zerodha) ────────────────────────────────────────────────
STT_SELL_PCT = 0.001             # 0.1% STT on sell side
EXCHANGE_TXN_PCT = 0.0000335     # 0.00335% exchange transaction charges
GST_PCT = 0.18                   # 18% GST on brokerage + exchange charges
SEBI_CHARGES_PER_CRORE = 10      # ₹10 per crore traded

# ─── Trend Filter (Hard Gate) ─────────────────────────────────────────────────
NIFTY_TREND_THRESHOLD = 0.01  # 1% — if Nifty > +1%, suppress SELL; < -1%, suppress BUY

# ─── Market Hours (IST) ──────────────────────────────────────────────────────
MARKET_OPEN_HOUR = 9
MARKET_OPEN_MINUTE = 15
MARKET_CLOSE_HOUR = 15
MARKET_CLOSE_MINUTE = 30

# ─── Refresh Settings ────────────────────────────────────────────────────────
SCORE_REFRESH_MINUTES = 5        # How often to recalculate scores
NEWS_POLL_MINUTES = 2            # How often to fetch news

# ─── Data Fetch Settings ─────────────────────────────────────────────────────
HISTORICAL_DAYS = 45             # Days of OHLC history to fetch (need ~30 for ATR/RSI + buffer)
YFINANCE_BATCH_SIZE = 50         # Stocks per yfinance batch to avoid rate limits
YFINANCE_BATCH_DELAY = 1.0       # Seconds between batches

# ─── Circuit Breaker Bands ───────────────────────────────────────────────────
CIRCUIT_BANDS = [0.05, 0.10, 0.20]  # 5%, 10%, 20% price bands
CIRCUIT_PROXIMITY_PCT = 0.01         # Flag if within 1% of circuit limit

# ─── Nifty 50 Symbols (for slippage differentiation) ─────────────────────────
# Loaded dynamically from stock_universe.json, but kept here as reference
NIFTY50_YFINANCE_TICKERS = {
    "^NSEI": "Nifty 50",
    "^NSEBANK": "Bank Nifty",
    "^INDIAVIX": "India VIX",
}

# ─── News RSS Feeds ──────────────────────────────────────────────────────────
NEWS_RSS_FEEDS = [
    {
        "name": "Economic Times Markets",
        "url": "https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms",
    },
    {
        "name": "MoneyControl",
        "url": "https://www.moneycontrol.com/rss/latestnews.xml",
    },
    {
        "name": "LiveMint Markets",
        "url": "https://www.livemint.com/rss/markets",
    },
]

# ─── API Keys ────────────────────────────────────────────────────────────────
KITE_API_KEY = os.getenv("KITE_API_KEY", "")
KITE_API_SECRET = os.getenv("KITE_API_SECRET", "")
KITE_ACCESS_TOKEN = os.getenv("KITE_ACCESS_TOKEN", "")

# AI Providers (Groq primary, Gemini fallback)
GROQ_API_KEY = os.getenv("GROK_API_KEY", "")  # .env uses GROK_API_KEY for backwards compat
GROQ_MODEL = os.getenv("GROK_MODEL", "llama-3.3-70b-versatile")
GROQ_API_BASE = "https://api.groq.com/openai/v1"
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

# ─── AI Rate Limiting & Retry ────────────────────────────────────────────────
AI_MAX_RETRIES = 3                # Max retries on 429/5xx errors
AI_BASE_DELAY = 2.0              # Base delay in seconds (doubles each retry: 2s, 4s, 8s)

# ─── Mode ────────────────────────────────────────────────────────────────────
DRY_RUN = True  # Always True in Phase 1. No live orders.
