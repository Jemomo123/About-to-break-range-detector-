# config.py

OKX_CANDLE_URL = "https://www.okx.com/api/v5/market/candles"
MEXC_CANDLE_URL = "https://contract.mexc.com/api/v1/contract/kline/"

# STRICT REQUIREMENT: Only 5M, 15M, and 1H
SUPPORTED_TIMEFRAMES = ["5M", "15M", "1H"]

OKX_TF_MAP = {
    "5M": "5m",
    "15M": "15m",
    "1H": "1H"
}

MEXC_TF_MAP = {
    "5M": "Min5",
    "15M": "Min15",
    "1H": "Min60"
}

DEFAULT_WATCHLIST = [
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "PENGUUSDT", "PEPEUSDT",
    "BONKUSDT", "FOGOUSDT", "BRETTUSDT", "NEARUSDT", "IWMUSDT",
    "FARTCOINUSDT", "MOVEUSDT", "DOGEUSDT", "SUIUSDT", "APTUSDT",
    "AVAXUSDT", "LINKUSDT", "ARBUSDT", "OPUSDT", "INJUSDT",
    "RENDERUSDT", "TIAUSDT", "SEIUSDT", "FETUSDT", "TAOUSDT"
]
