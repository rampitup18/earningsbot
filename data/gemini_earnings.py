from __future__ import annotations
import json
import os
import re
from datetime import date, datetime, timedelta


def get_earnings_week_from_gemini(days_ahead: int = 7) -> list[tuple[str, date]]:
    """
    Use Gemini 2.0 Flash with Google Search grounding to discover upcoming earnings.
    Returns (ticker, earnings_date) tuples sorted by date.
    Falls back gracefully if the API key is missing or the call fails.
    """
    from config import GEMINI_API_KEY as api_key
    if not api_key:
        print("  [gemini] GEMINI_API_KEY not set in .env — skipping discovery")
        return []

    try:
        from google import genai
        from google.genai.types import Tool, GenerateContentConfig, GoogleSearch
    except ImportError:
        print("  [gemini] google-genai not installed — run: pip install google-genai")
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
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=prompt,
            config=GenerateContentConfig(
                tools=[Tool(google_search=GoogleSearch())],
                response_modalities=["TEXT"],
            ),
        )

        text = (response.text or "").strip()
        if not text:
            print("  [gemini] Empty response")
            return []

        # Strip markdown fences if present
        text = re.sub(r"^```(?:json)?\s*\n?", "", text, flags=re.MULTILINE)
        text = re.sub(r"\n?```\s*$", "", text, flags=re.MULTILINE)
        text = text.strip()

        # Extract the first JSON object block from the text
        match = re.search(r"\{[\s\S]*\}", text)
        if match:
            text = match.group()

        day_map: dict[str, list[str]] = json.loads(text)
        results: list[tuple[str, date]] = []

        for date_str, tickers in day_map.items():
            try:
                d = datetime.strptime(date_str, "%Y-%m-%d").date()
                if today <= d <= end and d.weekday() < 5:  # weekdays only
                    for ticker in tickers:
                        t = str(ticker).strip().upper()
                        # Basic sanity check: US tickers are 1-5 uppercase letters
                        if t and t.isalpha() and len(t) <= 5:
                            results.append((t, d))
            except ValueError:
                continue

        n_days = len({d for _, d in results})
        print(f"  [gemini] Discovered {len(results)} tickers across {n_days} trading days")
        return sorted(results, key=lambda x: x[1])

    except json.JSONDecodeError as exc:
        print(f"  [gemini] JSON parse error: {exc}")
        return []
    except Exception as exc:
        print(f"  [gemini] Error: {exc}")
        return []
