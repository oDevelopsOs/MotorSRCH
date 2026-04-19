"""Comprueba HTTP(S) de todas las URLs en crawler/seeds.json. Salida por lotes."""
from __future__ import annotations

import json
import os
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SEEDS = ROOT / "crawler" / "seeds.json"
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)
# SEC exige User-Agent identificable (nombre o email); sin esto suele devolver 403.
UA_SEC = "MotorDeBusqueda/1.0 (compliance; contact: compliance@example.com)"
# BLS y algunos .gov responden mejor con UA identificable (uso razonable).
UA_GOV = "MotorDeBusqueda/1.0 (research bot; contact: compliance@example.com)"
TIMEOUT = 28
CHUNK = 30
WORKERS = 8


def load_env_file() -> None:
    """Carga claves desde .env sin sobrescribir variables ya definidas en el proceso."""
    env_path = ROOT / ".env"
    if not env_path.is_file():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = val


def resolve_fred_in_url(raw: str) -> str:
    """Igual que el crawler: inyecta FRED_API_KEY en api.stlouisfed.org con api_key= vacío."""
    k = (os.environ.get("FRED_API_KEY") or "").strip()
    if not k or "api.stlouisfed.org" not in raw:
        return raw
    if "api_key=&" in raw:
        return raw.replace("api_key=&", "api_key=" + urllib.parse.quote(k, safe="") + "&", 1)
    return raw


def load_urls() -> tuple[list[dict], list[dict]]:
    data = json.loads(SEEDS.read_text(encoding="utf-8"))
    feeds = [{"kind": "feed", **x} for x in data.get("feeds", [])]
    urls = [{"kind": "url", **x} for x in data.get("urls", [])]
    return feeds, urls


def _ua_for_url(url: str) -> str:
    u = url.lower()
    if "sec.gov" in u or "data.sec.gov" in u:
        return UA_SEC
    if "bls.gov" in u or "census.gov" in u or "imf.org" in u or "cato.org" in u:
        return UA_GOV
    return UA


def check(url: str) -> tuple[str, int | None, str | None, str | None]:
    """Returns (url, status_or_none, final_url_or_error, snippet)."""
    url = resolve_fred_in_url(url)
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": _ua_for_url(url),
            "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml, text/html, */*;q=0.8",
        },
        method="GET",
    )
    ctx = ssl.create_default_context()
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT, context=ctx) as resp:
            code = resp.getcode()
            final = resp.geturl()
            body = resp.read(4096)
            snippet = (body[:200] or b"").decode("utf-8", "replace").strip()
            return url, code, final, snippet[:120] if snippet else None
    except urllib.error.HTTPError as e:
        return url, e.code, e.headers.get("Location") or getattr(e, "url", None), str(e.reason)
    except urllib.error.URLError as e:
        return url, None, None, str(e.reason)
    except TimeoutError:
        return url, None, None, "timeout"
    except Exception as e:
        return url, None, None, repr(e)


def label(status: int | None, err: str | None) -> str:
    if status is None:
        return f"FAIL ({err or '?'})"
    if 200 <= status < 300:
        return "OK"
    if 300 <= status < 400:
        return f"REDIR/{status}"
    if status == 403:
        return "403"
    if status == 404:
        return "404"
    if status == 429:
        return "429"
    if 400 <= status < 500:
        return f"4xx/{status}"
    if 500 <= status < 600:
        return f"5xx/{status}"
    return str(status)


def main() -> None:
    load_env_file()
    feeds, urls = load_urls()
    items = feeds + urls
    all_u = [x["url"] for x in items]

    print(f"Total URLs: {len(all_u)} (feeds {len(feeds)}, direct urls {len(urls)})")
    print(f"Timeout {TIMEOUT}s, workers {WORKERS}\n")

    results: list[tuple[str, str, str | None, str | None, str]] = []
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futs = {ex.submit(check, u): u for u in all_u}
        for fut in as_completed(futs):
            url, code, final, extra = fut.result()
            lbl = label(code, extra if code is None else None)
            results.append((lbl, url, str(code) if code is not None else "-", final or "", extra or ""))

    # Orden estable: por URL
    results.sort(key=lambda r: r[1])

    bad = [r for r in results if not r[0].startswith("OK") and not r[0].startswith("REDIR")]
    okish = [r for r in results if r[0].startswith("OK") or r[0].startswith("REDIR")]
    print(f"Resumen: OK/redirect ~{len(okish)} | problemas ~{len(bad)}\n")

    for i in range(0, len(results), CHUNK):
        chunk = results[i : i + CHUNK]
        print("=" * 72)
        print(f"Lote {i // CHUNK + 1} (filas {i + 1}-{i + len(chunk)} de {len(results)})")
        print("=" * 72)
        for lbl, url, code, final, extra in chunk:
            line = f"[{lbl:12}] {code:>4} | {url}"
            print(line)
            if final and final != url and lbl.startswith("REDIR"):
                print(f"           -> {final[:100]}")
            code_i: int | None = None
            if code not in (None, "-") and str(code).isdigit():
                code_i = int(code)
            if lbl.startswith("FAIL") or (code_i is not None and code_i >= 400):
                if extra:
                    print(f"           ! {extra[:160]}")
        print()

    if bad:
        print("\n--- Lista compacta de problemas ---")
        for lbl, url, code, final, extra in sorted(bad, key=lambda x: x[1]):
            print(f"{lbl:14} {code:>4} {url}")
    else:
        print("Todas las URLs respondieron OK o con redirección HTTP válida.")


if __name__ == "__main__":
    if not SEEDS.is_file():
        print("No existe", SEEDS, file=sys.stderr)
        sys.exit(1)
    main()
