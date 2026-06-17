from __future__ import annotations
import json
import urllib.request
from analysis.recommender import Recommendation
from config import NTFY_TOPIC, NTFY_SERVER, NTFY_TOKEN

ACTION_LABELS = {
    "buy_call":    "BUY CALL",
    "buy_put":     "BUY PUT",
    "call_spread": "CALL DEBIT SPREAD",
    "put_spread":  "PUT DEBIT SPREAD",
    "go_long":     "BUY SHARES (LONG)",
    "go_short":    "SELL SHORT",
    "skip":        "SKIP",
}

DIRECTION_ARROW = {
    "bullish": "^",
    "bearish": "v",
    "neutral": "-",
}

DIRECTION_TAG = {
    "bullish": "chart_with_upwards_trend",
    "bearish": "chart_with_downwards_trend",
    "neutral": "bar_chart",
}

_EQUITY_ACTIONS = {"go_long", "go_short"}


def format_message(rec: Recommendation) -> tuple[str, str]:
    """Return (title, body) for the ntfy notification."""
    arrow = DIRECTION_ARROW.get(rec.direction, "-")
    action = ACTION_LABELS.get(rec.action, rec.action.upper())
    is_equity = rec.action in _EQUITY_ACTIONS

    title = f"[{arrow}] {rec.ticker}  {action}"

    lines = [f"Earnings: {rec.earnings_date}"]

    if is_equity:
        lines.append(f"{rec.contracts} shares @ ${rec.cost_per_contract:.2f}")
    else:
        lines.append(f"Strike ${rec.strike:.0f}  Exp {rec.expiry}")
        lines.append(f"${rec.cost_per_contract:.0f}/contract x{rec.contracts}")

    lines.append(f"Max risk ${rec.max_risk:.0f}")

    if not is_equity and rec.expected_move_pct:
        lines.append(f"Implied move ±{rec.expected_move_pct:.1%}")
    if rec.iv_hv_ratio and not is_equity:
        lines.append(f"IV/HV {rec.iv_hv_ratio:.2f}x")

    lines.append(f"\n{rec.thesis}")

    if rec.key_factors:
        for factor in rec.key_factors:
            lines.append(f"• {factor}")

    return title, "\n".join(lines)


def send_ntfy(title: str, body: str, priority: str = "default") -> bool:
    if not NTFY_TOPIC:
        print("\n[ntfy preview — NTFY_TOPIC not set]")
        print(f"  {title}")
        print(body)
        return False

    url = f"{NTFY_SERVER.rstrip('/')}/{NTFY_TOPIC}"
    payload = json.dumps({
        "title": title,
        "message": body,
        "priority": priority,
    }).encode()

    headers = {"Content-Type": "application/json"}
    if NTFY_TOKEN:
        headers["Authorization"] = f"Bearer {NTFY_TOKEN}"

    try:
        req = urllib.request.Request(url, data=payload, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status == 200
    except Exception as exc:
        print(f"  [ntfy] send failed: {exc}")
        return False


def notify_all(recs: list[Recommendation]) -> None:
    actionable = [r for r in recs if r.action != "skip"]
    if not actionable:
        print("No actionable setups — no notification sent.")
        return

    for rec in actionable:
        title, body = format_message(rec)
        # High priority for strong signals
        priority = "high" if rec.confidence >= 0.6 else "default"
        ok = send_ntfy(title, body, priority=priority)
        status = "sent" if ok else "previewed"
        print(f"  [{rec.ticker}] ntfy {status}: {rec.action.upper()}")
