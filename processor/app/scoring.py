from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .trust import trust_for_domain


def freshness_score(published_at: datetime | None) -> float:
    if published_at is None:
        return 0.5
    now = datetime.now(timezone.utc)
    if published_at.tzinfo is None:
        published_at = published_at.replace(tzinfo=timezone.utc)
    age_hours = (now - published_at).total_seconds() / 3600.0
    return 1.0 / (1.0 + age_hours / 24.0)


def calculate_score(doc: dict[str, Any]) -> float:
    pub = doc.get("published_at")
    if isinstance(pub, str):
        try:
            pub = datetime.fromisoformat(pub.replace("Z", "+00:00"))
        except ValueError:
            pub = None
    elif not isinstance(pub, datetime):
        pub = None
    fresh = freshness_score(pub)
    domain = str(doc.get("source_domain") or doc.get("domain") or "")
    trust = trust_for_domain(domain)
    return fresh * 0.4 + trust * 0.6
