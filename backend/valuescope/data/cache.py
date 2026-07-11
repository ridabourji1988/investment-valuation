"""Tiny thread-safe TTL cache + retrying GET, shared by all data clients.

The whole data layer is autonomous: sources are fetched on demand, cached with
per-kind TTLs, retried with backoff, and every failure degrades to the next
source — never to made-up numbers.

Small entries (< 512 KB) are persisted to disk so process restarts don't
refetch everything — that cold-start burst is what triggers Yahoo's per-IP
rate limiting. Large entries (EDGAR companyfacts, several MB each) stay
memory-only: SEC allows 10 req/s, so refetching them is cheap and polite.
"""
from __future__ import annotations

import os
import pickle
import tempfile
import threading
import time

import httpx

_STORE: dict = {}
_LOCK = threading.Lock()

# VALUESCOPE_DATA_DIR: durable directory for all pickles (mount a Railway
# Volume there so big-universe warms survive redeploys). Default: OS tmp,
# which is ephemeral per container.
_DATA_DIR = os.getenv("VALUESCOPE_DATA_DIR", tempfile.gettempdir())
_PERSIST_PATH = os.getenv("VALUESCOPE_CACHE_FILE",
                          os.path.join(_DATA_DIR, "valuescope-cache.pkl"))
_PERSIST_MAX_BYTES = 512 * 1024
_persist_loaded = False
_last_persist = 0.0


def _load_persisted() -> None:
    global _persist_loaded
    if _persist_loaded:
        return
    _persist_loaded = True
    try:
        with open(_PERSIST_PATH, "rb") as fh:
            for k, v in pickle.load(fh).items():
                _STORE.setdefault(k, v)
    except Exception:  # noqa: BLE001 — missing/corrupt cache file is fine
        pass


def _persist() -> None:
    """Write small entries to disk (throttled to every 5s; atomic rename)."""
    global _last_persist
    now = time.time()
    if now - _last_persist < 5.0:
        return
    _last_persist = now
    try:
        small = {}
        for k, v in _STORE.items():
            try:
                blob = pickle.dumps(v)
            except Exception:  # noqa: BLE001 — unpicklable, skip
                continue
            if len(blob) <= _PERSIST_MAX_BYTES:
                small[k] = v
        tmp = _PERSIST_PATH + ".tmp"
        with open(tmp, "wb") as fh:
            pickle.dump(small, fh)
        os.replace(tmp, _PERSIST_PATH)
    except Exception:  # noqa: BLE001 — persistence is best-effort
        pass


def get_cached(key: str, ttl: float, build):
    """Return the cached value for key, rebuilding via build() when stale.

    Failures never poison the cache: if build() raises and a stale value
    exists, the stale value is served (data beats downtime); otherwise the
    error propagates."""
    now = time.time()
    with _LOCK:
        _load_persisted()
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
        _persist()
    return value


def http_get(url: str, *, params: dict | None = None, headers: dict | None = None,
             timeout: float = 20.0, retries: int = 2, alt_hosts: dict | None = None) -> httpx.Response:
    """GET with backoff. alt_hosts maps host -> alternate host, rotated on 429
    (Yahoo rate-limits per host+IP; query2 mirrors query1)."""
    last: Exception | None = None
    current = url
    for attempt in range(retries + 1):
        try:
            r = httpx.get(current, params=params, headers=headers, timeout=timeout,
                          follow_redirects=True)
            if r.status_code in (429, 502, 503) and attempt < retries:
                if alt_hosts:
                    for host, alt in alt_hosts.items():
                        if host in current:
                            current = current.replace(host, alt)
                            break
                time.sleep(1.5 * (attempt + 1) if r.status_code == 429 else 0.8 * (attempt + 1))
                continue
            r.raise_for_status()
            return r
        except Exception as e:  # noqa: BLE001
            last = e
            if attempt < retries:
                time.sleep(0.5 * (attempt + 1))
    raise last  # type: ignore[misc]
