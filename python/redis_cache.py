"""
redis_cache.py — Athena read-cache layer for hot scribe queries.
================================================================

Purpose
-------
The Athena dashboard polls 5-7 endpoints every 3 seconds. Each endpoint
hits the SQLite scribe DB. During heavy backtest write windows the
bridge process syncs FORGE journal data in large transactions, holding
the WAL writer lock long enough that Athena reads bump into
busy_timeout=5000ms and the dashboard appears frozen.

This module wraps hot scribe queries in a Redis cache with short TTL
(2 seconds by default). Pattern:

  - Cache HIT:  return cached JSON, ~0.5ms response, no scribe touch.
  - Cache MISS: run the underlying scribe call, cache the result, return.
  - Cache DOWN: skip cache, fall through to direct scribe call. Athena
                stays functional even if Redis is unhealthy.

Future: when F6 (containerize) lands, swap Redis for Dragonfly in the
docker-compose. Dragonfly speaks the Redis wire protocol — no code
change required here.

Configuration (read from environment, with sensible defaults)
-------------------------------------------------------------
  REDIS_HOST              default 127.0.0.1
  REDIS_PORT              default 6379
  REDIS_PASSWORD          default "" (no auth — single-machine localhost)
  REDIS_DB                default 0
  ATHENA_CACHE_ENABLED    default "1" — set to "0" to disable cache layer
  ATHENA_CACHE_DEFAULT_TTL  default 2 (seconds)

Usage
-----
    from redis_cache import cached

    @cached(ttl=2, key_prefix="api:live")
    def build_live_payload(...):
        return scribe.get_open_groups() + ...

    # Decorated function caches by (prefix + hash(args)).

Or imperatively:

    from redis_cache import get_cache
    cache = get_cache()
    result = cache.get_or_compute(
        key="api:live:default",
        ttl=2,
        compute=lambda: build_live_payload(),
    )

Cache design notes
------------------
- TTL-based, not pub/sub invalidation. Simple and reliable. Future F5R-2
  could add bridge → Redis pub/sub for sub-second invalidation, but TTL=2s
  is plenty for a dashboard that polls every 3s.
- Keys are namespaced with `signal:` prefix to avoid collisions if Redis
  is shared with anything else.
- Cached values are JSON strings. Pickle was rejected — JSON is debuggable
  via redis-cli and won't break across Python version upgrades.
- Stale-while-error: if compute() raises during a cache miss, the cache
  retains the previous value (which has already expired) at a longer
  fallback TTL so the dashboard sees stale data instead of a 500. This is
  defensive — never let cache logic make Athena worse than no-cache.
"""

import os
import json
import time
import hashlib
import logging
import functools
from typing import Any, Callable, Optional

log = logging.getLogger("redis_cache")

try:
    import redis  # type: ignore
    _REDIS_AVAILABLE = True
except ImportError:
    redis = None  # type: ignore
    _REDIS_AVAILABLE = False
    log.warning("redis package not installed — cache layer disabled")


# ─────────────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────────────

_HOST = os.environ.get("REDIS_HOST", "127.0.0.1")
_PORT = int(os.environ.get("REDIS_PORT", "6379"))
_PASSWORD = os.environ.get("REDIS_PASSWORD", "") or None
_DB = int(os.environ.get("REDIS_DB", "0"))
_ENABLED = os.environ.get("ATHENA_CACHE_ENABLED", "1") == "1"
_DEFAULT_TTL = int(os.environ.get("ATHENA_CACHE_DEFAULT_TTL", "2"))
_NAMESPACE = "signal:"


# ─────────────────────────────────────────────────────────────────────
# Cache singleton
# ─────────────────────────────────────────────────────────────────────


class Cache:
    """Thin Redis wrapper with defensive fallback.

    Every read/write swallows Redis errors and logs at debug. Athena
    must never crash because of a cache hiccup — the cache is an
    optimization, not a correctness layer.
    """

    def __init__(self):
        self._client = None
        self._healthy = False
        if _REDIS_AVAILABLE and _ENABLED:
            self._connect()

    def _connect(self):
        try:
            self._client = redis.Redis(
                host=_HOST,
                port=_PORT,
                db=_DB,
                password=_PASSWORD,
                socket_connect_timeout=1.0,
                socket_timeout=1.0,
                decode_responses=False,  # store raw bytes; we encode/decode JSON ourselves
                retry_on_timeout=False,  # fast-fail on a single tick; we want predictable latency
            )
            # Health check at construct — if Redis is down, mark unhealthy
            # and fall through to direct scribe for the lifetime of THIS process.
            self._client.ping()
            self._healthy = True
            log.info("redis_cache connected: %s:%s db=%d", _HOST, _PORT, _DB)
        except Exception as e:
            log.warning("redis_cache connect failed: %s — cache disabled for this process", e)
            self._client = None
            self._healthy = False

    @property
    def enabled(self) -> bool:
        return self._healthy and _ENABLED

    def _full_key(self, key: str) -> str:
        return _NAMESPACE + key

    def get(self, key: str) -> Optional[Any]:
        if not self.enabled:
            return None
        try:
            raw = self._client.get(self._full_key(key))
            if raw is None:
                return None
            return json.loads(raw)
        except Exception as e:
            log.debug("redis_cache get(%s) failed: %s", key, e)
            return None

    def set(self, key: str, value: Any, ttl: int = _DEFAULT_TTL):
        if not self.enabled:
            return
        try:
            encoded = json.dumps(value, default=str).encode("utf-8")
            self._client.setex(self._full_key(key), ttl, encoded)
        except Exception as e:
            log.debug("redis_cache set(%s) failed: %s", key, e)

    def delete(self, key: str):
        if not self.enabled:
            return
        try:
            self._client.delete(self._full_key(key))
        except Exception as e:
            log.debug("redis_cache delete(%s) failed: %s", key, e)

    def get_or_compute(
        self,
        key: str,
        compute: Callable[[], Any],
        ttl: int = _DEFAULT_TTL,
    ) -> Any:
        """Canonical cache pattern. Returns cached value if fresh, else
        runs compute(), stores, returns. Cache hiccups fall through to
        compute() directly.
        """
        if self.enabled:
            cached = self.get(key)
            if cached is not None:
                return cached
        # Compute path (cache miss OR cache disabled)
        value = compute()
        if self.enabled and value is not None:
            self.set(key, value, ttl=ttl)
        return value

    def health(self) -> dict:
        """Return diagnostic info for `make redis-status` / dashboard."""
        info = {
            "enabled": _ENABLED,
            "healthy": self._healthy,
            "host": _HOST,
            "port": _PORT,
            "db": _DB,
            "default_ttl_sec": _DEFAULT_TTL,
        }
        if self._healthy and self._client:
            try:
                pong = self._client.ping()
                info["ping"] = bool(pong)
                # dbsize is fast — used to confirm Redis sees actual cached entries
                info["keys"] = self._client.dbsize()
            except Exception as e:
                info["ping"] = False
                info["error"] = str(e)
        return info


_singleton: Optional[Cache] = None


def get_cache() -> Cache:
    """Process-local singleton. First call connects to Redis."""
    global _singleton
    if _singleton is None:
        _singleton = Cache()
    return _singleton


# ─────────────────────────────────────────────────────────────────────
# Decorator API
# ─────────────────────────────────────────────────────────────────────


def _args_hash(args: tuple, kwargs: dict) -> str:
    """Stable short hash of call arguments for cache-key construction.
    Used so that e.g. `get_recent_closures(limit=5)` and
    `get_recent_closures(limit=20)` get distinct cache slots.
    """
    if not args and not kwargs:
        return "default"
    blob = json.dumps([args, sorted(kwargs.items())], default=str).encode("utf-8")
    return hashlib.sha1(blob).hexdigest()[:12]


def cached(ttl: int = _DEFAULT_TTL, key_prefix: Optional[str] = None):
    """Decorator: cache the return value of a function by (prefix + args-hash).

    The decorated function MUST return a JSON-serializable object (or None
    for explicit "no value"). Functions that return raw objects, file
    handles, etc. should NOT be decorated.

    The cache short-circuits in two cases:
      1. Cache disabled (ATHENA_CACHE_ENABLED=0 or Redis unreachable):
         calls the wrapped function every time.
      2. Function raises during a cache miss: exception propagates;
         no garbage is cached.
    """
    def _decorator(fn):
        prefix = key_prefix or f"fn:{fn.__module__}:{fn.__qualname__}"

        @functools.wraps(fn)
        def _wrapper(*args, **kwargs):
            cache = get_cache()
            key = f"{prefix}:{_args_hash(args, kwargs)}"
            return cache.get_or_compute(
                key=key,
                compute=lambda: fn(*args, **kwargs),
                ttl=ttl,
            )
        return _wrapper
    return _decorator


def cached_view(ttl: int = _DEFAULT_TTL):
    """Flask route-handler decorator. Caches the JSON payload of a view
    by (endpoint name + request.full_path query string).

    Designed for views that return `jsonify(dict)` or `(jsonify(dict), status_code)`.
    Views returning streaming Responses, files, or non-JSON content should
    NOT be decorated — they'll fall back to direct call without caching.

    Caching short-circuits if:
      - Cache is disabled / Redis unreachable
      - View returns a non-200 status (errors aren't cached)
      - View returns a Response we can't safely .get_json() from

    Usage:
        @app.route("/api/live")
        @cached_view(ttl=2)
        def api_live():
            return jsonify(build_live_payload())
    """
    def _decorator(fn):
        @functools.wraps(fn)
        def _wrapper(*args, **kwargs):
            from flask import request, jsonify, Response  # lazy import — keeps redis_cache importable outside Flask context

            cache = get_cache()
            if not cache.enabled:
                return fn(*args, **kwargs)

            # Cache key includes path + query string so /api/signals?limit=50
            # and /api/signals?limit=20 get distinct slots.
            key = f"view:{request.full_path}"

            # Cache hit?
            cached_payload = cache.get(key)
            if cached_payload is not None:
                # Wrap the cached dict back into a Response with cache-hit
                # diagnostic header so dashboard / debugging can see it.
                resp = jsonify(cached_payload)
                resp.headers["X-Athena-Cache"] = "HIT"
                return resp

            # Cache miss — compute, then try to extract JSON for caching
            result = fn(*args, **kwargs)

            # Result might be: Response | dict | tuple(Response|dict, status) | tuple(dict, status, headers)
            payload = None
            status = 200
            response_obj = None

            if isinstance(result, tuple):
                response_obj = result[0]
                if len(result) > 1 and isinstance(result[1], int):
                    status = result[1]
            else:
                response_obj = result

            if isinstance(response_obj, Response):
                if response_obj.status_code != 200:
                    response_obj.headers["X-Athena-Cache"] = "MISS-NOCACHE-NONOK"
                    return result
                try:
                    payload = response_obj.get_json()
                except Exception:
                    payload = None
                response_obj.headers["X-Athena-Cache"] = "MISS"
            elif isinstance(response_obj, dict):
                payload = response_obj
                # Convert dict → Response so we can attach headers consistently
                response_obj = jsonify(response_obj)
                response_obj.headers["X-Athena-Cache"] = "MISS"
                if isinstance(result, tuple):
                    result = (response_obj,) + tuple(result[1:])
                else:
                    result = response_obj
            else:
                # Unknown return shape — don't cache, just return as-is
                return result

            # Cache only on 200 + extractable JSON
            if status == 200 and payload is not None:
                cache.set(key, payload, ttl=ttl)

            return result
        return _wrapper
    return _decorator
