# About To Break Range Detector

**Version 1.0** — Stable OHLCV-based crypto scanner.

## Overview

This application scans a fixed watchlist of 25 cryptocurrencies across multiple timeframes (5M, 15M, 1H) to detect consolidation ranges that are approaching a breakout or breakdown. It uses purely **Open, High, Low, Close, and Volume** data to estimate buyer/seller pressure and range readiness.

## Philosophy

- **V1 Only**: No Open Interest, Funding Rates, CVD, or Websockets.
- **Fast & Light**: Cached data served instantly via Flask. Background worker handles API polling.
- **Single Source of Truth**: All calculations stem from the `scanner.py` module.

## Architecture

| File | Responsibility |
| :--- | :--- |
| `server.py` | Gunicorn entry point. Initializes the background cache worker. |
| `app.py` | Flask server, web routes, in-memory cache, and background `update_cache_job`. |
| `scanner.py` | OHLCV fetcher (OKX primary, MEXC fallback), range analyzer, and readiness scorer. |
| `templates/index.html` | Web dashboard rendering the watchlist and scanner opportunities. |

## Default Watchlist

The scanner uses a fixed, immutable list of 25 symbols:

`BTCUSDT, ETHUSDT, SOLUSDT, PEPEUSDT, BONKUSDT, SHIBUSDT, USELESSUSDT, SPACEUSDT, MOVEUSDT, ZECUSDT, SPXUSDT, PEOPLEUSDT, PENGUUSDT, FARTCOINUSDT, LINEAUSDT, MEMEUSDT, PUMPUSDT, AIXBTUSDT, BRETTUSDT, FOGOUSDT, GOOGLUSDT, FLOKIUSDT, IWMUSDT, MOODENGUSDT, NEARUSDT`

## Readiness Score Calculation

The score evaluates:

- **Proximity** to support/resistance.
- **Compression** (higher lows for bullish, lower highs for bearish).
- **Pullback depth** within the range.
- **Buyer/Seller Power** derived from volume-weighted close-to-range ratios.

## Deployment (Render)

1. Point Render to the repository.
2. Use `server.py` as the entry point (`gunicorn server:app`).
3. Ensure `requirements.txt` is installed.

## Logs

The application logs data source usage (OKX vs MEXC) and fetch errors to stdout for monitoring.
