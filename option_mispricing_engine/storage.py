from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

import duckdb


@dataclass
class SignalRecord:
    ts: datetime
    symbol: str
    strike: float
    option_type: str
    fair: float
    ltp: float
    score: float
    action: str
    priority: str
    inefficiency_pct: float
    expiry: str


class DuckDBStorage:
    def __init__(self, db_path: str) -> None:
        self.conn = duckdb.connect(db_path)
        self._init_schema()

    def _init_schema(self) -> None:
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS signals (
              ts TIMESTAMP,
              symbol VARCHAR,
              strike DOUBLE,
              option_type VARCHAR,
              fair DOUBLE,
              ltp DOUBLE,
              score DOUBLE,
              action VARCHAR,
              priority VARCHAR,
              inefficiency_pct DOUBLE,
              expiry VARCHAR
            )
            """
        )
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS snapshots (
              ts TIMESTAMP,
              tradingsymbol VARCHAR,
              symbol VARCHAR,
              strike DOUBLE,
              option_type VARCHAR,
              ltp DOUBLE,
              iv DOUBLE,
              oi BIGINT,
              volume BIGINT,
              fut_ltp DOUBLE,
              fut_change_pct DOUBLE
            )
            """
        )

    def insert_signal(self, rec: SignalRecord) -> None:
        self.conn.execute(
            """
            INSERT INTO signals VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                rec.ts,
                rec.symbol,
                rec.strike,
                rec.option_type,
                rec.fair,
                rec.ltp,
                rec.score,
                rec.action,
                rec.priority,
                rec.inefficiency_pct,
                rec.expiry,
            ],
        )

    def insert_snapshot(
        self,
        tradingsymbol: str,
        symbol: str,
        strike: float,
        option_type: str,
        ltp: float,
        iv: float,
        oi: int,
        volume: int,
        fut_ltp: float,
        fut_change_pct: float,
    ) -> None:
        self.conn.execute(
            """
            INSERT INTO snapshots VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                datetime.now(timezone.utc),
                tradingsymbol,
                symbol,
                strike,
                option_type,
                ltp,
                iv,
                oi,
                volume,
                fut_ltp,
                fut_change_pct,
            ],
        )

    def latest_signals(self, limit: int = 100) -> list[dict]:
        rows = self.conn.execute(
            """
            SELECT *
            FROM signals
            ORDER BY ts DESC, score DESC
            LIMIT ?
            """,
            [limit],
        ).fetchall()

        cols = [
            "ts",
            "symbol",
            "strike",
            "option_type",
            "fair",
            "ltp",
            "score",
            "action",
            "priority",
            "inefficiency_pct",
            "expiry",
        ]
        return [dict(zip(cols, r)) for r in rows]
