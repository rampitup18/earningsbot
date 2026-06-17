from __future__ import annotations
import yfinance as yf
import numpy as np
from datetime import datetime, date
from typing import Optional


def get_spot_price(ticker: str) -> float:
    t = yf.Ticker(ticker)
    info = t.info
    price = (
        info.get("regularMarketPrice")
        or info.get("currentPrice")
        or info.get("previousClose")
        or 0.0
    )
    return float(price)


def get_nearest_expiry_after(ticker: str, target_date: date) -> Optional[str]:
    """Return the first options expiry on or after target_date."""
    try:
        expiries = yf.Ticker(ticker).options
    except Exception:
        return None

    for exp in expiries:
        if datetime.strptime(exp, "%Y-%m-%d").date() >= target_date:
            return exp
    return None


def get_options_snapshot(ticker: str, expiry: str, spot: float) -> dict:
    """
    Return ATM straddle data for the given expiry:
      atm_strike, call_price, put_price, straddle_price,
      expected_move_pct, call_iv, put_iv, atm_iv, iv_skew
    Returns empty dict on failure.
    """
    try:
        chain = yf.Ticker(ticker).option_chain(expiry)
    except Exception:
        return {}

    calls = chain.calls.copy()
    puts = chain.puts.copy()

    if calls.empty or puts.empty:
        return {}

    # ATM = strike closest to spot
    atm_idx = (calls["strike"] - spot).abs().idxmin()
    atm_strike = float(calls.loc[atm_idx, "strike"])

    call_row = calls[calls["strike"] == atm_strike]
    put_row = puts[puts["strike"] == atm_strike]

    if call_row.empty or put_row.empty:
        return {}

    def mid(row):
        b, a = float(row["bid"].iloc[0]), float(row["ask"].iloc[0])
        return (b + a) / 2 if b > 0 and a > 0 else float(row["lastPrice"].iloc[0])

    call_price = mid(call_row)
    put_price = mid(put_row)
    call_iv = float(call_row["impliedVolatility"].iloc[0])
    put_iv = float(put_row["impliedVolatility"].iloc[0])
    straddle = call_price + put_price
    expected_move = straddle / spot if spot > 0 else 0.0
    # Positive skew = put IV > call IV = market pricing downside
    iv_skew = (put_iv - call_iv) / call_iv if call_iv > 0 else 0.0

    return {
        "atm_strike": atm_strike,
        "call_price": call_price,
        "put_price": put_price,
        "straddle_price": straddle,
        "expected_move_pct": expected_move,
        "call_iv": call_iv,
        "put_iv": put_iv,
        "atm_iv": (call_iv + put_iv) / 2,
        "iv_skew": iv_skew,
    }


def get_historical_vol(ticker: str, days: int = 30) -> float:
    """Annualized 30-day realized volatility from daily closes."""
    hist = yf.Ticker(ticker).history(period="3mo", auto_adjust=True)
    if hist.empty or len(hist) < 10:
        return 0.0
    log_returns = np.log(hist["Close"] / hist["Close"].shift(1)).dropna()
    return float(log_returns.tail(days).std() * np.sqrt(252))


def get_price_history(ticker: str, days: int = 30) -> list[float]:
    """Return list of recent closing prices (oldest first)."""
    hist = yf.Ticker(ticker).history(period=f"{days + 10}d", auto_adjust=True)
    if hist.empty:
        return []
    return hist["Close"].tail(days).tolist()
