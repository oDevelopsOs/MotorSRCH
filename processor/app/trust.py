SOURCE_TRUST = {
    "sec.gov": 1.0,
    "reuters.com": 0.95,
    "ft.com": 0.93,
    "bloomberg.com": 0.93,
    "wsj.com": 0.90,
    "investopedia.com": 0.75,
    "federalreserve.gov": 0.95,
}


def trust_for_domain(domain: str) -> float:
    if not domain:
        return 0.5
    d = domain.lower().strip()
    for k, v in SOURCE_TRUST.items():
        if k in d or d.endswith(k):
            return v
    return 0.5
