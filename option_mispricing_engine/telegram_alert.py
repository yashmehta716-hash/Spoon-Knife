from __future__ import annotations

import asyncio

import requests


class TelegramAlerter:
    def __init__(self, token: str | None, chat_id: str | None) -> None:
        self.token = token
        self.chat_id = chat_id

    @property
    def enabled(self) -> bool:
        return bool(self.token and self.chat_id)

    async def send(self, text: str) -> None:
        if not self.enabled:
            return

        url = f"https://api.telegram.org/bot{self.token}/sendMessage"

        def _post() -> None:
            requests.post(
                url,
                json={"chat_id": self.chat_id, "text": text},
                timeout=10,
            ).raise_for_status()

        await asyncio.to_thread(_post)
