"""Write the OpenAPI document the frontend contract is generated from.

    python -m app.openapi_export ../web/openapi.json          # regenerate
    python -m app.openapi_export ../web/openapi.json --check  # CI: fail when the committed file is stale
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from .main import app


def render() -> str:
    return json.dumps(app.openapi(), ensure_ascii=False, indent=1, sort_keys=True) + "\n"


def main() -> None:
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "../web/openapi.json")
    text = render()
    if "--check" in sys.argv:
        if not out.exists() or out.read_text(encoding="utf-8") != text:
            raise SystemExit(f"{out} is out of date — run `python -m app.openapi_export {out}` and commit it")
        print(f"{out} up to date ({len(json.loads(text)['paths'])} paths)")
        return
    out.write_text(text, encoding="utf-8")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
