from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    kite_api_key: str
    kite_access_token: str
    telegram_bot_token: str | None
    chat_id: str | None
    scan_interval_seconds: int = 3
    risk_free_rate: float = 0.06
    min_volume: int = 100
    min_oi: int = 500
    max_bid_ask_spread_pct: float = 1.5
    iv_spike_threshold_pct: float = 5.0
    max_underlying_move_pct: float = 0.15
    min_option_move_pct: float = 1.0
    alert_cooldown_seconds: int = 60
    duckdb_path: str = "mispricing.duckdb"
    debug_mode: bool = False
    max_symbols: int | None = None
    symbol_concurrency: int = 8
    scan_expiries_per_symbol: int = 2


def load_settings() -> Settings:
    load_dotenv()
    api_key = os.getenv("KITE_API_KEY", "").strip()
    access_token = os.getenv("KITE_ACCESS_TOKEN", "").strip()
    if not api_key or not access_token:
        raise ValueError("KITE_API_KEY and KITE_ACCESS_TOKEN are required in .env")

    max_symbols_raw = os.getenv("MAX_SYMBOLS")
    max_symbols = int(max_symbols_raw) if max_symbols_raw else None

    return Settings(
        kite_api_key=api_key,
        kite_access_token=access_token,
        telegram_bot_token=os.getenv("TELEGRAM_BOT_TOKEN", "").strip() or None,
        chat_id=os.getenv("CHAT_ID", "").strip() or None,
        scan_interval_seconds=int(os.getenv("SCAN_INTERVAL_SECONDS", "3")),
        risk_free_rate=float(os.getenv("RISK_FREE_RATE", "0.06")),
        min_volume=int(os.getenv("MIN_VOLUME", "100")),
        min_oi=int(os.getenv("MIN_OI", "500")),
        max_bid_ask_spread_pct=float(os.getenv("MAX_BID_ASK_SPREAD_PCT", "1.5")),
        iv_spike_threshold_pct=float(os.getenv("IV_SPIKE_THRESHOLD_PCT", "5")),
        max_underlying_move_pct=float(os.getenv("MAX_UNDERLYING_MOVE_PCT", "0.15")),
        min_option_move_pct=float(os.getenv("MIN_OPTION_MOVE_PCT", "1.0")),
        alert_cooldown_seconds=int(os.getenv("ALERT_COOLDOWN_SECONDS", "60")),
        duckdb_path=os.getenv("DUCKDB_PATH", "mispricing.duckdb"),
        debug_mode=os.getenv("DEBUG_MODE", "false").lower() == "true",
        max_symbols=max_symbols,
        symbol_concurrency=int(os.getenv("SYMBOL_CONCURRENCY", "8")),
        scan_expiries_per_symbol=int(os.getenv("SCAN_EXPIRIES_PER_SYMBOL", "2")),
    )
