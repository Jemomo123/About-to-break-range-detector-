# coinalyze.py
# =====================================================================
# VERSION 1.0 — ORDER FLOW TELEMETRY PROVIDER
# =====================================================================

import logging
import requests

logger = logging.getLogger(__name__)

COINALYZE_API_KEY = ""  # Set via environment or config if required

def fetch_open_interest(symbol):
    """
    Fetches raw Open Interest telemetry from Coinalyze API.
    Performs ZERO scoring, evaluation, or range boundary logic.
    """
    if not COINALYZE_API_KEY:
        return None

    url = "https://api.coinalyze.net/v1/open-interest"
    params = {
        "symbols": symbol.upper(),
        "api_key": COINALYZE_API_KEY
    }

    try:
        response = requests.get(url, params=params, timeout=10)
        if response.status_code != 200:
            logger.warning(f"Coinalyze API returned status {response.status_code} for {symbol}")
            return None

        data = response.json()
        if isinstance(data, list) and len(data) > 0:
            return data[0].get("value")
        return None

    except Exception as e:
        logger.error(f"Error fetching Coinalyze Open Interest for {symbol}: {e}")
        return None


def fetch_funding_rate(symbol):
    """
    Fetches raw Funding Rate telemetry from Coinalyze API.
    Performs ZERO scoring or evaluation.
    """
    if not COINALYZE_API_KEY:
        return None

    url = "https://api.coinalyze.net/v1/predicted-funding-rate"
    params = {
        "symbols": symbol.upper(),
        "api_key": COINALYZE_API_KEY
    }

    try:
        response = requests.get(url, params=params, timeout=10)
        if response.status_code != 200:
            return None

        data = response.json()
        if isinstance(data, list) and len(data) > 0:
            return data[0].get("value")
        return None

    except Exception as e:
        logger.error(f"Error fetching Coinalyze Funding Rate for {symbol}: {e}")
        return None


def fetch_cvd(symbol):
    """
    Raw telemetry stub for Cumulative Volume Delta (CVD).
    Performs ZERO calculation, scoring, or interpretation.
    """
    if not COINALYZE_API_KEY:
        return None

    # Reserved for raw CVD endpoint integration
    return None
