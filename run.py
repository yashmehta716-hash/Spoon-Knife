from __future__ import annotations

import asyncio
import logging

from option_mispricing_engine.config import load_settings
from option_mispricing_engine.scanner import OptionMispricingScanner


def main() -> None:
    settings = load_settings()
    logging.basicConfig(
        level=logging.INFO if settings.debug_mode else logging.WARNING,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    scanner = OptionMispricingScanner(settings)
    asyncio.run(scanner.run_forever())


if __name__ == "__main__":
    main()
