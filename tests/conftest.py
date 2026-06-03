from __future__ import annotations

import fnmatch
from typing import Any


ENQUEUED: list[tuple[int, str | None]] = []


def sample_task(value: int, marker: str | None = None) -> None:
    ENQUEUED.append((value, marker))


class FakeQueue:
    calls: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []

    def __init__(self, name: str, connection: Any):
        self.name = name
        self.connection = connection

    def enqueue(self, func, *args, **kwargs):
        self.calls.append((self.name, args, kwargs))
        return {"func": func, "args": args, "kwargs": kwargs}


class MemoryRedis:
    def __init__(self):
        self.hashes: dict[str, dict[str, Any]] = {}
        self.strings: dict[str, Any] = {}
        self.zsets: dict[str, dict[str, float]] = {}
        self.events: list[tuple[str, str]] = []

    def hset(self, key, mapping=None, *args, **kwargs):
        self.hashes.setdefault(key, {}).update(mapping or {})
        return len(mapping or {})

    def hgetall(self, key):
        return dict(self.hashes.get(key, {}))

    def delete(self, key):
        removed = key in self.hashes or key in self.strings or key in self.zsets
        self.hashes.pop(key, None)
        self.strings.pop(key, None)
        self.zsets.pop(key, None)
        return int(removed)

    def zadd(self, key, mapping, **kwargs):
        self.zsets.setdefault(key, {}).update(
            {member: float(score) for member, score in mapping.items()}
        )
        return len(mapping)

    def zrem(self, key, *members):
        zset = self.zsets.setdefault(key, {})
        removed = 0
        for member in members:
            member = member.decode() if isinstance(member, bytes) else member
            if member in zset:
                removed += 1
                del zset[member]
        return removed

    def zrange(self, key, start, end, withscores=False, **kwargs):
        items = sorted(
            self.zsets.get(key, {}).items(), key=lambda item: (item[1], item[0])
        )
        if end == -1:
            selected = items[start:]
        else:
            selected = items[start : end + 1]
        if withscores:
            return selected
        return [member for member, _score in selected]

    def zrangebyscore(self, key, min, max, **kwargs):
        min_score = float("-inf") if min == "-inf" else float(min)
        max_score = float("inf") if max == "+inf" else float(max)
        return [
            member
            for member, score in sorted(
                self.zsets.get(key, {}).items(), key=lambda item: (item[1], item[0])
            )
            if min_score <= score <= max_score
        ]

    def set(self, key, value, nx=False, ex=None):
        if nx and key in self.strings:
            return False
        self.strings[key] = value
        return True

    def get(self, key):
        return self.strings.get(key)

    def publish(self, channel, payload):
        self.events.append((channel, payload))
        return 1

    def eval(self, script, numkeys, key, token, *args):
        if self.strings.get(key) != token:
            return 0
        if args:
            return 1
        if self.strings.get(key) == token:
            del self.strings[key]
            return 1
        return 0

    def keys(self, pattern):
        return [
            key
            for key in set(self.hashes) | set(self.strings) | set(self.zsets)
            if fnmatch.fnmatch(key, pattern)
        ]
