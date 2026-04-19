"""Fusiona crawler/seeds.json con arrays JSON adicionales de feeds (mismo esquema v2)."""
from __future__ import annotations

import json
import sys


def main() -> None:
    if len(sys.argv) < 2:
        print("Uso: python merge_seed_feeds.py crawler/extra_feeds1.json [extra_feeds2.json ...]", file=sys.stderr)
        sys.exit(1)
    base_path = "crawler/seeds.json"
    with open(base_path, encoding="utf-8") as f:
        base = json.load(f)
    for path in sys.argv[1:]:
        with open(path, encoding="utf-8") as f:
            chunk = json.load(f)
        if isinstance(chunk, list):
            base["feeds"].extend(chunk)
        elif isinstance(chunk, dict) and "feeds" in chunk:
            base["feeds"].extend(chunk["feeds"])
        else:
            raise SystemExit(f"Formato no soportado: {path}")
    with open(base_path, "w", encoding="utf-8") as f:
        json.dump(base, f, ensure_ascii=False, indent=2)
    print("OK", base_path, "feeds:", len(base["feeds"]))


if __name__ == "__main__":
    main()
