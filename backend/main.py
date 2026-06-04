"""
NSE Volatility Scanner — FastAPI Backend
REST API + static file serving for the dashboard.
"""

import os
import sys
import logging
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from backend.config import DASHBOARD_PORT, FRONTEND_DIR, DASHBOARD_TOP_N
from backend.scanner import run_scan, get_last_scan
from backend.database import init_db, get_recent_signals, get_scan_stats, get_ai_accuracy
from backend.news_feed import fetch_news

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("nse_scanner")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    logger.info("=" * 60)
    logger.info("  NSE Volatility Scanner — Starting Up")
    logger.info("=" * 60)
    init_db()
    logger.info("Database initialized")
    logger.info(f"Frontend dir: {FRONTEND_DIR}")
    logger.info(f"Dashboard will be available at http://localhost:{DASHBOARD_PORT}")
    yield
    logger.info("Shutting down...")


app = FastAPI(
    title="NSE Volatility Scanner",
    description="Real-time NSE stock volatility scanner with technical analysis",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── API Routes ───────────────────────────────────────────────────────────────

@app.get("/api/scan")
async def api_scan(force: bool = False, top_n: int = DASHBOARD_TOP_N):
    """Run a scan and return results."""
    try:
        result = run_scan(force_refresh=force, top_n=top_n)
        return JSONResponse(content=result.to_dict())
    except Exception as e:
        logger.error(f"Scan error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/last-scan")
async def api_last_scan():
    """Get the last scan result from cache."""
    result = get_last_scan()
    if result:
        return JSONResponse(content=result.to_dict())
    return JSONResponse(content={"signals": [], "market_overview": None, "news": [], "errors": ["No scan data yet. Trigger a scan first."]})


@app.get("/api/news")
async def api_news(limit: int = 20):
    """Fetch latest news."""
    try:
        news = fetch_news(max_items=limit)
        return JSONResponse(content=[n.to_dict() for n in news])
    except Exception as e:
        logger.error(f"News error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/signals/history")
async def api_signal_history(limit: int = 50):
    """Get recent signal history from database."""
    try:
        signals = get_recent_signals(limit=limit)
        return JSONResponse(content=signals)
    except Exception as e:
        logger.error(f"History error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/stats")
async def api_stats():
    """Get scan statistics."""
    try:
        stats = get_scan_stats()
        return JSONResponse(content=stats)
    except Exception as e:
        logger.error(f"Stats error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/health")
async def api_health():
    """Health check."""
    return {"status": "ok", "service": "NSE Volatility Scanner"}


@app.get("/api/ai-accuracy")
async def api_ai_accuracy():
    """Get AI prediction accuracy from the feedback loop."""
    try:
        accuracy = get_ai_accuracy()
        return JSONResponse(content=accuracy)
    except Exception as e:
        logger.error(f"AI accuracy error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ─── Static Files (Frontend) ─────────────────────────────────────────────────

# Serve static files (CSS, JS)
app.mount("/css", StaticFiles(directory=str(FRONTEND_DIR / "css")), name="css")
app.mount("/js", StaticFiles(directory=str(FRONTEND_DIR / "js")), name="js")


@app.get("/")
async def serve_dashboard():
    """Serve the main dashboard HTML."""
    index_path = FRONTEND_DIR / "index.html"
    if index_path.exists():
        return FileResponse(str(index_path))
    raise HTTPException(status_code=404, detail="Dashboard not found")


# ─── Entry Point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", DASHBOARD_PORT))
    uvicorn.run(
        "backend.main:app",
        host="0.0.0.0",
        port=port,
        reload=False,
        log_level="info",
    )
