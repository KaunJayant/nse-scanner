# NSE Volatility Scanner 📊

Real-time NSE stock volatility scanner with AI-powered news sentiment analysis and technical trading signals.

![Python](https://img.shields.io/badge/Python-3.11-blue?logo=python)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?logo=fastapi)
![License](https://img.shields.io/badge/License-MIT-green)

## Features

- **Real-time Market Data** — Fetches OHLCV data for 100+ NSE stocks via yfinance
- **Technical Analysis** — ATR (14), RSI (14), Volume Spike, Gap %, with Wilder's smoothing
- **AI News Sentiment** — Dual-provider pipeline (Groq LLaMA 3.3 70B + Gemini 2.0 Flash fallback)
- **Weighted Scoring** — ATR 30%, Volume 25%, Gap 20%, AI Materiality 20%, RSI 5%
- **Trade Parameters** — Auto-calculated Entry, Stop Loss, Target, R:R ratio, Position Sizing
- **AI Feedback Loop** — Tracks prediction accuracy and injects past mistakes into prompts
- **Nifty Trend Filter** — Suppresses counter-trend signals when Nifty moves >1%

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Backend | FastAPI + Uvicorn (Python) |
| Frontend | Vanilla HTML/CSS/JS |
| Database | SQLite |
| AI | Groq (primary) + Google Gemini (fallback) |
| Data | yfinance + RSS feeds |

## Quick Start

```bash
# Clone
git clone https://github.com/KaunJayant/nse-scanner.git
cd nse-scanner

# Install
pip install -r requirements.txt

# Configure
cp .env.example .env
# Edit .env with your API keys

# Run
python -m backend.main
# Open http://localhost:8000
```

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `GROK_API_KEY` | Yes | Groq API key from [console.x.ai](https://console.x.ai) |
| `GEMINI_API_KEY` | No | Gemini fallback from [aistudio.google.com](https://aistudio.google.com) |

## Architecture

```
Frontend (HTML/JS) → FastAPI REST API → Scanner Pipeline
                                          ├── yfinance (OHLCV data)
                                          ├── RSS feeds (news)
                                          ├── Groq/Gemini (AI sentiment)
                                          ├── Technical indicators
                                          ├── Weighted scoring
                                          └── SQLite (history + feedback)
```

## Disclaimer

> This is a decision-support tool for **educational purposes only**. Not investment advice. Always do your own research before trading.
