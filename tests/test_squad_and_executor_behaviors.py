"""
Additional behavioral tests for Squad components and executor edge cases.
"""

import argparse
import asyncio
import pathlib
import sys

import pytest

# Ensure repo root is on path for direct imports
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from agentorchestrator import AgentOrchestrator, ChainContext  # noqa: E402
from agentorchestrator.core.context import ContextScope  # noqa: E402
from agentorchestrator.squad.agents.base import (  # noqa: E402
    Agent,
    AgentOptions,
    AgentStreamResponse,
)
from agentorchestrator.squad.classifiers.base import Classifier  # noqa: E402
from agentorchestrator.squad.classifiers.llm_gateway import (  # noqa: E402
    LLMGatewayClassifier,
    LLMGatewayClassifierOptions,
)
from agentorchestrator.squad.orchestrator import MultiAgentOrchestrator  # noqa: E402
from agentorchestrator.squad.storage.memory import InMemoryChatStorage  # noqa: E402
from agentorchestrator.squad.types import (  # noqa: E402
    ClassifierResult,
    ConversationMessage,
    ParticipantRole,
)
from agentorchestrator.services.mem0 import (  # noqa: E402
    CompositeMemory,
    Mem0Memory,
    MemoryEntry,
    BaseMemory,
)
from agentorchestrator.cli import cmd_new_agent, cmd_new_chain  # noqa: E402


class DummyLLMClient:
    """Stub LLM client to capture generate_async kwargs."""

    def __init__(self):
        self.calls: list[dict] = []

    async def generate_async(self, prompt: str, system_prompt: str | None = None, **kwargs):
        self.calls.append({"prompt": prompt, "system_prompt": system_prompt, **kwargs})
        return "selected_agent: helper\nconfidence: 0.75"


class HelperAgent(Agent):
    def __init__(self):
        super().__init__(AgentOptions(name="Helper", description="Returns canned replies"))

    async def process_request(
        self,
        input_text: str,
        user_id: str,
        session_id: str,
        chat_history: list[ConversationMessage],
        additional_params: dict | None = None,
    ) -> ConversationMessage:
        return ConversationMessage(
            role=ParticipantRole.ASSISTANT.value,
            content=[{"text": f"echo: {input_text}"}],
        )


@pytest.mark.asyncio
async def test_llm_classifier_respects_option_overrides():
    dummy_llm = DummyLLMClient()
    classifier = LLMGatewayClassifier(
        LLMGatewayClassifierOptions(
            llm_client=dummy_llm,
            model_name="model-x",
            temperature=0.33,
            max_tokens=55,
        )
    )
    agent = HelperAgent()
    classifier.set_agents({agent.id: agent})

    result = await classifier.classify("hello", [], {})

    assert result.selected_agent == agent
    call = dummy_llm.calls[-1]
    assert call["model"] == "model-x"
    assert call["temperature"] == 0.33
    assert call["max_tokens"] == 55


@pytest.mark.asyncio
async def test_fail_fast_records_cancelled_steps():
    ao = AgentOrchestrator(name="fail_fast_test", isolated=True)

    @ao.step(name="fail_step")
    async def fail_step(ctx: ChainContext):
        raise ValueError("boom")

    @ao.step(name="slow_step")
    async def slow_step(ctx: ChainContext):
        await asyncio.sleep(0.5)
        ctx.set("slow_result", True, scope=ContextScope.STEP)
        return {"slow": True}

    @ao.chain(name="ff_chain")
    class FFChain:
        steps = ["fail_step", "slow_step"]

    ctx = ChainContext(request_id="req_ff")
    try:
        await ao._executor.execute("ff_chain", ctx)
    except Exception:
        # Expected because fail-fast re-raises first exception
        pass

    skipped = ctx.get_skipped_steps()
    assert any(r.step_name == "slow_step" for r in skipped), "cancelled step should be marked skipped"


class StreamingAgent(Agent):
    def __init__(self):
        super().__init__(AgentOptions(name="Streamer", description="Streams tokens"))

    def is_streaming_enabled(self) -> bool:
        return True

    async def process_request(
        self,
        input_text: str,
        user_id: str,
        session_id: str,
        chat_history: list[ConversationMessage],
        additional_params: dict | None = None,
    ):
        async def generator():
            yield AgentStreamResponse(text="hello ")
            yield AgentStreamResponse(text="world")

        return generator()


class StubClassifier(Classifier):
    def __init__(self, agent: Agent):
        super().__init__()
        self._agent = agent

    async def process_request(
        self,
        input_text: str,
        chat_history: list[ConversationMessage],
        additional_params=None,
    ) -> ClassifierResult:
        return ClassifierResult(selected_agent=self._agent, confidence=1.0)


@pytest.mark.asyncio
async def test_streaming_without_final_message_accumulates_text():
    agent = StreamingAgent()
    classifier = StubClassifier(agent)
    orchestrator = MultiAgentOrchestrator(
        storage=InMemoryChatStorage(),
        classifier=classifier,
        default_agent=agent,
    )
    orchestrator.add_agent(agent)

    response = await orchestrator.route_request(
        user_input="hi",
        user_id="user1",
        session_id="sess1",
        stream_response=True,
    )

    assert response.streaming is True
    assert response.output.content[0]["text"] == "hello world"


def test_cli_generators_create_missing_directories(tmp_path):
    target = tmp_path / "nested" / "agents"
    args_agent = argparse.Namespace(name="Demo", output_dir=str(target), force=False)
    rc_agent = cmd_new_agent(args_agent)
    assert rc_agent == 0
    assert (target / "demo_agent.py").exists()

    target_chain = tmp_path / "nested" / "chains"
    args_chain = argparse.Namespace(name="Flow", output_dir=str(target_chain), force=False)
    rc_chain = cmd_new_chain(args_chain)
    assert rc_chain == 0
    assert (target_chain / "flow_chain.py").exists()


# ════════════════════════════════════════════════════════════════════
# Mem0 stubs and tests
# ════════════════════════════════════════════════════════════════════


class StubMem0Client:
    """Synchronous stub matching MemoryStoreClientProtocol."""

    def __init__(self):
        self._store: list[dict] = []
        self.raise_on_add = False
        self.raise_on_search = False
        self.raise_on_get_all = False
        self.raise_on_delete = False

    def add(self, memory: str, metadata: dict | None = None) -> dict:
        if self.raise_on_add:
            raise RuntimeError("add failed")
        entry = {
            "id": f"id-{len(self._store)}",
            "memory": memory,
            "metadata": metadata or {},
            "score": 0.5,
        }
        self._store.append(entry)
        return {"id": entry["id"]}

    def search(self, query: str, limit: int = 10) -> list[dict]:
        if self.raise_on_search:
            raise RuntimeError("search failed")
        return self._store[:limit]

    def get_all(self) -> list[dict]:
        if self.raise_on_get_all:
            raise RuntimeError("get_all failed")
        return list(self._store)

    def delete(self, memory_id: str) -> bool:
        if self.raise_on_delete:
            raise RuntimeError("delete failed")
        before = len(self._store)
        self._store = [m for m in self._store if m["id"] != memory_id]
        return len(self._store) < before


@pytest.mark.asyncio
async def test_mem0_happy_paths_and_error_handling():
    client = StubMem0Client()
    memory = Mem0Memory(client=client, default_user_id="u1")

    # Happy add
    entry = await memory.add("User likes cats")
    assert entry.id.startswith("id-")
    assert entry.metadata["user_id"] == "u1"

    # Happy search with user filter keeps entries with matching user_id
    results = await memory.search("cats", user_id="u1")
    assert len(results) == 1
    assert results[0].content == "User likes cats"

    # Error paths: search returns [] on exception
    client.raise_on_search = True
    results = await memory.search("fail")
    assert results == []

    # Error path: add propagates
    client.raise_on_add = True
    with pytest.raises(RuntimeError):
        await memory.add("boom")

    # Error path: delete returns False on exception
    client.raise_on_delete = True
    success = await memory.delete("id-0")
    assert success is False


class FakeMemory(BaseMemory):
    """Minimal BaseMemory impl for CompositeMemory tests."""

    def __init__(self, entries: list[MemoryEntry]):
        self._entries = entries

    async def add(self, content: str, user_id=None, session_id=None, metadata=None) -> MemoryEntry:
        entry = MemoryEntry(id=f"f-{len(self._entries)}", content=content, metadata=metadata or {})
        self._entries.append(entry)
        return entry

    async def search(self, query: str, user_id=None, limit: int = 10) -> list[MemoryEntry]:
        items = self._entries[:limit]
        if user_id:
            items = [e for e in items if e.metadata.get("user_id") == user_id]
        return items

    async def get_all(self, user_id=None) -> list[MemoryEntry]:
        if user_id:
            return [e for e in self._entries if e.metadata.get("user_id") == user_id]
        return list(self._entries)

    async def delete(self, memory_id: str) -> bool:
        before = len(self._entries)
        self._entries = [e for e in self._entries if e.id != memory_id]
        return len(self._entries) < before

    async def clear(self, user_id: str | None = None) -> bool:
        if user_id:
            self._entries = [e for e in self._entries if e.metadata.get("user_id") != user_id]
        else:
            self._entries = []
        return True


@pytest.mark.asyncio
async def test_composite_memory_dedup_and_user_filtering():
    mem1 = FakeMemory(
        [
            MemoryEntry(id="1", content="A", metadata={"user_id": "u1"}, relevance_score=0.9),
        ]
    )
    mem2 = FakeMemory(
        [
            MemoryEntry(id="1", content="A", metadata={"user_id": "u1"}, relevance_score=0.8),
            MemoryEntry(id="2", content="B", metadata={"user_id": "u2"}, relevance_score=0.7),
        ]
    )

    composite = CompositeMemory([mem1, mem2])

    results = await composite.search("anything")
    assert [r.id for r in results] == ["1", "2"]

    # User filter should drop entries not matching
    user_results = await composite.search("anything", user_id="u1")
    assert all(r.metadata.get("user_id") == "u1" for r in user_results)
