"""Prueba FRED API usando FRED_API_KEY del .env (sin imprimir la clave)."""
from __future__ import annotations

import json
import os
import ssl
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    env_path = ROOT / ".env"
    if env_path.is_file():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("FRED_API_KEY="):
                _, v = line.split("=", 1)
                os.environ.setdefault("FRED_API_KEY", v.strip().strip('"').strip("'"))
                break
    k = os.environ.get("FRED_API_KEY", "").strip()
    if not k:
        raise SystemExit("FRED_API_KEY no definida en entorno ni en .env")
    q = urllib.parse.urlencode({"api_key": k, "file_type": "json", "limit": "2"})
    u = "https://api.stlouisfed.org/fred/releases?" + q
    req = urllib.request.Request(u, headers={"User-Agent": "MotorDeBusqueda/1.0"})
    ctx = ssl.create_default_context()
    with urllib.request.urlopen(req, timeout=25, context=ctx) as r:
        body = r.read()
        data = json.loads(body)
    rel = data.get("releases") or []
    print("OK HTTP", r.status, "| releases en respuesta:", len(rel))
    if rel:
        print("Ejemplo id:", rel[0].get("id"))


if __name__ == "__main__":
    main()
