"""Write the API's OpenAPI document. Run `uv run python -m openhal.hub.openapi` after changing a route."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from openhal.hub.api import create_app
from openhal.hub.config import HubConfig
from openhal.hub.hub import Hub

TARGET = Path(__file__).resolve().parents[2] / "docs" / "api" / "openapi.json"


def document() -> str:
    hub = Hub(HubConfig(home=Path("/nonexistent")), in_memory=True)
    try:
        schema = create_app(hub).openapi()
    finally:
        hub.audit.close()
        hub.tokens.close()
    return json.dumps(schema, indent=2, sort_keys=True) + "\n"


def main() -> None:
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else TARGET
    target.write_text(document())
    print(f"Wrote {target}")


if __name__ == "__main__":
    main()
