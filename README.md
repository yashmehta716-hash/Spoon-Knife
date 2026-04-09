# Option Mispricing Engine

A production-grade Python scanner for NSE F&O options mispricing detection using **Kite Connect** market data and a **Black-Scholes futures-based fair value model**.

## Features

- Scans NSE F&O stocks plus NIFTY / BANKNIFTY / FINNIFTY.
- Uses **futures LTP (not spot)** as underlying for pricing.
- Computes implied volatility from market option price (bisection IV solver).
- Computes fair call/put values with Black-Scholes (futures form).
- Detects inefficiency:
  - Overpriced: inefficiency > +100% (SELL)
  - Underpriced: inefficiency < -40% (BUY)
- Applies strict filters:
  - Liquidity (Volume/OI thresholds)
  - Bid-ask spread guard
  - Underlying low movement + option movement
  - IV spike confirmation
  - OI build-up confirmation
- Produces weighted mispricing score (0-100).
- Terminal table + optional Telegram alerts.
- Async scan loop (default every 3 seconds).

## Project Structure

```text
option_mispricing_engine/
  config.py
  data_fetcher.py
  iv_solver.py
  pricing_model.py
  scanner.py
  signal_engine.py
  telegram_alert.py
run.py
.env.example
requirements.txt
```

## Setup

1. Install Python 3.11+.
2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Create your `.env` file:

```bash
cp .env.example .env
```

4. Fill values:

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
DEBUG_MODE=false
```

## Run

```bash
python run.py
```

## Notes

- Exchange source is **NFO** instruments.
- Nearest-expiry futures are selected per symbol and used as underlying.
- Scanner focuses on **ATM ± 5 strikes** (both CE and PE) for performance.
- If Telegram credentials are absent, scanner still runs with terminal output only.

## Telegram Alert Example

```text
🚨 MISPRICING ALERT
Stock: RELIANCE
Strike: 2500 CE
Fair Value: 12.00
Market Price: 30.00
Inefficiency: +150.00%
Signal: SELL CALL
Priority: 🟠 High
```
