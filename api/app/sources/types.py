from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class NormalizedHit:
    id: str
    source: str
    title: str
    snippet: str
    url: str
    published_at: str | None = None
    domain: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def to_result_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "summary": self.snippet,
            "url": self.url,
            "source_domain": self.domain or "",
            "published_at": self.published_at,
            "source": self.source,
            **self.extra,
        }
