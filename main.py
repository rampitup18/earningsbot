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
import os
import time
from datetime import datetime, date

from config import MIN_ALERT_CONFIDENCE, SCHEDULE_HOUR, SCHEDULE_MINUTE, EARNINGS_LOOKAHEAD_DAYS
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


def analyze(ticker: str, earnings_date: date):
    print(f"\n  {ticker} (earnings {earnings_date})")

    spot = get_spot_price(ticker)
    if not spot:
        print("    ! Could not get spot price")
        return None

    # Options are optional — Claude can still recommend go_long/go_short without them
    expiry = get_nearest_expiry_after(ticker, earnings_date)
    opts: dict = {}
    if expiry:
        opts = get_options_snapshot(ticker, expiry, spot)
        if not opts:
            print("    ~ No options chain available — equity plays only")
    else:
        print("    ~ No options expiry found — equity plays only")

    hv30 = get_historical_vol(ticker)
    iv_hv = opts["atm_iv"] / hv30 if hv30 > 0 and opts else 1.0

    past_moves = get_past_earnings_moves(ticker, n=10)
    hist = summarize_moves(past_moves, opts.get("expected_move_pct", 0.0))
    closes = get_price_history(ticker, days=25)

    # Run traditional signals for display (skip IV signals when no options)
    signals = []
    if opts:
        signals.append(score_iv_skew(opts["put_iv"], opts["call_iv"]))
        signals.append(score_premium_value(hist["beat_implied_pct"], iv_hv))
    signals.append(score_historical_direction(past_moves))
    signals.append(score_price_drift(closes))

    direction_score, confidence = aggregate_signals(signals) if signals else (0.0, 0.0)

    for s in signals:
        marker = ">>" if s.confidence >= 0.3 else "  "
        print(f"    {marker} [{s.name:20s}] dir={s.direction:+.2f} "
              f"conf={s.confidence:.0%}  {s.detail}")

    # Gemini pre-screen: cheap filter before expensive Claude call
    from data.gemini_earnings import prescreen_ticker
    if not prescreen_ticker(ticker, spot, opts, hist, closes, hv30):
        print("    ~ [gemini pre-screen] No clear edge — skipping")
        return None

    # Claude makes the final call on action type
    claude = analyze_with_claude(
        ticker=ticker,
        earnings_date=earnings_date,
        spot=spot,
        options=opts,
        hv30=hv30,
        hist_moves=hist.get("moves", []),
        hist_summary=hist,
        closes=closes,
    )

    if not claude:
        print("    ! Claude unavailable — check ANTHROPIC_API_KEY")
        return None

    from config import CLAUDE_ANALYZER_MODEL
    print(f"    >> [claude/{CLAUDE_ANALYZER_MODEL}] "
          f"action={claude.action} dir={claude.direction} conf={claude.confidence:.0%}")
    for factor in claude.key_factors:
        print(f"       • {factor}")
    rec = build_from_claude(
        ticker=ticker,
        earnings_date=earnings_date,
        expiry=expiry or "",
        spot=spot,
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

    print("\nAnalyzing...")
    recs = []
    for ticker, edate in upcoming:
        rec = analyze(ticker, edate)
        if rec:
            recs.append(rec)
        time.sleep(0.5)

    actionable = [r for r in recs if r.action != "skip" and r.confidence >= MIN_ALERT_CONFIDENCE]
    print(f"\n{'='*60}")
    print(f"Actionable setups: {len(actionable)} / {len(recs)}")

    if dry_run:
        print("(dry-run mode — SMS suppressed)\n")
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
