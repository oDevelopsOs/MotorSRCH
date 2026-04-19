from __future__ import annotations

from datasketch import MinHash, MinHashLSH


class SemanticDedup:
    def __init__(self, threshold: float = 0.8, num_perm: int = 128) -> None:
        self.lsh = MinHashLSH(threshold=threshold, num_perm=num_perm)
        self.num_perm = num_perm
        self._seen_ids: set[str] = set()

    def should_skip_duplicate(self, text: str, doc_id: str) -> bool:
        if doc_id in self._seen_ids:
            return True
        m = MinHash(num_perm=self.num_perm)
        for w in text.lower().split():
            m.update(w.encode("utf-8"))
        if self.lsh.query(m):
            return True
        self.lsh.insert(doc_id, m)
        self._seen_ids.add(doc_id)
        return False
