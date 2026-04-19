from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from . import settings
from .sources.types import NormalizedHit
from .trust import trust_for_domain, trust_for_source_key


def multi_rrf(ranked_lists: list[list[str]], k: int) -> dict[str, float]:
    scores: dict[str, float] = {}
    for ids in ranked_lists:
        for rank, cid in enumerate(ids):
            if not cid:
                continue
            scores[cid] = scores.get(cid, 0.0) + 1.0 / (k + rank + 1)
    return scores


def _parse_dt(s: str | None) -> datetime | None:
    if not s or not isinstance(s, str):
        return None
    t = s.strip()
    if not t:
        return None
    try:
        if t.endswith("Z"):
            t = t.replace("Z", "+00:00")
        dt = datetime.fromisoformat(t)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        m = re.match(r"^(\d{4}-\d{2}-\d{2})", t)
        if m:
            try:
                return datetime.fromisoformat(m.group(1)).replace(tzinfo=timezone.utc)
            except ValueError:
                return None
    return None


def recency_component(published_at: str | None, needs_fresh: bool) -> float:
    """0..1 higher is fresher."""
    dt = _parse_dt(published_at)
    if dt is None:
        return 0.45 if needs_fresh else 0.75
    now = datetime.now(timezone.utc)
    age_days = max(0.0, (now - dt).total_seconds() / 86400.0)
    if age_days <= 1:
        return 1.0
    if age_days <= 7:
        return 0.95
    if age_days <= 30:
        return 0.85
    if age_days <= 365:
        return 0.65
    return 0.4


def trust_component(hit: dict[str, Any]) -> float:
    dom = str(hit.get("source_domain") or hit.get("domain") or "")
    src = str(hit.get("source") or "")
    if dom:
        return trust_for_domain(dom)
    if src:
        return trust_for_source_key(src)
    return trust_for_domain(dom)


def normalize_scores(scores: dict[str, float]) -> dict[str, float]:
    if not scores:
        return {}
    m = max(scores.values())
    if m <= 0:
        return scores
    return {k: v / m for k, v in scores.items()}


def weighted_fusion_scores(
    rrf_scores: dict[str, float],
    id_to_hit: dict[str, dict[str, Any]],
    *,
    needs_fresh: bool,
) -> dict[str, float]:
    """Blend normalized RRF with trust and recency."""
    n_rrf = normalize_scores(rrf_scores)
    wt = settings.FUSION_TRUST_WEIGHT
    wr = settings.FUSION_RECENCY_WEIGHT
    w_rrf = max(0.0, 1.0 - wt - wr)
    out: dict[str, float] = {}
    for cid, rrf_n in n_rrf.items():
        hit = id_to_hit.get(cid) or {}
        tr = trust_component(hit)
        rc = recency_component(
            str(hit.get("published_at") or "") or None,
            needs_fresh,
        )
        out[cid] = w_rrf * rrf_n + wt * tr + wr * rc
    return out


def build_id_registry(
    meili_hits: list[dict[str, Any]],
    external: list[NormalizedHit],
) -> dict[str, dict[str, Any]]:
    reg: dict[str, dict[str, Any]] = {}
    for h in meili_hits:
        hid = str(h.get("id") or "")
        if hid:
            reg[hid] = dict(h)
    for e in external:
        reg[e.id] = e.to_result_dict()
    return reg
