from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
from statistics import median
from typing import Any

from option_mispricing_engine.config import Settings
from option_mispricing_engine.data_fetcher import InstrumentRef, KiteDataFetcher
from option_mispricing_engine.iv_solver import implied_volatility
from option_mispricing_engine.pricing_model import black_scholes_futures_call_put
from option_mispricing_engine.signal_engine import SignalDecision, SignalEngine
from option_mispricing_engine.storage import DuckDBStorage, SignalRecord
from option_mispricing_engine.telegram_alert import TelegramAlerter

IST = timezone(timedelta(hours=5, minutes=30))


@dataclass
class OptionSnapshot:
    ltp: float
    oi: int
    iv: float | None


class OptionMispricingScanner:
    def __init__(self, settings: Settings, storage: DuckDBStorage | None = None) -> None:
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
        self.storage = storage or DuckDBStorage(settings.duckdb_path)
        self.prev_options: dict[str, OptionSnapshot] = {}
        self.prev_futures: dict[str, float] = {}
        self.last_alert_at: dict[str, datetime] = {}
        self.sem = asyncio.Semaphore(settings.symbol_concurrency)

    async def run_forever(self) -> None:
        while True:
            try:
                signals = await self.scan_once()
                self._print_signals(signals)
                for row in signals:
                    if self._should_alert(row):
                        await self.alerts.send(self._format_telegram(row))
            except Exception:
                logging.exception("Scan cycle failed")
            await asyncio.sleep(self.settings.scan_interval_seconds)

    async def scan_once(self) -> list[dict[str, Any]]:
        universe = await self.fetcher.get_fo_universe(max_symbols=self.settings.max_symbols)
        symbols = list(universe.items())
        tasks = [self._scan_symbol_limited(symbol, details["future"]) for symbol, details in symbols]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        signals: list[dict[str, Any]] = []
        for (symbol, _), res in zip(symbols, results):
            if isinstance(res, Exception):
                logging.error("Failed symbol=%s err=%s", symbol, res)
                continue
            signals.extend(res)

        signals.sort(key=lambda row: row["score"], reverse=True)
        return signals

    async def _scan_symbol_limited(self, symbol: str, fut_meta: dict[str, Any]) -> list[dict[str, Any]]:
        async with self.sem:
            return await self._scan_symbol(symbol, fut_meta)

    async def _scan_symbol(self, symbol: str, fut_meta: dict[str, Any]) -> list[dict[str, Any]]:
        fut_key = f"NFO:{fut_meta['tradingsymbol']}"
        fut_quote = await self.fetcher.quote([fut_key])
        fut_ltp = float(fut_quote[fut_key]["last_price"])

        prev_fut = self.prev_futures.get(symbol, fut_ltp)
        fut_change_pct = ((fut_ltp - prev_fut) / prev_fut * 100.0) if prev_fut else 0.0
        self.prev_futures[symbol] = fut_ltp

        expiries = await self.fetcher.get_option_expiries(symbol)
        if not expiries:
            return []
        scan_expiries = expiries[: self.settings.scan_expiries_per_symbol]
        contracts = await self.fetcher.get_symbol_option_contracts(symbol, expiries=scan_expiries)
        if not contracts:
            return []

        all_quotes = await self.fetcher.quote([c.quote_key for c in contracts])
        shortlisted = self._select_contracts(contracts, all_quotes, fut_ltp)
        if not shortlisted:
            return []

        iv_map = self._compute_current_iv_map(shortlisted, all_quotes, fut_ltp)
        atm_ref_iv = self._atm_reference_iv(shortlisted, fut_ltp, iv_map)

        now = datetime.now(timezone.utc)
        symbol_signals: list[dict[str, Any]] = []

        for contract in shortlisted:
            payload = all_quotes.get(contract.quote_key)
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
            if best_bid is not None and best_ask is not None and ltp > 0:
                spread_pct = ((best_ask - best_bid) / ltp) * 100.0

            tte = self._time_to_expiry_years(contract.expiry, now)
            curr_iv = iv_map.get(contract.quote_key)
            if curr_iv is None:
                continue

            prev = self.prev_options.get(contract.quote_key)
            pricing_iv = prev.iv if prev and prev.iv else atm_ref_iv
            if pricing_iv is None:
                pricing_iv = curr_iv

            call_fair, put_fair = black_scholes_futures_call_put(
                futures_price=fut_ltp,
                strike=contract.strike,
                time_to_expiry=tte,
                risk_free_rate=self.settings.risk_free_rate,
                volatility=pricing_iv,
            )
            fair = call_fair if contract.instrument_type == "CE" else put_fair
            if fair <= 0:
                continue

            ineff = (ltp - fair) / fair
            option_change_pct = ((ltp - prev.ltp) / prev.ltp * 100.0) if prev and prev.ltp > 0 else 0.0
            oi_change = oi - prev.oi if prev else 0
            prev_iv = prev.iv if prev and prev.iv else curr_iv
            iv_spike_pct = ((curr_iv - prev_iv) / prev_iv * 100.0) if prev_iv > 0 else 0.0
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

            self.prev_options[contract.quote_key] = OptionSnapshot(ltp=ltp, oi=oi, iv=curr_iv)
            self.storage.insert_snapshot(
                tradingsymbol=contract.tradingsymbol,
                symbol=symbol,
                strike=contract.strike,
                option_type=contract.instrument_type,
                ltp=ltp,
                iv=curr_iv,
                oi=oi,
                volume=volume,
                fut_ltp=fut_ltp,
                fut_change_pct=fut_change_pct,
            )

            if not decision:
                continue

            row = {
                "symbol": symbol,
                "strike": contract.strike,
                "type": contract.instrument_type,
                "fair": fair,
                "ltp": ltp,
                "score": decision.score,
                "action": self._action_label(decision, contract.instrument_type),
                "priority": decision.priority,
                "inefficiency": decision.inefficiency_score * 100,
                "expiry": contract.expiry.isoformat() if contract.expiry else "",
            }
            symbol_signals.append(row)

            self.storage.insert_signal(
                SignalRecord(
                    ts=datetime.now(timezone.utc),
                    symbol=row["symbol"],
                    strike=row["strike"],
                    option_type=row["type"],
                    fair=row["fair"],
                    ltp=row["ltp"],
                    score=row["score"],
                    action=row["action"],
                    priority=row["priority"],
                    inefficiency_pct=row["inefficiency"],
                    expiry=row["expiry"],
                )
            )

            if self.settings.debug_mode:
                logging.info(
                    "DEBUG %s %s %s fair=%.2f ltp=%.2f iv(cur/pricing)=%.4f/%.4f ineff=%.2f%%",
                    symbol,
                    contract.strike,
                    contract.instrument_type,
                    fair,
                    ltp,
                    curr_iv,
                    pricing_iv,
                    ineff * 100,
                )

        return symbol_signals

    def _compute_current_iv_map(
        self,
        contracts: list[InstrumentRef],
        quotes: dict[str, Any],
        fut_ltp: float,
    ) -> dict[str, float]:
        now = datetime.now(timezone.utc)
        ivs: dict[str, float] = {}
        for c in contracts:
            q = quotes.get(c.quote_key)
            if not q:
                continue
            ltp = float(q.get("last_price") or 0)
            if ltp <= 0:
                continue
            tte = self._time_to_expiry_years(c.expiry, now)
            iv = implied_volatility(
                market_price=ltp,
                futures_price=fut_ltp,
                strike=c.strike,
                time_to_expiry=tte,
                risk_free_rate=self.settings.risk_free_rate,
                option_type=c.instrument_type,
            )
            if iv is not None:
                ivs[c.quote_key] = iv
        return ivs

    @staticmethod
    def _atm_reference_iv(contracts: list[InstrumentRef], fut_ltp: float, iv_map: dict[str, float]) -> float | None:
        iv_values: list[float] = []
        nearest = sorted(contracts, key=lambda c: abs(c.strike - fut_ltp))[:6]
        for c in nearest:
            iv = iv_map.get(c.quote_key)
            if iv is not None:
                iv_values.append(iv)
        return median(iv_values) if iv_values else None

    @staticmethod
    def _select_contracts(
        contracts: list[InstrumentRef],
        quotes: dict[str, Any],
        fut_ltp: float,
    ) -> list[InstrumentRef]:
        if not contracts:
            return []

        strikes = sorted({c.strike for c in contracts})
        atm_idx = min(range(len(strikes)), key=lambda i: abs(strikes[i] - fut_ltp))
        low = max(0, atm_idx - 5)
        high = min(len(strikes), atm_idx + 6)
        atm_strikes = set(strikes[low:high])

        contracts_with_data = [c for c in contracts if c.quote_key in quotes]
        top_oi = sorted(
            contracts_with_data,
            key=lambda c: float((quotes[c.quote_key].get("oi") or 0)),
            reverse=True,
        )[:12]
        top_vol = sorted(
            contracts_with_data,
            key=lambda c: float((quotes[c.quote_key].get("volume") or 0)),
            reverse=True,
        )[:12]

        selected_keys = {c.quote_key for c in contracts if c.strike in atm_strikes}
        selected_keys.update(c.quote_key for c in top_oi)
        selected_keys.update(c.quote_key for c in top_vol)
        return [c for c in contracts if c.quote_key in selected_keys]

    @staticmethod
    def _time_to_expiry_years(expiry_date, now_utc: datetime) -> float:
        expiry_dt_ist = datetime.combine(expiry_date, time(15, 30), tzinfo=IST)
        expiry_dt_utc = expiry_dt_ist.astimezone(timezone.utc)
        delta_seconds = max((expiry_dt_utc - now_utc).total_seconds(), 60)
        return delta_seconds / (365.0 * 24 * 3600)

    def _should_alert(self, row: dict[str, Any]) -> bool:
        key = f"{row['symbol']}:{row['strike']}:{row['type']}:{row['action']}"
        now = datetime.now(timezone.utc)
        prev = self.last_alert_at.get(key)
        if prev and (now - prev).total_seconds() < self.settings.alert_cooldown_seconds:
            return False
        self.last_alert_at[key] = now
        return True

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
            f"Expiry: {row['expiry']}\n"
            f"Fair Value: {row['fair']:.2f}\n"
            f"Market Price: {row['ltp']:.2f}\n"
            f"Inefficiency: {row['inefficiency']:+.2f}%\n"
            f"Signal: {row['action']}\n"
            f"Priority: {row['priority']}"
        )

    @staticmethod
    def _print_signals(rows: list[dict[str, Any]]) -> None:
        print("\nSYMBOL | STRIKE | TYPE | EXPIRY | FAIR | LTP | SCORE | ACTION | PRIORITY")
        print("-" * 96)
        for row in rows[:30]:
            print(
                f"{row['symbol']:<10}| {int(row['strike']):>6} | {row['type']:<4}| "
                f"{row['expiry']:<10} | {row['fair']:>7.2f} | {row['ltp']:>7.2f} | "
                f"{row['score']:>5.1f} | {row['action']:<10}| {row['priority']}"
            )
