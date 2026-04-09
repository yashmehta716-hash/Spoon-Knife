from __future__ import annotations

import uvicorn

from option_mispricing_engine.config import load_settings
from option_mispricing_engine.webapp import create_app


def main() -> None:
    settings = load_settings()
    app = create_app(settings)
    uvicorn.run(app, host="0.0.0.0", port=8000)


if __name__ == "__main__":
    main()
