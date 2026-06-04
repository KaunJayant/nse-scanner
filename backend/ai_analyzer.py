"""
NSE Volatility Scanner — AI News Analyzer
Primary: Groq (LPU inference) via OpenAI-compatible API
Fallback: Google Gemini
Features: Exponential backoff, rate limiting, retry logic.
"""

import json
import time
import logging
import threading
from typing import Dict, List, Optional

from backend.signal import NewsItem
from backend.config import GROQ_API_KEY, GROQ_MODEL, GROQ_API_BASE, GEMINI_API_KEY, AI_MAX_RETRIES, AI_BASE_DELAY

logger = logging.getLogger(__name__)

# ─── Rate Limiter ─────────────────────────────────────────────────────────────

class RateLimiter:
    """Simple token-bucket rate limiter. Thread-safe."""

    def __init__(self, max_calls: int, per_seconds: float):
        self.max_calls = max_calls
        self.per_seconds = per_seconds
        self._calls: List[float] = []
        self._lock = threading.Lock()

    def wait(self):
        """Block until a call is allowed."""
        while True:
            with self._lock:
                now = time.time()
                # Purge old timestamps
                self._calls = [t for t in self._calls if now - t < self.per_seconds]
                if len(self._calls) < self.max_calls:
                    self._calls.append(now)
                    return
            # Wait a fraction of the window before retrying
            time.sleep(self.per_seconds / self.max_calls)


# 10 calls per 60 seconds — conservative for both Grok and Gemini
_rate_limiter = RateLimiter(max_calls=10, per_seconds=60)


# ─── Client Initialization ───────────────────────────────────────────────────

_groq_client = None
_gemini_client = None

if GROQ_API_KEY:
    try:
        from openai import OpenAI
        _groq_client = OpenAI(
            api_key=GROQ_API_KEY,
            base_url=GROQ_API_BASE,
        )
        logger.info(f"Groq client initialized — primary AI provider (model: {GROQ_MODEL})")
    except ImportError:
        logger.error("openai package not installed. Run: pip install openai")
    except Exception as e:
        logger.error(f"Failed to initialize Groq client: {e}")

if GEMINI_API_KEY:
    try:
        from google import genai
        _gemini_client = genai.Client(api_key=GEMINI_API_KEY)
        logger.info("Gemini client initialized — fallback AI provider")
    except ImportError:
        logger.warning("google-genai package not installed. Gemini fallback unavailable.")
    except Exception as e:
        logger.error(f"Failed to initialize Gemini client: {e}")


# ─── Prompt Builder ──────────────────────────────────────────────────────────

def _build_prompt(news_items: List[NewsItem], universe_map: Dict[str, str]) -> str:
    """Build the classification prompt for the AI model."""
    prompt = "You are a financial news classifier for Indian equity markets (NSE).\n\n"
    prompt += "Here are the latest financial news headlines:\n"
    for item in news_items:
        prompt += f"- {item.headline} (Source: {item.source})\n"

    prompt += "\nHere is our active stock universe (Symbol: Company Name):\n"
    for sym, comp in list(universe_map.items()):
        prompt += f"{sym}: {comp}\n"

    prompt += """
Task: Analyze each headline. If a headline is specifically about a company in our universe, classify it.

For each match, return a JSON object with these fields:
- symbol: The EXACT NSE symbol from the list above
- direction: "BULLISH", "BEARISH", or "NEUTRAL"
- materiality: A float 0.0 to 1.0 (1.0 = massive impact like earnings, mergers, SEBI bans; 0.1 = minor)
- headline: The exact headline that matched

CRITICAL RULES:
- IGNORE broker opinions ("Stock to buy", "Broker cuts target price") — these are NOT facts.
- IGNORE predictions ("Will Tata Motors crash?") — materiality 0.0
- IGNORE clickbait and sarcasm
- ONLY score materiality > 0.0 for HARD FACTS: earnings, management changes, contracts, regulatory actions, deal announcements
- If headline is about a sector/macro trend, not a specific stock, materiality should be 0.1-0.3 max
- If headline is not in English or unclear, treat as NEUTRAL with 0.0 materiality

Return your response as a JSON object with this exact structure:
{"sentiments": [{"symbol": "...", "direction": "...", "materiality": 0.0, "headline": "..."}]}

If no headlines match any stocks, return: {"sentiments": []}
"""

    # Inject lessons from past mistakes (feedback loop)
    mistakes_section = _build_mistakes_section()
    if mistakes_section:
        prompt += mistakes_section
        logger.info("Injected feedback loop: AI will learn from past mistakes")

    return prompt


def _build_mistakes_section() -> str:
    """
    Build a 'lessons learned' section from past wrong predictions.
    This is the core of the feedback loop — teaching the AI from its own errors.
    """
    try:
        from backend.database import get_ai_mistakes
        mistakes = get_ai_mistakes(limit=5)
    except Exception:
        return ""

    if not mistakes:
        return ""

    section = "\n\n--- LESSONS FROM YOUR PAST MISTAKES (learn from these) ---\n"
    section += "You previously made the following incorrect predictions. Adjust your reasoning accordingly:\n"

    for m in mistakes:
        section += (
            f"- You read \"{m['headline']}\" and predicted {m['ai_direction']} "
            f"with materiality {m['ai_materiality']:.1f}. "
            f"But the stock actually moved {m['actual_pct_move']:+.2f}%. "
            f"Your prediction was WRONG.\n"
        )

    section += (
        "\nUse these mistakes to calibrate. If you see similar headlines, "
        "be more conservative or flip your direction.\n"
        "--- END OF LESSONS ---\n"
    )
    return section


# ─── Retry with Exponential Backoff ──────────────────────────────────────────

def _retry_with_backoff(fn, provider_name: str) -> Optional[dict]:
    """
    Call `fn` with exponential backoff on 429/5xx errors.
    Returns parsed JSON dict or None on failure.
    """
    for attempt in range(1, AI_MAX_RETRIES + 1):
        try:
            _rate_limiter.wait()  # Throttle before every call
            result = fn()
            return result
        except Exception as e:
            error_str = str(e)
            is_rate_limit = "429" in error_str or "RESOURCE_EXHAUSTED" in error_str or "rate" in error_str.lower()
            is_server_error = any(code in error_str for code in ["500", "502", "503", "504"])

            if is_rate_limit or is_server_error:
                delay = AI_BASE_DELAY * (2 ** (attempt - 1))  # 2s, 4s, 8s, 16s...
                logger.warning(
                    f"{provider_name} attempt {attempt}/{AI_MAX_RETRIES} failed "
                    f"({'rate limit' if is_rate_limit else 'server error'}). "
                    f"Retrying in {delay}s..."
                )
                time.sleep(delay)
            else:
                # Non-retryable error (auth, bad request, etc.)
                logger.error(f"{provider_name} non-retryable error: {e}")
                return None

    logger.error(f"{provider_name} exhausted all {AI_MAX_RETRIES} retries")
    return None


# ─── Groq Provider ──────────────────────────────────────────────────────────

def _call_groq(prompt: str) -> Optional[dict]:
    """Call Groq API with structured JSON output."""
    if not _groq_client:
        return None

    def _do_call():
        response = _groq_client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[
                {"role": "system", "content": "You are a precise financial news classifier. Always respond with valid JSON only."},
                {"role": "user", "content": prompt},
            ],
            response_format={"type": "json_object"},
            temperature=0.1,
        )
        content = response.choices[0].message.content
        parsed = json.loads(content)
        return parsed

    return _retry_with_backoff(_do_call, "Groq")


# ─── Gemini Provider ────────────────────────────────────────────────────────

def _call_gemini(prompt: str) -> Optional[dict]:
    """Call Gemini API with structured JSON output."""
    if not _gemini_client:
        return None

    from pydantic import BaseModel, Field

    class StockSentiment(BaseModel):
        symbol: str = Field(description="The exact stock symbol from the universe")
        direction: str = Field(description="BULLISH, BEARISH, or NEUTRAL")
        materiality: float = Field(description="0.0 to 1.0 impact score")
        headline: str = Field(description="The matched headline")

    class SentimentResponse(BaseModel):
        sentiments: List[StockSentiment]

    def _do_call():
        response = _gemini_client.models.generate_content(
            model='gemini-2.0-flash',
            contents=prompt,
            config={
                'response_mime_type': 'application/json',
                'response_schema': SentimentResponse,
                'temperature': 0.1,
            },
        )
        parsed_data = response.parsed
        if not parsed_data:
            raise ValueError("Gemini returned empty response")
        # Convert Pydantic model to dict
        return {"sentiments": [s.model_dump() for s in parsed_data.sentiments]}

    return _retry_with_backoff(_do_call, "Gemini")


# ─── Main Entry Point ───────────────────────────────────────────────────────

def analyze_news_batch(news_items: List[NewsItem], universe_map: Dict[str, str]) -> Dict[str, dict]:
    """
    Analyze news headlines using AI (Groq primary, Gemini fallback).
    Returns dict mapping symbol -> {direction, materiality, headline}
    """
    if not news_items:
        return {}

    if not _groq_client and not _gemini_client:
        logger.warning("No AI provider configured. Set GROK_API_KEY or GEMINI_API_KEY in .env")
        return {}

    prompt = _build_prompt(news_items, universe_map)
    parsed = None

    # Try Groq first (primary)
    if _groq_client:
        logger.info(f"Sending {len(news_items)} headlines to Groq ({GROQ_MODEL}) for analysis...")
        start = time.time()
        parsed = _call_groq(prompt)
        if parsed:
            latency = int((time.time() - start) * 1000)
            logger.info(f"Groq responded in {latency}ms")

    # Fallback to Gemini
    if parsed is None and _gemini_client:
        logger.info(f"Groq unavailable. Falling back to Gemini...")
        start = time.time()
        parsed = _call_gemini(prompt)
        if parsed:
            latency = int((time.time() - start) * 1000)
            logger.info(f"Gemini responded in {latency}ms")

    # Both failed — return empty (scorer redistributes weights to technical-only)
    if parsed is None:
        logger.warning("All AI providers failed. Scoring will use technical indicators only.")
        return {}

    # Parse the response into our format
    result_map = {}
    sentiments = parsed.get("sentiments", [])
    for item in sentiments:
        symbol = item.get("symbol", "")
        if symbol in universe_map:
            direction = item.get("direction", "NEUTRAL").upper()
            if direction not in ("BULLISH", "BEARISH", "NEUTRAL"):
                direction = "NEUTRAL"
            materiality = min(1.0, max(0.0, float(item.get("materiality", 0.0))))
            result_map[symbol] = {
                "direction": direction,
                "materiality": materiality,
                "headline": item.get("headline", ""),
            }

    logger.info(f"AI matched {len(result_map)} headlines to universe symbols")
    return result_map
