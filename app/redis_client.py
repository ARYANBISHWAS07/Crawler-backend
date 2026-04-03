import json
import os
from typing import Any, Optional

import redis.asyncio as redis_async
import redis as redis_sync

_redis_async: Optional[redis_async.Redis] = None
_redis_url = os.getenv("REDIS_URL", "").strip()


async def connect_redis() -> None:
    global _redis_async
    if not _redis_url:
        return
    if _redis_async is not None:
        return
    _redis_async = redis_async.from_url(_redis_url, encoding="utf-8", decode_responses=True)
    try:
        await _redis_async.ping()
        print("Connected to Redis")
    except Exception as exc:
        print(f"Failed to connect to Redis: {exc}")
        _redis_async = None


async def close_redis() -> None:
    global _redis_async
    if _redis_async is None:
        return
    try:
        await _redis_async.close()
    finally:
        _redis_async = None


def get_redis() -> Optional[redis_async.Redis]:
    return _redis_async


async def cache_get_json(key: str) -> Optional[Any]:
    client = get_redis()
    if client is None:
        return None
    try:
        value = await client.get(key)
        if value is None:
            return None
        return json.loads(value)
    except Exception:
        return None


async def cache_set_json(key: str, payload: Any, ttl_seconds: int = 60) -> None:
    client = get_redis()
    if client is None:
        return
    try:
        await client.set(key, json.dumps(payload), ex=ttl_seconds)
    except Exception:
        return


async def cache_delete(*keys: str) -> None:
    client = get_redis()
    if client is None or not keys:
        return
    try:
        await client.delete(*keys)
    except Exception:
        return


async def publish_event(channel: str, payload: dict) -> None:
    client = get_redis()
    if client is None:
        return
    try:
        await client.publish(channel, json.dumps(payload))
    except Exception:
        return


def _get_sync_redis() -> Optional[redis_sync.Redis]:
    if not _redis_url:
        return None
    try:
        return redis_sync.from_url(_redis_url, encoding="utf-8", decode_responses=True)
    except Exception:
        return None


def cache_delete_sync(*keys: str) -> None:
    client = _get_sync_redis()
    if client is None or not keys:
        return
    try:
        client.delete(*keys)
    except Exception:
        return


def publish_event_sync(channel: str, payload: dict) -> None:
    client = _get_sync_redis()
    if client is None:
        return
    try:
        client.publish(channel, json.dumps(payload))
    except Exception:
        return
