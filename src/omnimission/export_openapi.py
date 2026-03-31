"""Write the FastAPI OpenAPI schema to ``openapi/openapi.json`` (repo root)."""

from __future__ import annotations

import json
from pathlib import Path


def main() -> None:
    from omnimission.api.main import app

    root = Path(__file__).resolve().parents[2]
    out = root / "openapi" / "openapi.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    schema = app.openapi()
    out.write_text(json.dumps(schema, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()
