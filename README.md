# EarningsBot

Pre-earnings trade scanner that discovers upcoming earnings, analyzes each ticker, and pushes recommendations to your phone.

## How it works

1. **Gemini Flash** searches the web for stocks reporting earnings this week (10+ per day)
2. **Gemini Flash** ranks them by volatility and profit potential
3. **Claude Opus** deep-analyzes the top 3 most volatile tickers
4. **Claude Sonnet** analyzes the rest
5. **ntfy.sh** pushes trade recommendations (buy call, buy put, go long, go short) to your phone

Runs automatically every weekday at 6:30 AM ET via GitHub Actions.

## Setup

### 1. Get API keys

- **Gemini**: [aistudio.google.com](https://aistudio.google.com)
- **Anthropic**: [console.anthropic.com](https://console.anthropic.com)

### 2. Install ntfy

Download the [ntfy app](https://ntfy.sh) and subscribe to a private topic name.

### 3. Configure

```bash
cp .env.example .env
```

Fill in your `.env`:

```
GEMINI_API_KEY=your-gemini-key
ANTHROPIC_API_KEY=your-anthropic-key
NTFY_TOPIC=your-private-topic-name
```

### 4. Install and run

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python main.py --dry-run
```

## Usage

```bash
python main.py                  # full scan + push notifications
python main.py --dry-run        # scan without sending notifications
python main.py --ticker NVDA    # analyze a single ticker
python main.py --schedule       # run on a daily schedule (6:30 AM ET)
```

## GitHub Actions

The bot runs automatically on weekday mornings via `.github/workflows/scan.yml`. Add your API keys as repository secrets:

- `GEMINI_API_KEY`
- `ANTHROPIC_API_KEY`
- `NTFY_TOPIC`

Trigger manually from the Actions tab anytime.

## Configuration

All settings are in `.env` (or GitHub Actions secrets):

| Variable | Default | Description |
|---|---|---|
| `GEMINI_API_KEY` | — | Gemini API key for earnings discovery |
| `ANTHROPIC_API_KEY` | — | Anthropic API key for trade analysis |
| `NTFY_TOPIC` | — | ntfy.sh topic for push notifications |
| `CLAUDE_ANALYZER_MODEL` | `claude-opus-4-8` | Model for top-tier analysis |
| `OPUS_TICKER_COUNT` | `3` | How many tickers get Opus (rest get Sonnet) |
| `PORTFOLIO_SIZE` | `10000` | Portfolio size for position sizing |
| `MAX_RISK_PCT` | `0.01` | Max risk per trade (% of portfolio) |
| `MAX_TRADE_VALUE` | `100000` | Hard cap on position value |
| `EARNINGS_LOOKAHEAD_DAYS` | `7` | How far ahead to scan for earnings |

## Architecture

```
data/
  gemini_earnings.py    Gemini discovery + ranking + Claude fallback
  options.py            Options chains, IV, price history (yfinance)
  historical.py         Past earnings moves

analysis/
  scorer.py             Signal scoring (IV skew, drift, historical)
  claude_analyzer.py    Claude Opus/Sonnet trade analysis
  recommender.py        Position sizing from Claude output

alerts/
  notifier.py           ntfy.sh push notifications
```

## Cost

~$13/year at 10 tickers/day, 5 days/week.

| Layer | Model | Role |
|---|---|---|
| Discovery | Gemini 2.0 Flash | Find earnings tickers via Google Search |
| Ranking | Gemini 2.0 Flash | Pick top 3 most volatile |
| Deep analysis | Claude Opus 4.8 | Analyze top 3 tickers |
| Standard analysis | Claude Sonnet 4.6 | Analyze remaining tickers |
| Fallback discovery | Claude Haiku 4.5 | Backup if Gemini is down |
