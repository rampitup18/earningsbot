from __future__ import annotations
from dataclasses import dataclass
from datetime import date

from pydantic import BaseModel


@dataclass
class ClaudeAnalysis:
    action: str       # buy_call | buy_put | call_spread | put_spread | go_long | go_short | skip
    direction: str    # bullish | bearish | neutral
    confidence: float
    thesis: str
    key_factors: list[str]


class _Output(BaseModel):
    action: str
    direction: str
    confidence: float
    thesis: str
    key_factors: list[str]


def _build_prompt(
    ticker: str,
    earnings_date: date,
    spot: float,
    options: dict,
    hv30: float,
    hist_moves: list[dict],
    hist_summary: dict,
    closes: list[float],
) -> str:
    has_opts = bool(options)
    iv_hv = options.get("atm_iv", 0) / hv30 if hv30 > 0 and has_opts else None
    drift = (closes[-1] - closes[0]) / closes[0] if len(closes) >= 2 else 0.0
    recent = [f"{m.get('date', '?')} {m['move_pct']:+.1%}" for m in hist_moves[:5]]

    lines = [
        f"TICKER: {ticker}  |  EARNINGS: {earnings_date}  |  SPOT: ${spot:.2f}",
        "",
    ]

    if has_opts:
        lines += [
            "OPTIONS (nearest expiry after earnings):",
            f"  ATM strike:     ${options['atm_strike']:.2f}",
            f"  Call price:     ${options['call_price']:.2f}",
            f"  Put price:      ${options['put_price']:.2f}",
            f"  Expected move:  ±{options['expected_move_pct']:.1%}",
            f"  ATM IV:         {options['atm_iv']:.1%}",
            f"  IV skew (P-C):  {options['iv_skew']:+.1%}",
            f"  IV / HV30:      {iv_hv:.2f}x",
            "",
        ]
    else:
        lines += ["OPTIONS: Not available — equity-only plays considered", ""]

    n = hist_summary.get("n", 0)
    lines += [
        f"HISTORICAL EARNINGS MOVES (last {n} events):",
        f"  Avg abs move:   {hist_summary.get('avg_abs_move', 0):.1%}",
        f"  Median abs:     {hist_summary.get('median_abs_move', 0):.1%}",
        f"  % up reactions: {hist_summary.get('up_pct', 0):.0%}",
        f"  Beat implied:   {hist_summary.get('beat_implied_pct', 0):.0%}",
        f"  Recent dates:   {recent}",
        "",
        f"PRICE ACTION: {len(closes)}-day drift {drift:+.1%}  "
        f"(${closes[0]:.2f} → ${closes[-1]:.2f})",
        "",
    ]

    if has_opts:
        actions = (
            "AVAILABLE ACTIONS (pick the single best one):\n"
            "  buy_call    — bullish, IV/HV < 1.4, stock tends to beat implied move\n"
            "  buy_put     — bearish, IV/HV < 1.4, stock tends to beat implied move\n"
            "  call_spread — bullish but IV/HV ≥ 1.4 (reduce premium cost)\n"
            "  put_spread  — bearish but IV/HV ≥ 1.4 (reduce premium cost)\n"
            "  go_long     — very bullish, options overpriced or illiquid\n"
            "  go_short    — very bearish, options overpriced or illiquid\n"
            "  skip        — conflicting signals or no clear edge"
        )
    else:
        actions = (
            "AVAILABLE ACTIONS (no options data — equity only):\n"
            "  go_long  — bullish conviction from historical pattern + price action\n"
            "  go_short — bearish conviction from historical pattern + price action\n"
            "  skip     — conflicting signals or insufficient data"
        )

    lines += [
        actions,
        "",
        "Respond with this JSON and nothing else:",
        '{"action": "...", "direction": "bullish|bearish|neutral",',
        ' "confidence": 0.0-1.0, "thesis": "one sentence",',
        ' "key_factors": ["factor1", "factor2", "factor3"]}',
        "",
        "Confidence: <0.3=weak/skip, 0.3-0.6=moderate, 0.6-0.8=strong, >0.8=very strong",
    ]

    return "\n".join(lines)


def analyze_with_claude(
    ticker: str,
    earnings_date: date,
    spot: float,
    options: dict,
    hv30: float,
    hist_moves: list[dict],
    hist_summary: dict,
    closes: list[float],
) -> ClaudeAnalysis | None:
    """
    Ask Claude to analyze a pre-earnings setup and recommend a trade.
    Returns None if the API key is missing or the call fails.
    """
    from config import ANTHROPIC_API_KEY, CLAUDE_ANALYZER_MODEL as model
    api_key = ANTHROPIC_API_KEY
    if not api_key:
        return None

    try:
        import anthropic
    except ImportError:
        print("    ! anthropic not installed — run: pip install anthropic")
        return None
    client = anthropic.Anthropic(api_key=api_key)
    prompt = _build_prompt(
        ticker, earnings_date, spot, options, hv30, hist_moves, hist_summary, closes
    )

    from utils import retry_with_backoff

    try:
        response = retry_with_backoff(
            lambda: client.messages.parse(
                model=model,
                max_tokens=512,
                system=(
                    "Analyze the provided pre-earnings market data. "
                    "Recommend a single trade action based strictly on the numbers. "
                    "Respond with valid JSON only — no markdown."
                ),
                messages=[{"role": "user", "content": prompt}],
                output_format=_Output,
            ),
            label="claude-analysis",
        )
        out = response.parsed_output
        return ClaudeAnalysis(
            action=out.action,
            direction=out.direction,
            confidence=float(out.confidence),
            thesis=out.thesis,
            key_factors=out.key_factors,
        )
    except Exception as exc:
        print(f"    ! Claude error: {exc}")
        return None
