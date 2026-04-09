from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, time, timezone
from typing import Any

from option_mispricing_engine.config import Settings
from option_mispricing_engine.data_fetcher import InstrumentRef, KiteDataFetcher
from option_mispricing_engine.iv_solver import implied_volatility
from option_mispricing_engine.pricing_model import black_scholes_futures_call_put
from option_mispricing_engine.signal_engine import SignalDecision, SignalEngine
from option_mispricing_engine.telegram_alert import TelegramAlerter


@dataclass
class OptionSnapshot:
    ltp: float
    oi: int
    iv: float | None


class OptionMispricingScanner:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.fetcher = KiteDataFetcher(settings.kite_api_key, settings.kite_access_token)
        self.signal_engine = SignalEngine(
            min_volume=settings.min_volume,
            min_oi=settings.min_oi,
            max_bid_ask_spread_pct=settings.max_bid_ask_spread_pct,
            iv_spike_threshold_pct=settings.iv_spike_threshold_pct,
            max_underlying_move_pct=settings.max_underlying_move_pct,
            min_option_move_pct=settings.min_option_move_pct,
        )
        self.alerts = TelegramAlerter(settings.telegram_bot_token, settings.chat_id)
        self.prev_options: dict[str, OptionSnapshot] = {}
        self.prev_futures: dict[str, float] = {}

    async def run_forever(self) -> None:
        while True:
            try:
                signals = await self.scan_once()
                self._print_signals(signals)
                for line in signals:
                    await self.alerts.send(self._format_telegram(line))
            except Exception:
                logging.exception("Scan cycle failed")
            await asyncio.sleep(self.settings.scan_interval_seconds)

    async def scan_once(self) -> list[dict[str, Any]]:
        universe = await self.fetcher.get_fo_universe(max_symbols=self.settings.max_symbols)
        signals: list[dict[str, Any]] = []

        tasks = [self._scan_symbol(symbol, details["future"]) for symbol, details in universe.items()]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for symbol, res in zip(universe.keys(), results):
            if isinstance(res, Exception):
                logging.error("Failed symbol=%s err=%s", symbol, res)
                continue
            signals.extend(res)

        signals.sort(key=lambda row: row["score"], reverse=True)
        return signals

    async def _scan_symbol(self, symbol: str, fut_meta: dict[str, Any]) -> list[dict[str, Any]]:
        expiry = fut_meta["expiry"]
        fut_key = f"NFO:{fut_meta['tradingsymbol']}"
        fut_quote = await self.fetcher.quote([fut_key])
        fut_ltp = float(fut_quote[fut_key]["last_price"])

        prev_fut = self.prev_futures.get(symbol, fut_ltp)
        fut_change_pct = ((fut_ltp - prev_fut) / prev_fut * 100.0) if prev_fut else 0.0
        self.prev_futures[symbol] = fut_ltp

        contracts = await self.fetcher.get_symbol_option_contracts(symbol, expiry=expiry)
        shortlisted = self._select_contracts(contracts, fut_ltp)
        if not shortlisted:
            return []

        quotes = await self.fetcher.quote([c.quote_key for c in shortlisted])
        now = datetime.now(timezone.utc)
        time_to_expiry = self._time_to_expiry_years(expiry, now)

        symbol_signals: list[dict[str, Any]] = []
        for contract in shortlisted:
            payload = quotes.get(contract.quote_key)
            if not payload:
                continue

            depth = payload.get("depth") or {}
            buy = depth.get("buy") or []
            sell = depth.get("sell") or []
            best_bid = float(buy[0]["price"]) if buy else None
            best_ask = float(sell[0]["price"]) if sell else None

            ltp = float(payload.get("last_price") or 0)
            if ltp <= 0:
                continue
            volume = int(payload.get("volume") or 0)
            oi = int(payload.get("oi") or 0)
            spread_pct = None
            if best_bid and best_ask and ltp > 0:
                spread_pct = ((best_ask - best_bid) / ltp) * 100.0

            prev = self.prev_options.get(contract.quote_key)
            option_change_pct = ((ltp - prev.ltp) / prev.ltp * 100.0) if prev and prev.ltp > 0 else 0.0
            oi_change = (oi - prev.oi) if prev else 0

            iv = implied_volatility(
                market_price=ltp,
                futures_price=fut_ltp,
                strike=contract.strike,
                time_to_expiry=time_to_expiry,
                risk_free_rate=self.settings.risk_free_rate,
                option_type=contract.instrument_type,
            )
            if iv is None:
                continue

            call_fair, put_fair = black_scholes_futures_call_put(
                futures_price=fut_ltp,
                strike=contract.strike,
                time_to_expiry=time_to_expiry,
                risk_free_rate=self.settings.risk_free_rate,
                volatility=iv,
            )
            fair = call_fair if contract.instrument_type == "CE" else put_fair
            if fair <= 0:
                continue

            ineff = (ltp - fair) / fair
            prev_iv = prev.iv if prev else iv
            iv_spike_pct = ((iv - prev_iv) / prev_iv * 100.0) if prev_iv and prev_iv > 0 else 0.0
            trend_strength = min(10.0, max(0.0, abs(option_change_pct) - abs(fut_change_pct) * 2.0))

            decision = self.signal_engine.evaluate(
                inefficiency_score=ineff,
                volume=volume,
                oi=oi,
                spread_pct=spread_pct,
                fut_change_pct=fut_change_pct,
                opt_change_pct=option_change_pct,
                iv_spike_pct=iv_spike_pct,
                oi_change=oi_change,
                trend_strength=trend_strength,
            )

            self.prev_options[contract.quote_key] = OptionSnapshot(ltp=ltp, oi=oi, iv=iv)

            if decision:
                symbol_signals.append(
                    {
                        "symbol": symbol,
                        "strike": contract.strike,
                        "type": contract.instrument_type,
                        "fair": fair,
                        "ltp": ltp,
                        "score": decision.score,
                        "action": self._action_label(decision, contract.instrument_type),
                        "priority": decision.priority,
                        "inefficiency": decision.inefficiency_score * 100,
                    }
                )

            if self.settings.debug_mode:
                logging.info(
                    "DEBUG %s %s %s fair=%.2f ltp=%.2f iv=%.4f ineff=%.2f%%",
                    symbol,
                    contract.strike,
                    contract.instrument_type,
                    fair,
                    ltp,
                    iv,
                    ineff * 100,
                )

        return symbol_signals

    @staticmethod
    def _select_contracts(contracts: list[InstrumentRef], fut_ltp: float) -> list[InstrumentRef]:
        if not contracts:
            return []

        strikes = sorted({c.strike for c in contracts})
        atm_idx = min(range(len(strikes)), key=lambda i: abs(strikes[i] - fut_ltp))
        low = max(0, atm_idx - 5)
        high = min(len(strikes), atm_idx + 6)
        targeted_strikes = set(strikes[low:high])
        return [c for c in contracts if c.strike in targeted_strikes]

    @staticmethod
    def _time_to_expiry_years(expiry_date, now_utc: datetime) -> float:
        expiry_dt = datetime.combine(expiry_date, time(15, 30), tzinfo=timezone.utc)
        delta_seconds = max((expiry_dt - now_utc).total_seconds(), 60)
        return delta_seconds / (365.0 * 24 * 3600)

    @staticmethod
    def _action_label(decision: SignalDecision, opt_type: str) -> str:
        if decision.action == "SELL":
            return "SELL CALL" if opt_type == "CE" else "SELL PUT"
        return "BUY CALL" if opt_type == "CE" else "BUY PUT"

    @staticmethod
    def _format_telegram(row: dict[str, Any]) -> str:
        return (
            "🚨 MISPRICING ALERT\n"
            f"Stock: {row['symbol']}\n"
            f"Strike: {int(row['strike'])} {row['type']}\n"
            f"Fair Value: {row['fair']:.2f}\n"
            f"Market Price: {row['ltp']:.2f}\n"
            f"Inefficiency: {row['inefficiency']:+.2f}%\n"
            f"Signal: {row['action']}\n"
            f"Priority: {row['priority']}"
        )

    @staticmethod
    def _print_signals(rows: list[dict[str, Any]]) -> None:
        print("\nSYMBOL | STRIKE | TYPE | FAIR | LTP | SCORE | ACTION | PRIORITY")
        print("-" * 78)
        for row in rows[:25]:
            print(
                f"{row['symbol']:<10}| {int(row['strike']):>6} | {row['type']:<4}| "
                f"{row['fair']:>7.2f} | {row['ltp']:>7.2f} | {row['score']:>5.1f} | "
                f"{row['action']:<10}| {row['priority']}"
            )
