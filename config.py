# config.py

SUPPORTED_TIMEFRAMES = ["3m", "5m", "15m", "1h", "4h"]
DEFAULT_TIMEFRAME = "1h"

# UNFILTERED AUTHORITATIVE WATCHLIST (EXACT 25 SYMBOLS)
WATCHLIST = [
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "PEPEUSDT", "BONKUSDT",
    "SHIBUSDT", "USELESSUSDT", "SPACEUSDT", "MOVEUSDT", "ZECUSDT",
    "SPXUSDT", "PEOPLEUSDT", "PENGUUSDT", "FARTCOINUSDT", "LINEAUSDT",
    "MEMEUSDT", "PUMPUSDT", "AIXBTUSDT", "BRETTUSDT", "FOGOUSDT",
    "GOOGLUSDT", "FLOKIUSDT", "IWMUSDT", "MOODENGUSDT", "NEARUSDT"
]

OKX_CANDLE_URL = "https://www.okx.com/api/v5/market/candles"
MEXC_CANDLE_URL = "https://contract.mexc.com/api/v1/contract/kline/"

OKX_TF_MAP = {"3m": "3m", "5m": "5m", "15m": "15m", "1h": "1H", "4h": "4H"}
MEXC_TF_MAP = {"3m": "Min3", "5m": "Min5", "15m": "Min15", "1h": "Min60", "4h": "Hour4"}
