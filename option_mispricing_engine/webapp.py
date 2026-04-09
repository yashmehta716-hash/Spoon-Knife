from __future__ import annotations

import asyncio
import contextlib

from fastapi import FastAPI
from fastapi.responses import HTMLResponse

from option_mispricing_engine.config import Settings
from option_mispricing_engine.scanner import OptionMispricingScanner
from option_mispricing_engine.storage import DuckDBStorage


def create_app(settings: Settings) -> FastAPI:
    storage = DuckDBStorage(settings.duckdb_path)
    scanner = OptionMispricingScanner(settings=settings, storage=storage)
    app = FastAPI(title="Option Mispricing Engine")

    @app.on_event("startup")
    async def startup() -> None:
        app.state.scanner_task = asyncio.create_task(scanner.run_forever())

    @app.on_event("shutdown")
    async def shutdown() -> None:
        task = app.state.scanner_task
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

    @app.get("/", response_class=HTMLResponse)
    async def home() -> str:
        return """
<!DOCTYPE html>
<html>
<head>
  <title>Option Mispricing Engine</title>
  <script src="https://unpkg.com/htmx.org@1.9.12"></script>
  <style>
    body {font-family: Arial, sans-serif; margin: 20px;}
    table {border-collapse: collapse; width: 100%;}
    th, td {border: 1px solid #ddd; padding: 8px; font-size: 13px;}
    th {background: #f5f5f5;}
  </style>
</head>
<body>
  <h2>Option Mispricing Engine (DuckDB-backed)</h2>
  <div hx-get="/signals" hx-trigger="load, every 3s" hx-target="#signals" hx-swap="innerHTML"></div>
  <table>
    <thead>
      <tr>
        <th>Time (UTC)</th><th>Symbol</th><th>Strike</th><th>Type</th><th>Expiry</th>
        <th>Fair</th><th>LTP</th><th>Ineff%</th><th>Score</th><th>Action</th><th>Priority</th>
      </tr>
    </thead>
    <tbody id="signals"></tbody>
  </table>
</body>
</html>
        """

    @app.get("/signals", response_class=HTMLResponse)
    async def signals() -> str:
        rows = storage.latest_signals(limit=100)
        html_rows = []
        for r in rows:
            ts = r["ts"].strftime("%Y-%m-%d %H:%M:%S") if r["ts"] else ""
            html_rows.append(
                "<tr>"
                f"<td>{ts}</td>"
                f"<td>{r['symbol']}</td>"
                f"<td>{int(r['strike'])}</td>"
                f"<td>{r['option_type']}</td>"
                f"<td>{r['expiry']}</td>"
                f"<td>{r['fair']:.2f}</td>"
                f"<td>{r['ltp']:.2f}</td>"
                f"<td>{r['inefficiency_pct']:+.2f}%</td>"
                f"<td>{r['score']:.2f}</td>"
                f"<td>{r['action']}</td>"
                f"<td>{r['priority']}</td>"
                "</tr>"
            )
        return "".join(html_rows)

    @app.get("/health", response_class=HTMLResponse)
    async def health() -> str:
        return "ok"

    return app
