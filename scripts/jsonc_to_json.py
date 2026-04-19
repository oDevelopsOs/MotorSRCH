"""Quita líneas de comentario estilo // (solo líneas que empiezan por // tras espacio) y valida JSON."""
from __future__ import annotations

import json
import re
import sys


def strip_line_comments(text: str) -> str:
    lines = []
    for line in text.splitlines():
        if re.match(r"^\s*//", line):
            continue
        lines.append(line)
    return "\n".join(lines)


def main() -> None:
    if len(sys.argv) < 3:
        print("Uso: python jsonc_to_json.py entrada.jsonc salida.json", file=sys.stderr)
        sys.exit(1)
    raw = open(sys.argv[1], encoding="utf-8").read()
    clean = strip_line_comments(raw)
    json.loads(clean)
    open(sys.argv[2], "w", encoding="utf-8").write(clean)
    print("OK", sys.argv[2])


if __name__ == "__main__":
    main()
