# config.py

SUPPORTED_TIMEFRAMES = ["3m", "5m", "15m", "1h", "4h"]
DEFAULT_TIMEFRAME = "1h"

# SINGLE AUTHORITATIVE WATCHLIST (25 SYMBOLS)
WATCHLIST = [
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT",
    "ADAUSDT", "DOGEUSDT", "AVAXUSDT", "DOTUSDT", "LINKUSDT",
    "NEARUSDT", "SUIUSDT", "APTUSDT", "PEPEUSDT", "BONKUSDT",
    "SHIBUSDT", "WIFUSDT", "TAOUSDT", "RENDERUSDT", "OPUSDT",
    "ARBUSDT", "INJUSDT", "TIAUSDT", "SUIUSDT", "NEARUSDT"
]

# Deduplicate list while preserving order just in case
WATCHLIST = list(dict.fromkeys(WATCHLIST))

OKX_CANDLE_URL = "https://www.okx.com/api/v5/market/candles"
MEXC_CANDLE_URL = "https://contract.mexc.com/api/v1/contract/kline/"

OKX_TF_MAP = {"3m": "3m", "5m": "5m", "15m": "15m", "1h": "1H", "4h": "4H"}
MEXC_TF_MAP = {"3m": "Min3", "5m": "Min5", "15m": "Min15", "1h": "Min60", "4h": "Hour4"}
