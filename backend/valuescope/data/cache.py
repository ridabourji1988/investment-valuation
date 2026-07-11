"""Tiny thread-safe TTL cache + retrying GET, shared by all data clients.

The whole data layer is autonomous: sources are fetched on demand, cached with
per-kind TTLs, retried with backoff, and every failure degrades to the next
source — never to made-up numbers.
"""
from __future__ import annotations

import threading
import time

import httpx

_STORE: dict = {}
_LOCK = threading.Lock()


def get_cached(key: str, ttl: float, build):
    """Return the cached value for key, rebuilding via build() when stale.

    Failures never poison the cache: if build() raises and a stale value
    exists, the stale value is served (data beats downtime); otherwise the
    error propagates."""
    now = time.time()
    with _LOCK:
        hit = _STORE.get(key)
        if hit and now - hit[0] < ttl:
            return hit[1]
    try:
        value = build()
    except Exception:
        with _LOCK:
            hit = _STORE.get(key)
            if hit:
                return hit[1]  # stale beats nothing
        raise
    with _LOCK:
        _STORE[key] = (now, value)
    return value


def http_get(url: str, *, params: dict | None = None, headers: dict | None = None,
             timeout: float = 20.0, retries: int = 2) -> httpx.Response:
    last: Exception | None = None
    for attempt in range(retries + 1):
        try:
            r = httpx.get(url, params=params, headers=headers, timeout=timeout,
                          follow_redirects=True)
            if r.status_code in (429, 502, 503) and attempt < retries:
                time.sleep(0.8 * (attempt + 1))
                continue
            r.raise_for_status()
            return r
        except Exception as e:  # noqa: BLE001
            last = e
            if attempt < retries:
                time.sleep(0.5 * (attempt + 1))
    raise last  # type: ignore[misc]
