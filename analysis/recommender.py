from __future__ import annotations
from dataclasses import dataclass, field
from datetime import date
from typing import List, TYPE_CHECKING

from analysis.scorer import Signal
from config import MAX_RISK_PCT, PORTFOLIO_SIZE, MAX_TRADE_VALUE

if TYPE_CHECKING:
    from analysis.claude_analyzer import ClaudeAnalysis


@dataclass
class Recommendation:
    ticker: str
    earnings_date: date
    # buy_call | buy_put | call_spread | put_spread | go_long | go_short | skip
    action: str
    direction: str       # bullish | bearish | neutral
    confidence: float    # 0–1
    strike: float        # 0 for equity plays
    expiry: str          # '' for equity plays
    cost_per_contract: float   # dollars (per share for equity plays)
    contracts: int             # shares for equity plays
    max_risk: float            # dollars
    expected_move_pct: float
    iv_hv_ratio: float
    thesis: str
    key_factors: List[str] = field(default_factory=list)
    signals: List[Signal] = field(default_factory=list)


def build_from_claude(
    ticker: str,
    earnings_date: date,
    expiry: str,
    spot: float,
    options: dict,
    iv_hv_ratio: float,
    claude_analysis: ClaudeAnalysis,
    signals: List[Signal],
) -> Recommendation:
    action = claude_analysis.action
    direction = claude_analysis.direction
    confidence = claude_analysis.confidence
    thesis = claude_analysis.thesis
    has_opts = bool(options)

    strike = options.get("atm_strike", spot) if has_opts else 0.0
    expected_move = options.get("expected_move_pct", 0.0)

    if action == "buy_call":
        cost = options.get("call_price", 0.0) * 100 if has_opts else 0.0
    elif action == "buy_put":
        cost = options.get("put_price", 0.0) * 100 if has_opts else 0.0
    elif action in ("call_spread", "put_spread"):
        leg = "call_price" if action == "call_spread" else "put_price"
        cost = options.get(leg, 0.0) * 100 * 0.5 if has_opts else 0.0
    elif action in ("go_long", "go_short"):
        cost = spot
        strike = 0.0
        expiry = ""
    else:  # skip
        cost = 0.0

    target = PORTFOLIO_SIZE * MAX_RISK_PCT
    if cost > 0 and action != "skip":
        contracts = max(1, int(target / cost))
        # Hard cap: total position value must stay under MAX_TRADE_VALUE
        if cost * contracts > MAX_TRADE_VALUE:
            contracts = max(1, int(MAX_TRADE_VALUE / cost))
        actual_risk = cost * contracts
    else:
        contracts = 0
        actual_risk = 0.0

    return Recommendation(
        ticker=ticker,
        earnings_date=earnings_date,
        action=action,
        direction=direction,
        confidence=confidence,
        strike=strike,
        expiry=expiry,
        cost_per_contract=cost,
        contracts=contracts,
        max_risk=actual_risk,
        expected_move_pct=expected_move,
        iv_hv_ratio=iv_hv_ratio,
        thesis=thesis,
        key_factors=claude_analysis.key_factors,
        signals=signals,
    )
