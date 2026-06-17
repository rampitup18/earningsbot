import yfinance as yf
import numpy as np
from datetime import datetime, timezone, timedelta
from typing import List


def get_past_earnings_moves(ticker: str, n: int = 10) -> List[dict]:
    """
    Return up to N past earnings events with next-day price moves.
    Each entry: {date, move_pct, abs_move, direction}
    """
    t = yf.Ticker(ticker)

    try:
        ed = t.earnings_dates
    except Exception:
        return []

    if ed is None or ed.empty:
        return []

    # Only past dates
    now = datetime.now(timezone.utc)
    past = ed[ed.index < now].head(n)

    if past.empty:
        return []

    # Fetch enough price history to cover all past events
    hist = t.history(period="5y", auto_adjust=True)
    if hist.empty:
        return []

    # Normalize history index to date only
    hist.index = hist.index.tz_localize(None) if hist.index.tzinfo else hist.index
    hist_dates = hist.index.normalize()

    results = []
    for dt in past.index:
        try:
            dt_naive = dt.tz_localize(None) if dt.tzinfo else dt
            event_date = dt_naive.normalize()

            # Close on or before earnings date
            before = hist[hist_dates <= event_date]
            # Close on the first trading day after
            after = hist[hist_dates > event_date]

            if before.empty or after.empty:
                continue

            close_before = float(before["Close"].iloc[-1])
            close_after = float(after["Close"].iloc[0])
            move = (close_after - close_before) / close_before

            results.append({
                "date": event_date.date(),
                "move_pct": move,
                "abs_move": abs(move),
                "direction": "up" if move >= 0 else "down",
            })
        except Exception:
            continue

    return results


def summarize_moves(moves: List[dict], implied_move: float) -> dict:
    """Aggregate historical move stats vs. the current implied move."""
    if not moves:
        return {
            "n": 0,
            "avg_abs_move": 0.0,
            "up_pct": 0.5,
            "beat_implied_pct": 0.0,
            "median_abs_move": 0.0,
        }

    abs_moves = [m["abs_move"] for m in moves]
    up_count = sum(1 for m in moves if m["direction"] == "up")
    beat_count = sum(1 for a in abs_moves if a > implied_move)

    return {
        "n": len(moves),
        "avg_abs_move": float(np.mean(abs_moves)),
        "median_abs_move": float(np.median(abs_moves)),
        "up_pct": up_count / len(moves),
        "beat_implied_pct": beat_count / len(moves),
        "moves": moves,
    }
