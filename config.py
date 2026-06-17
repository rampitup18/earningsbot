import os
from dotenv import load_dotenv

load_dotenv()

# ntfy.sh push notifications — install the ntfy app and subscribe to your topic
# Pick a hard-to-guess topic name, e.g. "earningsbot-abc123"
NTFY_TOPIC = os.environ.get("NTFY_TOPIC", "")
NTFY_SERVER = os.environ.get("NTFY_SERVER", "https://ntfy.sh")
NTFY_TOKEN = os.environ.get("NTFY_TOKEN", "")

# Gemini API — discovers upcoming earnings tickers via Google Search grounding
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")

# Anthropic API — analyzes each ticker and recommends put/call/long/short
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
CLAUDE_ANALYZER_MODEL = os.environ.get("CLAUDE_ANALYZER_MODEL", "claude-opus-4-8")

# How many calendar days ahead Gemini should search for earnings
EARNINGS_LOOKAHEAD_DAYS = int(os.environ.get("EARNINGS_LOOKAHEAD_DAYS", 7))

# Sizing: risk this % of portfolio per trade, hard cap at MAX_TRADE_VALUE
MAX_RISK_PCT = float(os.environ.get("MAX_RISK_PCT", 0.01))
PORTFOLIO_SIZE = float(os.environ.get("PORTFOLIO_SIZE", 10000))
MAX_TRADE_VALUE = float(os.environ.get("MAX_TRADE_VALUE", 100_000))

# Minimum confidence to trigger a notification
MIN_ALERT_CONFIDENCE = 0.25

# Scheduler: run daily at this hour (ET)
SCHEDULE_HOUR = 6
SCHEDULE_MINUTE = 30
