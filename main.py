#!/usr/bin/env python3
"""
EarningsBot — pre-earnings signal scanner powered by Gemini + Claude.

Usage:
  python main.py                 # discover earnings via Gemini, analyze with Claude
  python main.py --ticker NVDA   # analyze a single ticker
  python main.py --dry-run       # scan but do not send SMS
  python main.py --schedule      # run daily at 6:30 AM ET via APScheduler
"""
from __future__ import annotations
import argparse
import time
from datetime import datetime, date

from config import (
    MIN_ALERT_CONFIDENCE, SCHEDULE_HOUR, SCHEDULE_MINUTE,
    EARNINGS_LOOKAHEAD_DAYS, OPUS_TICKER_COUNT, CLAUDE_ANALYZER_MODEL,
)
from data.options import (
    get_spot_price,
    get_nearest_expiry_after,
    get_options_snapshot,
    get_historical_vol,
    get_price_history,
)
from data.historical import get_past_earnings_moves, summarize_moves
from analysis.scorer import (
    score_iv_skew,
    score_historical_direction,
    score_premium_value,
    score_price_drift,
    aggregate_signals,
)
from analysis.recommender import build_from_claude
from analysis.claude_analyzer import analyze_with_claude
from alerts.notifier import notify_all


def _fetch_ticker_data(ticker: str, earnings_date: date) -> dict | None:
    """Fetch all market data for a ticker. Returns a dict or None."""
    print(f"\n  {ticker} (earnings {earnings_date})")

    spot = get_spot_price(ticker)
    if not spot:
        print("    ! Could not get spot price")
        return None

    expiry = get_nearest_expiry_after(ticker, earnings_date)
    opts: dict = {}
    if expiry:
        opts = get_options_snapshot(ticker, expiry, spot)
        if not opts:
            print("    ~ No options chain — equity plays only")
    else:
        print("    ~ No options expiry — equity plays only")

    hv30 = get_historical_vol(ticker)
    past_moves = get_past_earnings_moves(ticker, n=10)
    hist = summarize_moves(past_moves, opts.get("expected_move_pct", 0.0))
    closes = get_price_history(ticker, days=25)

    return {
        "ticker": ticker,
        "earnings_date": earnings_date,
        "spot": spot,
        "expiry": expiry,
        "opts": opts,
        "hv30": hv30,
        "past_moves": past_moves,
        "hist_summary": hist,
        "closes": closes,
    }


def _analyze_ticker(data: dict, model: str) -> object | None:
    """Run signals + Claude analysis on a pre-fetched data dict."""
    ticker = data["ticker"]
    opts = data["opts"]
    hv30 = data["hv30"]
    hist = data["hist_summary"]
    closes = data["closes"]
    iv_hv = opts["atm_iv"] / hv30 if hv30 > 0 and opts else 1.0

    signals = []
    if opts:
        signals.append(score_iv_skew(opts["put_iv"], opts["call_iv"]))
        signals.append(score_premium_value(hist["beat_implied_pct"], iv_hv))
    signals.append(score_historical_direction(data["past_moves"]))
    signals.append(score_price_drift(closes))

    for s in signals:
        marker = ">>" if s.confidence >= 0.3 else "  "
        print(f"    {marker} [{s.name:20s}] dir={s.direction:+.2f} "
              f"conf={s.confidence:.0%}  {s.detail}")

    claude = analyze_with_claude(
        ticker=ticker,
        earnings_date=data["earnings_date"],
        spot=data["spot"],
        options=opts,
        hv30=hv30,
        hist_moves=hist.get("moves", []),
        hist_summary=hist,
        closes=closes,
        model=model,
    )

    if not claude:
        print("    ! Claude unavailable — check ANTHROPIC_API_KEY")
        return None

    print(f"    >> [claude/{claude.model_used}] "
          f"action={claude.action} dir={claude.direction} conf={claude.confidence:.0%}")
    for factor in claude.key_factors:
        print(f"       • {factor}")

    rec = build_from_claude(
        ticker=ticker,
        earnings_date=data["earnings_date"],
        expiry=data["expiry"] or "",
        spot=data["spot"],
        options=opts,
        iv_hv_ratio=iv_hv,
        claude_analysis=claude,
        signals=signals,
    )

    flag = "**" if rec.action != "skip" else "  "
    print(f"    {flag} RESULT: {rec.action.upper()} | conf={rec.confidence:.0%} | {rec.thesis}")
    return rec


def _discover_earnings() -> list[tuple[str, date]]:
    from data.gemini_earnings import get_earnings_week_from_gemini, get_earnings_week_from_claude

    results = get_earnings_week_from_gemini(days_ahead=EARNINGS_LOOKAHEAD_DAYS)
    if results:
        return results

    print("  Gemini failed — falling back to Claude Haiku for discovery")
    return get_earnings_week_from_claude(days_ahead=EARNINGS_LOOKAHEAD_DAYS)


def run(dry_run: bool = False, single_ticker: str | None = None) -> None:
    print(f"\nEarningsBot  {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 60)

    if single_ticker:
        try:
            import yfinance as yf
            from datetime import timezone
            now = datetime.now(timezone.utc)
            ed = yf.Ticker(single_ticker).earnings_dates
            future = ed[ed.index > now] if ed is not None and not ed.empty else None
            if future is not None and not future.empty:
                next_date = future.index[0].tz_convert("UTC").date()
            else:
                from datetime import timedelta
                next_date = (datetime.now() + timedelta(days=1)).date()
                print(f"  Note: no earnings date found for {single_ticker}, using {next_date}")
        except Exception as exc:
            from datetime import timedelta
            next_date = (datetime.now() + timedelta(days=1)).date()
            print(f"  Note: error fetching earnings date ({exc}), using {next_date}")
        upcoming = [(single_ticker, next_date)]
    else:
        upcoming = _discover_earnings()

    if not upcoming:
        print("No earnings found — check GEMINI_API_KEY and ANTHROPIC_API_KEY in .env")
        return

    print(f"\nFound {len(upcoming)} earnings event(s):")
    for ticker, d in upcoming:
        print(f"  {ticker}: {d}")

    # Phase 1: Fetch market data for all tickers
    print("\nFetching market data...")
    all_data: list[dict] = []
    for ticker, edate in upcoming:
        data = _fetch_ticker_data(ticker, edate)
        if data:
            all_data.append(data)
        time.sleep(0.5)

    if not all_data:
        print("No tickers with valid market data.")
        return

    # Phase 2: Gemini ranks tickers — top N go to Opus, rest to Haiku
    if single_ticker:
        opus_tickers = {single_ticker}
    else:
        from data.gemini_earnings import rank_tickers
        opus_tickers = rank_tickers(all_data, top_n=OPUS_TICKER_COUNT)

    opus_model = CLAUDE_ANALYZER_MODEL
    haiku_model = "claude-haiku-4-5"

    opus_count = sum(1 for d in all_data if d["ticker"] in opus_tickers)
    haiku_count = len(all_data) - opus_count
    print(f"\n  Routing: {opus_count} tickers → {opus_model}, {haiku_count} tickers → {haiku_model}")

    # Phase 3: Analyze — Opus for high-vol, Haiku for the rest
    print("\nAnalyzing...")
    recs = []
    for data in all_data:
        model = opus_model if data["ticker"] in opus_tickers else haiku_model
        print(f"\n  {data['ticker']} → {model}")
        rec = _analyze_ticker(data, model)
        if rec:
            recs.append(rec)
        time.sleep(0.5)

    actionable = [r for r in recs if r.action != "skip" and r.confidence >= MIN_ALERT_CONFIDENCE]
    print(f"\n{'='*60}")
    print(f"Actionable setups: {len(actionable)} / {len(recs)}")

    if dry_run:
        print("(dry-run mode — notifications suppressed)\n")
        from alerts.notifier import format_message
        for r in actionable:
            title, body = format_message(r)
            print(f"--- {title}")
            print(body)
            print()
    else:
        notify_all(recs)


def schedule_daily() -> None:
    from apscheduler.schedulers.blocking import BlockingScheduler

    scheduler = BlockingScheduler(timezone="US/Eastern")
    scheduler.add_job(run, "cron", hour=SCHEDULE_HOUR, minute=SCHEDULE_MINUTE)
    print(f"EarningsBot scheduled — runs daily at {SCHEDULE_HOUR:02d}:{SCHEDULE_MINUTE:02d} ET")
    print("Press Ctrl+C to stop.")
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        print("Scheduler stopped.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="EarningsBot options signal scanner")
    parser.add_argument("--schedule", action="store_true", help="Run on daily schedule")
    parser.add_argument("--dry-run", action="store_true", help="Print alerts without sending SMS")
    parser.add_argument("--ticker", type=str, help="Analyze a single ticker")
    args = parser.parse_args()

    if args.schedule:
        schedule_daily()
    else:
        run(dry_run=args.dry_run, single_ticker=args.ticker)
