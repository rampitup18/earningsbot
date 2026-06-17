from __future__ import annotations
import numpy as np
from dataclasses import dataclass


@dataclass
class Signal:
    name: str
    direction: float   # -1.0 (bearish) → 0 (neutral) → +1.0 (bullish)
    confidence: float  # 0 → 1
    detail: str


def score_iv_skew(put_iv: float, call_iv: float) -> Signal:
    """
    Positive skew (put_iv > call_iv) = market pricing downside = bearish lean.
    Negative skew = calls pricier = bullish lean.
    """
    if call_iv == 0:
        return Signal("iv_skew", 0.0, 0.0, "No IV data available")

    skew = (put_iv - call_iv) / call_iv
    # Flip sign: put more expensive → bearish
    direction = float(-np.clip(skew * 6, -1, 1))
    confidence = float(min(abs(skew) * 4, 1.0))

    if skew > 0.05:
        label = f"puts {skew:.1%} more expensive — market fears downside"
    elif skew < -0.05:
        label = f"calls {abs(skew):.1%} more expensive — market leans bullish"
    else:
        label = "IV roughly balanced"

    return Signal("iv_skew", direction, confidence, label)


def score_historical_direction(moves: list) -> Signal:
    """Does this stock consistently move up or down on earnings?"""
    if len(moves) < 4:
        return Signal("hist_direction", 0.0, 0.0,
                       f"Only {len(moves)} prior earnings — no pattern")

    n = len(moves)
    up_pct = sum(1 for m in moves if m["direction"] == "up") / n
    avg_abs = np.mean([m["abs_move"] for m in moves])

    # 50% up → direction 0; 100% up → direction +1; 0% up → direction -1
    direction = float((up_pct - 0.5) * 2)
    # More historical data + more extreme win rate → higher confidence
    confidence = float(min(abs(direction) * (n / 8), 1.0))

    return Signal(
        "hist_direction",
        direction,
        confidence,
        f"Moved up {up_pct:.0%} of last {n} earnings (avg ±{avg_abs:.1%})",
    )


def score_premium_value(beat_implied_pct: float, iv_hv_ratio: float) -> Signal:
    """
    Is buying premium worthwhile? Good conditions:
    - stock historically beats the implied move (beat_implied_pct is high)
    - IV not wildly inflated vs realized vol (iv_hv_ratio close to 1)
    """
    edge = beat_implied_pct - max(0.0, (iv_hv_ratio - 1.0) * 0.5)
    direction = float(np.clip((edge - 0.1) * 3, -1, 1))
    confidence = float(min(abs(edge) * 2, 1.0))

    if edge > 0.2:
        detail = (f"Good premium buy: beats implied {beat_implied_pct:.0%} of time, "
                  f"IV/HV={iv_hv_ratio:.2f}x")
    elif edge > 0:
        detail = (f"Marginal buy: beats implied {beat_implied_pct:.0%}, "
                  f"IV/HV={iv_hv_ratio:.2f}x — consider spread")
    else:
        detail = (f"Poor premium buy: only beats implied {beat_implied_pct:.0%}, "
                  f"IV/HV={iv_hv_ratio:.2f}x — IV crush likely")

    return Signal("premium_value", direction, confidence, detail)


def score_price_drift(closes: list[float], days: int = 20) -> Signal:
    """
    Stock that ran up hard into earnings = priced for perfection = bearish lean.
    Stock that sold off = low expectations = bullish lean.
    """
    window = closes[-days:] if len(closes) >= days else closes
    if len(window) < 5:
        return Signal("price_drift", 0.0, 0.0, "Insufficient price history")

    drift = (window[-1] - window[0]) / window[0]
    # tanh squashes extreme moves; flip sign so run-up = bearish
    direction = float(-np.tanh(drift * 8))
    confidence = float(min(abs(drift) / 0.08, 1.0))

    drift_str = f"+{drift:.1%}" if drift > 0 else f"{drift:.1%}"
    if drift > 0.05:
        label = "priced for perfection → bearish lean"
    elif drift < -0.05:
        label = "sold off into print → bullish lean"
    else:
        label = "neutral drift"

    return Signal("price_drift", direction, confidence,
                   f"{drift_str} over {len(window)}d — {label}")


def aggregate_signals(signals: list[Signal]) -> tuple[float, float]:
    """Weighted average direction and mean confidence."""
    total_weight = sum(s.confidence for s in signals)
    if total_weight == 0:
        return 0.0, 0.0
    direction = sum(s.direction * s.confidence for s in signals) / total_weight
    confidence = sum(s.confidence for s in signals) / len(signals)
    return float(direction), float(confidence)
