from __future__ import annotations

import asyncio
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any

from kiteconnect import KiteConnect


@dataclass(frozen=True)
class InstrumentRef:
    exchange: str
    tradingsymbol: str
    name: str
    instrument_type: str
    strike: float
    expiry: date | None

    @property
    def quote_key(self) -> str:
        return f"{self.exchange}:{self.tradingsymbol}"


class KiteDataFetcher:
    def __init__(self, api_key: str, access_token: str) -> None:
        self.kite = KiteConnect(api_key=api_key)
        self.kite.set_access_token(access_token)
        self._instrument_cache: list[dict[str, Any]] | None = None
        self._instrument_cache_ts: datetime | None = None

    async def load_instruments(self, force: bool = False) -> list[dict[str, Any]]:
        now = datetime.now(timezone.utc)
        if (
            not force
            and self._instrument_cache is not None
            and self._instrument_cache_ts is not None
            and now - self._instrument_cache_ts < timedelta(minutes=20)
        ):
            return self._instrument_cache

        instruments = await asyncio.to_thread(self.kite.instruments, "NFO")
        self._instrument_cache = instruments
        self._instrument_cache_ts = now
        return instruments

    async def get_fo_universe(self, max_symbols: int | None = None) -> dict[str, dict[str, Any]]:
        instruments = await self.load_instruments()
        futures_by_symbol: dict[str, list[dict[str, Any]]] = defaultdict(list)

        for ins in instruments:
            if ins.get("instrument_type") == "FUT":
                futures_by_symbol[ins["name"]].append(ins)

        universe: dict[str, dict[str, Any]] = {}
        for symbol, futures in futures_by_symbol.items():
            nearest = min(futures, key=lambda x: x["expiry"])
            universe[symbol] = {"future": nearest}

        symbols = sorted(universe)
        if max_symbols:
            symbols = symbols[:max_symbols]
        return {sym: universe[sym] for sym in symbols}

    async def get_option_expiries(self, symbol: str) -> list[date]:
        instruments = await self.load_instruments()
        expiries = sorted(
            {
                ins["expiry"]
                for ins in instruments
                if ins.get("name") == symbol and ins.get("instrument_type") in {"CE", "PE"}
            }
        )
        return expiries

    async def get_symbol_option_contracts(self, symbol: str, expiries: list[date] | None = None) -> list[InstrumentRef]:
        instruments = await self.load_instruments()
        contracts: list[InstrumentRef] = []

        if expiries is None:
            all_expiries = await self.get_option_expiries(symbol)
            if not all_expiries:
                return []
            expiries = [all_expiries[0]]

        expiry_set = set(expiries)
        for ins in instruments:
            if (
                ins.get("name") == symbol
                and ins.get("instrument_type") in {"CE", "PE"}
                and ins.get("expiry") in expiry_set
            ):
                contracts.append(
                    InstrumentRef(
                        exchange=ins["exchange"],
                        tradingsymbol=ins["tradingsymbol"],
                        name=ins["name"],
                        instrument_type=ins["instrument_type"],
                        strike=float(ins["strike"]),
                        expiry=ins["expiry"],
                    )
                )
        return contracts

    async def quote(self, quote_keys: list[str]) -> dict[str, Any]:
        all_data: dict[str, Any] = {}
        chunk_size = 200
        for i in range(0, len(quote_keys), chunk_size):
            chunk = quote_keys[i : i + chunk_size]
            if not chunk:
                continue
            response = await asyncio.to_thread(self.kite.quote, chunk)
            all_data.update(response)
        return all_data
