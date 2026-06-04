"""
NSE Volatility Scanner — SQLite Database
Signal logging, outcomes tracking.
"""

import sqlite3
import logging
from datetime import datetime
from pathlib import Path
from typing import List, Optional
from backend.config import DB_PATH
from backend.signal import Signal

logger = logging.getLogger(__name__)


def get_connection() -> sqlite3.Connection:
    """Get SQLite connection, creating the database if needed."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Create tables if they don't exist."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.executescript("""
        CREATE TABLE IF NOT EXISTS signals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            symbol TEXT NOT NULL,
            company TEXT,
            sector TEXT,
            cmp REAL,
            atr REAL,
            atr_pct REAL,
            volume_spike REAL,
            gap_pct REAL,
            rsi REAL,
            materiality REAL,
            direction TEXT,
            headline TEXT,
            combined_score REAL,
            signal_type TEXT,
            entry REAL,
            stop_loss REAL,
            target REAL,
            rr_ratio REAL,
            quantity INTEGER,
            flags TEXT,
            dry_run INTEGER DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS outcomes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            signal_id INTEGER REFERENCES signals(id),
            close_price REAL,
            pct_move REAL,
            hit_target INTEGER,
            hit_stop INTEGER,
            outcome_date TEXT
        );

        CREATE TABLE IF NOT EXISTS news_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            headline TEXT,
            source TEXT,
            symbol TEXT,
            direction TEXT,
            materiality REAL,
            latency_ms INTEGER
        );

        CREATE TABLE IF NOT EXISTS scan_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            stocks_scanned INTEGER,
            duration_ms INTEGER,
            top_stock TEXT,
            top_score REAL
        );

        CREATE TABLE IF NOT EXISTS ai_predictions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            symbol TEXT NOT NULL,
            headline TEXT,
            ai_direction TEXT,
            ai_materiality REAL,
            price_at_prediction REAL,
            price_after REAL,
            actual_pct_move REAL,
            was_correct INTEGER,
            evaluated INTEGER DEFAULT 0,
            evaluated_at TEXT
        );
    """)

    conn.commit()
    conn.close()
    logger.info("Database initialized")


def log_signals(signals: List[Signal]):
    """Log a list of signals to the database."""
    if not signals:
        return

    conn = get_connection()
    cursor = conn.cursor()

    for sig in signals:
        cursor.execute("""
            INSERT INTO signals (
                timestamp, symbol, company, sector, cmp, atr, atr_pct,
                volume_spike, gap_pct, rsi, materiality, direction,
                headline, combined_score, signal_type, entry, stop_loss,
                target, rr_ratio, quantity, flags, dry_run
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
        """, (
            sig.timestamp, sig.symbol, sig.company, sig.sector,
            sig.cmp, sig.atr, sig.atr_pct, sig.volume_spike,
            sig.gap_pct, sig.rsi, sig.materiality, sig.direction,
            sig.headline, sig.combined_score, sig.signal_type,
            sig.entry, sig.stop_loss, sig.target, sig.rr_ratio,
            sig.quantity, sig.flags_str,
        ))

    conn.commit()
    conn.close()
    logger.info(f"Logged {len(signals)} signals to database")


def log_scan(stocks_scanned: int, duration_ms: int, top_stock: str, top_score: float):
    """Log a scan cycle."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO scan_log (timestamp, stocks_scanned, duration_ms, top_stock, top_score)
        VALUES (?, ?, ?, ?, ?)
    """, (datetime.now().isoformat(), stocks_scanned, duration_ms, top_stock, top_score))
    conn.commit()
    conn.close()


def get_recent_signals(limit: int = 50) -> List[dict]:
    """Fetch recent signals from database."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM signals ORDER BY timestamp DESC LIMIT ?
    """, (limit,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_scan_stats() -> dict:
    """Get scan statistics."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) as total FROM signals")
    total_signals = cursor.fetchone()["total"]

    cursor.execute("SELECT COUNT(*) as total FROM scan_log")
    total_scans = cursor.fetchone()["total"]

    cursor.execute("""
        SELECT signal_type, COUNT(*) as count
        FROM signals GROUP BY signal_type
    """)
    signal_counts = {row["signal_type"]: row["count"] for row in cursor.fetchall()}

    conn.close()
    return {
        "total_signals": total_signals,
        "total_scans": total_scans,
        "signal_counts": signal_counts,
    }


def log_ai_prediction(symbol: str, headline: str, direction: str,
                      materiality: float, price_at_prediction: float):
    """Log a single AI prediction for later evaluation."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO ai_predictions
        (timestamp, symbol, headline, ai_direction, ai_materiality, price_at_prediction)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (datetime.now().isoformat(), symbol, headline, direction,
          materiality, price_at_prediction))
    conn.commit()
    conn.close()


def evaluate_predictions(stock_data: dict):
    """
    Check past AI predictions against what actually happened.
    stock_data: dict mapping symbol -> DataFrame with current price info.
    """
    conn = get_connection()
    cursor = conn.cursor()

    # Get unevaluated predictions older than 1 scan cycle
    cursor.execute("""
        SELECT id, symbol, ai_direction, price_at_prediction
        FROM ai_predictions
        WHERE evaluated = 0
        AND timestamp < datetime('now', '-5 minutes')
    """)
    rows = cursor.fetchall()

    for row in rows:
        symbol = row["symbol"]
        if symbol not in stock_data:
            continue

        df = stock_data[symbol]
        if df.empty:
            continue

        current_price = float(df["Close"].iloc[-1])
        pred_price = row["price_at_prediction"]

        if pred_price == 0:
            continue

        actual_pct = ((current_price - pred_price) / pred_price) * 100
        direction = row["ai_direction"]

        # Was the AI correct?
        if direction == "BULLISH" and actual_pct > 0.5:
            was_correct = 1
        elif direction == "BEARISH" and actual_pct < -0.5:
            was_correct = 1
        elif direction == "NEUTRAL" and abs(actual_pct) < 1.0:
            was_correct = 1
        else:
            was_correct = 0

        cursor.execute("""
            UPDATE ai_predictions
            SET price_after = ?, actual_pct_move = ?, was_correct = ?,
                evaluated = 1, evaluated_at = ?
            WHERE id = ?
        """, (current_price, round(actual_pct, 2), was_correct,
              datetime.now().isoformat(), row["id"]))

    conn.commit()
    conn.close()
    logger.info(f"Evaluated {len(rows)} past AI predictions")


def get_ai_mistakes(limit: int = 5) -> List[dict]:
    """
    Get the most recent wrong AI predictions to feed back into the prompt.
    Returns list of dicts with headline, predicted direction, and what actually happened.
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT symbol, headline, ai_direction, ai_materiality,
               actual_pct_move, price_at_prediction, price_after
        FROM ai_predictions
        WHERE evaluated = 1 AND was_correct = 0
        ORDER BY evaluated_at DESC
        LIMIT ?
    """, (limit,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_ai_accuracy() -> dict:
    """Get overall AI prediction accuracy stats."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) as total FROM ai_predictions WHERE evaluated = 1")
    total = cursor.fetchone()["total"]

    cursor.execute("SELECT COUNT(*) as correct FROM ai_predictions WHERE evaluated = 1 AND was_correct = 1")
    correct = cursor.fetchone()["correct"]

    conn.close()
    accuracy = (correct / total * 100) if total > 0 else 0.0
    return {
        "total_evaluated": total,
        "correct": correct,
        "wrong": total - correct,
        "accuracy_pct": round(accuracy, 1),
    }
