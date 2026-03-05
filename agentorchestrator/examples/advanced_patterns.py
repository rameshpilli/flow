"""
Advanced Patterns in AgentOrchestrator
======================================

Demonstrates advanced features:
1. Dynamic DAG Modification (Map-Reduce pattern)
2. Automatic Agent Handoffs in MultiAgentOrchestrator
3. Shared Squad Memory across agents
"""

import asyncio
import logging
from typing import Any, List, Dict

from agentorchestrator import AgentOrchestrator, Context
from agentorchestrator.squad import (
    MultiAgentOrchestrator,
    Agent,
    AgentOptions,
    ConversationMessage,
    ParticipantRole,
)
from agentorchestrator.squad.storage import InMemoryChatStorage

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════════════════
# 1. DYNAMIC DAG MODIFICATION (Map-Reduce)
# ═══════════════════════════════════════════════════════════════════════════════

async def worker_step(ctx: Context) -> dict:
    """A worker step that processes a specific item."""
    # In a real scenario, this would get the item from context
    return {"status": "processed"}

def create_dynamic_chain() -> AgentOrchestrator:
    ao = AgentOrchestrator(name="dynamic_example")

    @ao.step(name="planner")
    async def planner(ctx: Context):
        """Planner step that dynamically generates worker steps."""
        num_workers = 3
        logger.info(f"Planner creating {num_workers} dynamic workers")
        
        dynamic_steps = []
        for i in range(num_workers):
            dynamic_steps.append({
                "name": f"worker_{i}",
                "handler": worker_step,
                "deps": ["planner"]
            })
        
        # Add a final aggregator that depends on all workers
        dynamic_steps.append({
            "name": "aggregator",
            "handler": lambda c: {"total_processed": num_workers},
            "deps": [f"worker_{i}" for i in range(num_workers)]
        })
        
        return {
            "plan_ready": True,
            "__dynamic_steps__": dynamic_steps
        }

    @ao.chain(name="map_reduce")
    class MapReduceChain:
        steps = ["planner"]

    return ao

async def run_dynamic_example():
    print("\n--- Running Dynamic DAG Example ---")
    ao = create_dynamic_chain()
    result = await ao.launch("map_reduce")
    print(f"Chain Success: {result['success']}")
    print(f"Final Aggregator Output: {result['results'][-1]['output']}")

# ═══════════════════════════════════════════════════════════════════════════════
# 2. AUTOMATIC AGENT HANDOFFS
# ═══════════════════════════════════════════════════════════════════════════════

class TriageAgent(Agent):
    async def process_request(self, input_text, user_id, session_id, history, params=None):
        if "finance" in input_text.lower():
            return ConversationMessage(
                role=ParticipantRole.ASSISTANT.value,
                content=[{"text": "I see this is a finance question. Handing you over to our Finance Expert."}],
                handoff_to="finance-agent"
            )
        return ConversationMessage(
            role=ParticipantRole.ASSISTANT.value,
            content=[{"text": "I can help with general questions. How can I assist?"}]
        )

class FinanceAgent(Agent):
    async def process_request(self, input_text, user_id, session_id, history, params=None):
        return ConversationMessage(
            role=ParticipantRole.ASSISTANT.value,
            content=[{"text": "Hello! I am the Finance Expert. I can help with stock analysis and market trends."}]
        )

async def run_handoff_example():
    print("\n--- Running Agent Handoff Example ---")
    orchestrator = MultiAgentOrchestrator()
    
    triage = TriageAgent(AgentOptions(name="Triage Agent", description="Initial contact"))
    finance = FinanceAgent(AgentOptions(name="Finance Agent", description="Finance expert"))
    
    orchestrator.add_agent(triage)
    orchestrator.add_agent(finance)
    orchestrator.set_default_agent(triage)
    
    # User asks a finance question
    response = await orchestrator.route_request(
        "I want to know about finance and stocks",
        user_id="user1",
        session_id="session1"
    )
    
    print(f"Final Response Agent: {response.metadata.agent_name}")
    print(f"Final Response Text: {response.output.get_text()}")

# ═══════════════════════════════════════════════════════════════════════════════
# 3. SHARED SQUAD MEMORY
# ═══════════════════════════════════════════════════════════════════════════════

async def run_shared_memory_example():
    print("\n--- Running Shared Memory Example ---")
    # Using InMemoryChatStorage (which I updated to support shared memory too)
    # Note: In production use RedisChatStorage for true persistence
    storage = InMemoryChatStorage()
    
    user_id = "user123"
    session_id = "session456"
    
    # Agent A updates shared memory
    await storage.update_shared_memory(user_id, session_id, "user_preference", "likes_short_answers")
    print("Agent A set user_preference to 'likes_short_answers'")
    
    # Agent B retrieves shared memory
    shared_mem = await storage.get_shared_memory(user_id, session_id)
    print(f"Agent B retrieved preference: {shared_mem.get('user_preference')}")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_dynamic_example())
    asyncio.run(run_handoff_example())
    asyncio.run(run_shared_memory_example())
