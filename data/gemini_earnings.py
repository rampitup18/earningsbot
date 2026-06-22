from __future__ import annotations
import json
import re
import time
from datetime import date, datetime, timedelta

from utils import retry_with_backoff


def _parse_earnings_json(text: str, today: date, end: date) -> list[tuple[str, date]]:
    """Parse a JSON dict of {date: [tickers]} into sorted (ticker, date) tuples."""
    text = re.sub(r"^```(?:json)?\s*\n?", "", text, flags=re.MULTILINE)
    text = re.sub(r"\n?```\s*$", "", text, flags=re.MULTILINE)
    text = text.strip()

    match = re.search(r"\{[\s\S]*\}", text)
    if match:
        text = match.group()

    day_map: dict[str, list[str]] = json.loads(text)
    results: list[tuple[str, date]] = []

    for date_str, tickers in day_map.items():
        try:
            d = datetime.strptime(date_str, "%Y-%m-%d").date()
            if today <= d <= end and d.weekday() < 5:
                for ticker in tickers:
                    t = str(ticker).strip().upper()
                    if t and t.isalpha() and len(t) <= 5:
                        results.append((t, d))
        except ValueError:
            continue

    return sorted(results, key=lambda x: x[1])


def get_earnings_week_from_gemini(days_ahead: int = 7) -> list[tuple[str, date]]:
    """Discover upcoming earnings via Gemini 2.0 Flash + Google Search grounding."""
    from config import GEMINI_API_KEY as api_key
    if not api_key:
        print("  [gemini] GEMINI_API_KEY not set — skipping")
        return []

    try:
        from google import genai
        from google.genai.types import Tool, GenerateContentConfig, GoogleSearch
    except ImportError:
        print("  [gemini] google-genai not installed")
        return []

    client = genai.Client(api_key=api_key)
    today = datetime.now().date()
    end = today + timedelta(days=days_ahead)

    prompt = (
        f"Search for US publicly traded companies scheduled to report quarterly earnings "
        f"between {today.strftime('%B %d, %Y')} and {end.strftime('%B %d, %Y')}. "
        "Focus on large-cap and mid-cap stocks listed on NYSE or NASDAQ with active options. "
        "Find at least 10 companies per trading day. "
        "Return ONLY valid JSON — no explanations, no markdown, no code fences. "
        'Format exactly: {"YYYY-MM-DD": ["TICK1", "TICK2", ...], ...} '
        "Use US ticker symbols only (e.g. AAPL, NVDA, MSFT). "
        "Include at least 10 tickers for each trading day in the date range."
    )

    try:
        response = retry_with_backoff(
            lambda: client.models.generate_content(
                model="gemini-2.0-flash",
                contents=prompt,
                config=GenerateContentConfig(
                    tools=[Tool(google_search=GoogleSearch())],
                    response_modalities=["TEXT"],
                ),
            ),
            label="gemini",
        )

        text = (response.text or "").strip()
        if not text:
            print("  [gemini] Empty response")
            return []

        results = _parse_earnings_json(text, today, end)
        n_days = len({d for _, d in results})
        print(f"  [gemini] Discovered {len(results)} tickers across {n_days} trading days")
        return results

    except Exception as exc:
        print(f"  [gemini] Error: {exc}")
        return []


def get_earnings_week_from_claude(days_ahead: int = 7) -> list[tuple[str, date]]:
    """Fallback: ask Claude Haiku for likely upcoming earnings reporters."""
    from config import ANTHROPIC_API_KEY
    if not ANTHROPIC_API_KEY:
        print("  [claude-discovery] ANTHROPIC_API_KEY not set — skipping")
        return []

    try:
        import anthropic
    except ImportError:
        print("  [claude-discovery] anthropic not installed")
        return []

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    today = datetime.now().date()
    end = today + timedelta(days=days_ahead)

    prompt = (
        f"Today is {today.strftime('%B %d, %Y')}. "
        f"List US publicly traded companies (NYSE/NASDAQ) that typically report quarterly earnings "
        f"between {today.strftime('%B %d, %Y')} and {end.strftime('%B %d, %Y')}. "
        "Base this on their historical earnings reporting patterns and typical Q2 earnings season timing. "
        "Focus on large-cap and mid-cap companies with active options markets. "
        "List at least 10 companies per trading day. "
        "Return ONLY valid JSON, no explanations: "
        '{"YYYY-MM-DD": ["TICK1", "TICK2", ...], ...}'
    )

    try:
        response = retry_with_backoff(
            lambda: client.messages.create(
                model="claude-haiku-4-5",
                max_tokens=1024,
                system="You are a financial data assistant. Return only valid JSON, no markdown.",
                messages=[{"role": "user", "content": prompt}],
            ),
            label="claude-discovery",
        )

        text = response.content[0].text.strip()
        results = _parse_earnings_json(text, today, end)
        n_days = len({d for _, d in results})
        print(f"  [claude-discovery] Found {len(results)} likely tickers across {n_days} days")
        return results

    except Exception as exc:
        print(f"  [claude-discovery] Error: {exc}")
        return []


def rank_tickers(ticker_data: list[dict], top_n: int = 3) -> set[str]:
    """
    Batch-rank tickers by volatility and profit potential using one Gemini call.
    Returns the top_n tickers that should get Opus-level analysis.
    """
    from config import GEMINI_API_KEY
    if not GEMINI_API_KEY or not ticker_data:
        return set()

    try:
        from google import genai
        from google.genai.types import GenerateContentConfig
    except ImportError:
        return set()

    client = genai.Client(api_key=GEMINI_API_KEY)

    lines = []
    for d in ticker_data:
        opts = d.get("opts", {})
        closes = d.get("closes", [])
        hv30 = d.get("hv30", 0)
        has_opts = bool(opts)
        iv_hv = opts.get("atm_iv", 0) / hv30 if hv30 > 0 and has_opts else 0
        drift = (closes[-1] - closes[0]) / closes[0] if len(closes) >= 2 else 0.0
        hist = d.get("hist_summary", {})

        line = f"{d['ticker']}: spot=${d['spot']:.0f}, drift={drift:+.1%}"
        if has_opts:
            line += (f", IV/HV={iv_hv:.1f}x"
                     f", expected_move=±{opts.get('expected_move_pct', 0):.1%}"
                     f", iv_skew={opts.get('iv_skew', 0):+.1%}")
        line += (f", avg_move={hist.get('avg_abs_move', 0):.1%}"
                 f", up={hist.get('up_pct', 0):.0%}"
                 f", beat_implied={hist.get('beat_implied_pct', 0):.0%}")
        lines.append(line)

    prompt = (
        "Here are stocks reporting earnings this week with their market data:\n\n"
        + "\n".join(lines)
        + f"\n\nPick the {top_n} tickers with the highest volatility, widest expected moves, "
        "strongest directional signals, or most mispriced options — the ones most likely "
        "to produce a significant profit or loss.\n"
        f'Return ONLY valid JSON: {{"high_priority": ["TICK1", "TICK2", "TICK3"]}}'
    )

    try:
        response = retry_with_backoff(
            lambda: client.models.generate_content(
                model="gemini-2.0-flash",
                contents=prompt,
                config=GenerateContentConfig(response_modalities=["TEXT"]),
            ),
            label="gemini-rank",
        )

        text = (response.text or "").strip()
        text = re.sub(r"^```(?:json)?\s*\n?", "", text, flags=re.MULTILINE)
        text = re.sub(r"\n?```\s*$", "", text, flags=re.MULTILINE)
        match = re.search(r"\{[\s\S]*\}", text.strip())
        if match:
            text = match.group()

        result = json.loads(text)
        top = {str(t).strip().upper() for t in result.get("high_priority", [])}
        print(f"  [gemini-rank] High priority for Opus: {', '.join(sorted(top))}")
        return top

    except Exception as exc:
        print(f"  [gemini-rank] Error: {exc} — all tickers will use Haiku")
        return set()
