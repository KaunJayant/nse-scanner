"""
NSE Volatility Scanner — Signal Data Model
Dataclass representing a trading signal with all computed fields.
"""

from dataclasses import dataclass, field, asdict
from typing import Optional, List


@dataclass
class Signal:
    """A single trading signal for one stock."""

    # Identity
    rank: int = 0
    symbol: str = ""
    company: str = ""
    sector: str = ""

    # Price data
    cmp: float = 0.0            # Current Market Price
    prev_close: float = 0.0
    day_open: float = 0.0
    day_high: float = 0.0
    day_low: float = 0.0
    volume: int = 0
    pct_change: float = 0.0     # Today's % change

    # Technical indicators
    atr: float = 0.0            # ATR in rupees
    atr_pct: float = 0.0        # ATR as % of CMP
    volume_spike: float = 0.0   # Today's volume / 20-day avg
    gap_pct: float = 0.0        # (Open - Prev Close) / Prev Close
    rsi: float = 0.0            # 14-period RSI

    # Scores (normalized 0-10)
    atr_score: float = 0.0
    volume_score: float = 0.0
    gap_score: float = 0.0
    rsi_score: float = 0.0
    materiality_score: float = 0.0  # Phase 2: Claude/Gemini score
    combined_score: float = 0.0     # Final composite score

    # Sentiment (Phase 2)
    direction: str = ""         # bullish / bearish / neutral
    materiality: float = 0.0   # 0.0 - 1.0
    headline: str = ""          # Matched headline, if any

    # Signal
    signal_type: str = ""       # BUY / SELL / WATCH

    # Trade parameters
    entry: float = 0.0          # Entry price (with slippage)
    stop_loss: float = 0.0
    target: float = 0.0
    risk_per_share: float = 0.0
    reward_per_share: float = 0.0
    rr_ratio: float = 0.0
    quantity: int = 0
    max_loss: float = 0.0
    brokerage_estimate: float = 0.0

    # Flags
    flags: List[str] = field(default_factory=list)

    # Meta
    is_nifty50: bool = False
    timestamp: str = ""

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)

    @property
    def flags_str(self) -> str:
        """Return flags as comma-separated string."""
        return ", ".join(self.flags) if self.flags else "—"


@dataclass
class MarketOverview:
    """Market-level data for the dashboard header."""

    nifty50_price: float = 0.0
    nifty50_change: float = 0.0
    nifty50_pct_change: float = 0.0

    bank_nifty_price: float = 0.0
    bank_nifty_change: float = 0.0
    bank_nifty_pct_change: float = 0.0

    india_vix: float = 0.0
    india_vix_change: float = 0.0
    india_vix_pct_change: float = 0.0

    trend_filter: str = "NEUTRAL"  # BULLISH / BEARISH / NEUTRAL
    market_status: str = "CLOSED"  # OPEN / CLOSED / PRE-MARKET

    timestamp: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class NewsItem:
    """A single news headline."""

    headline: str = ""
    source: str = ""
    published: str = ""
    link: str = ""
    symbol: Optional[str] = None      # Matched symbol (Phase 2)
    direction: Optional[str] = None    # bullish/bearish/neutral (Phase 2)
    materiality: Optional[float] = None  # 0.0-1.0 (Phase 2)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ScanResult:
    """Complete result of one scan cycle."""

    signals: List[Signal] = field(default_factory=list)
    market_overview: Optional[MarketOverview] = None
    news: List[NewsItem] = field(default_factory=list)
    scan_timestamp: str = ""
    scan_duration_ms: int = 0
    stocks_scanned: int = 0
    errors: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "signals": [s.to_dict() for s in self.signals],
            "market_overview": self.market_overview.to_dict() if self.market_overview else None,
            "news": [n.to_dict() for n in self.news],
            "scan_timestamp": self.scan_timestamp,
            "scan_duration_ms": self.scan_duration_ms,
            "stocks_scanned": self.stocks_scanned,
            "errors": self.errors,
        }
