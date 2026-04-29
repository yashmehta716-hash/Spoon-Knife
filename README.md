# Option Mispricing Engine

Production-grade NSE F&O option mispricing scanner using **Kite Connect + Black-Scholes (futures-based)** with **DuckDB persistence** and a **FastAPI + HTMX live dashboard**.

## What is fixed vs initial version

- Fair value volatility is now **independent** from current tick price where possible:
  - pricing IV uses previous snapshot IV (or ATM reference IV fallback),
  - current IV is used for IV-spike diagnostics.
- Option expiry handling is corrected:
  - scanner uses option expiries directly (nearest `SCAN_EXPIRIES_PER_SYMBOL`) instead of forcing futures expiry.
- Added top OI + top volume strike enrichment in scan selection (with ATM ±5 core focus).
- Added DuckDB storage for snapshots/signals.
- Added alert cooldown to avoid Telegram spam.
- Added FastAPI+HTMX dashboard for live monitoring.

## Modules

- `data_fetcher.py` — Kite Connect instruments/quote ingestion.
- `iv_solver.py` — bisection implied-volatility solver.
- `pricing_model.py` — Black-Scholes futures option pricing.
- `signal_engine.py` — all filters and weighted 0–100 mispricing score.
- `scanner.py` — async scan loop + scoring + persistence + alerting.
- `storage.py` — DuckDB schema and read/write APIs.
- `telegram_alert.py` — Telegram bot notifications.
- `webapp.py` — FastAPI + HTMX dashboard.

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env
```

Fill `.env`:

```env
KITE_API_KEY=
KITE_ACCESS_TOKEN=
TELEGRAM_BOT_TOKEN=
CHAT_ID=
SCAN_INTERVAL_SECONDS=3
RISK_FREE_RATE=0.06
MIN_VOLUME=100
MIN_OI=500
MAX_BID_ASK_SPREAD_PCT=1.5
IV_SPIKE_THRESHOLD_PCT=5
MAX_UNDERLYING_MOVE_PCT=0.15
MIN_OPTION_MOVE_PCT=1
ALERT_COOLDOWN_SECONDS=60
DUCKDB_PATH=mispricing.duckdb
SYMBOL_CONCURRENCY=8
SCAN_EXPIRIES_PER_SYMBOL=2
DEBUG_MODE=false
```

## Run

### Terminal scanner

```bash
python run.py
```

### Web dashboard (FastAPI + HTMX)

```bash
python run_web.py
```

Open: `http://localhost:8000`

## Output

### Terminal

`SYMBOL | STRIKE | TYPE | EXPIRY | FAIR | LTP | SCORE | ACTION | PRIORITY`

### Telegram alert

```text
🚨 MISPRICING ALERT
Stock: RELIANCE
Strike: 2500 CE
Expiry: 2026-04-30
Fair Value: 12.00
Market Price: 30.00
Inefficiency: +150.00%
Signal: SELL CALL
Priority: 🟠 High
```

## Notes

- Underlying for valuation is futures LTP, never spot.
- Scanner evaluates nearest option expiries and prioritizes ATM ±5 + high OI/volume contracts.
- DuckDB stores all snapshots/signals for later analytics and dashboard rendering.
