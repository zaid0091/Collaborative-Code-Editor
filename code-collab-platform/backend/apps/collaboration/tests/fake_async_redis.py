"""Minimal async Redis mock for consumer tests."""


class FakeAsyncRedis:
    def __init__(self):
        self.values: dict[str, str] = {}
        self.lists: dict[str, list[str]] = {}
        self.sets: dict[str, set[str]] = {}

    async def get(self, key: str):
        return self.values.get(key)

    async def set(self, key: str, value, ex=None):
        self.values[key] = str(value)

    async def exists(self, key: str) -> int:
        if key in self.values or key in self.lists or key in self.sets:
            return 1
        return 0

    async def delete(self, key: str):
        self.values.pop(key, None)
        self.lists.pop(key, None)
        self.sets.pop(key, None)

    async def expire(self, key: str, seconds: int):
        return True

    async def sadd(self, key: str, *values: str):
        target = self.sets.setdefault(key, set())
        target.update(values)

    async def srem(self, key: str, *values: str):
        target = self.sets.get(key, set())
        for value in values:
            target.discard(value)

    async def scard(self, key: str) -> int:
        return len(self.sets.get(key, set()))

    async def rpush(self, key: str, value: str):
        self.lists.setdefault(key, []).append(value)

    async def lrange(self, key: str, start: int, end: int):
        values = self.lists.get(key, [])
        if end == -1:
            end = len(values) - 1
        return values[start : end + 1]

    async def llen(self, key: str) -> int:
        return len(self.lists.get(key, []))

    async def scan_iter(self, match: str):
        del match
        for key in self.lists:
            if key.startswith("file:") and key.endswith(":updates"):
                yield key

    async def aclose(self):
        return None

    async def incr(self, key: str) -> int:
        current = int(self.values.get(key, 0))
        current += 1
        self.values[key] = str(current)
        return current

    def pipeline(self):
        return FakeAsyncPipeline(self)


class FakeAsyncPipeline:
    def __init__(self, redis: FakeAsyncRedis):
        self.redis = redis
        self.commands: list[tuple] = []

    def rpush(self, key: str, value: str):
        self.commands.append(("rpush", key, value))

    def incr(self, key: str):
        self.commands.append(("incr", key))

    def expire(self, key: str, seconds: int):
        self.commands.append(("expire", key, seconds))

    async def execute(self):
        results = []
        for command in self.commands:
            if command[0] == "rpush":
                await self.redis.rpush(command[1], command[2])
                results.append(None)
            elif command[0] == "incr":
                results.append(await self.redis.incr(command[1]))
            elif command[0] == "expire":
                await self.redis.expire(command[1], command[2])
                results.append(True)
        return results
