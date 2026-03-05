import asyncio
import json

import pytest

from agentorchestrator.core.event_bus import Event, RedisEventBus


class MockPubSub:
    def __init__(self, queue):
        self.queue = queue
        self._subscribed = False

    async def subscribe(self, channel):
        self._subscribed = True
        self.channel = channel

    async def unsubscribe(self, channel):
        self._subscribed = False

    async def close(self):
        return

    async def listen(self):
        while True:
            data = await self.queue.get()
            yield {"type": "message", "data": data}


class MockRedisService:
    def __init__(self):
        self.queue = asyncio.Queue()
        self._pubsub = MockPubSub(self.queue)

    async def ensure_connected(self):
        return self

    def client(self):
        return self

    def pubsub(self):
        return self._pubsub

    async def publish(self, channel, data):
        await self.queue.put(data)


@pytest.mark.asyncio
async def test_redis_event_bus_with_mock_service():
    service = MockRedisService()
    bus = RedisEventBus(service, channel="ao:events")

    received = []

    async def collector():
        async for evt in bus.subscribe(["TestEvent"]):
            received.append(evt)
            break

    task = asyncio.create_task(collector())
    await bus.publish(Event(type="TestEvent", payload={"x": 1}, run_id="r1"))
    await asyncio.wait_for(task, timeout=2.0)

    assert received and received[0].type == "TestEvent"
    assert received[0].payload["x"] == 1
