"""
CMPT Agent Tests

Simple test suite using the @testable decorator.
"""

import asyncio
import logging
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from cmpt/.env
cmpt_dir = Path(__file__).parent.parent
env_file = cmpt_dir / ".env"
if env_file.exists():
    load_dotenv(env_file)
    print(f"Loaded .env from: {env_file}")
else:
    print(f"Warning: .env not found at {env_file}")

workflows_dir = Path(__file__).parent.parent.parent
sys.path.insert(0, str(workflows_dir))

from agentorchestrator import AgentOrchestrator

# Import directly from the agents module to avoid __init__.py chain imports
import importlib.util
agents_path = Path(__file__).parent.parent / "services" / "agents.py"
spec = importlib.util.spec_from_file_location("cmpt_agents", agents_path)
cmpt_agents = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cmpt_agents)

register_cmpt_agents = cmpt_agents.register_cmpt_agents

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)

logger = logging.getLogger(__name__)


async def test_cmpt_agents():
    """Test all CMPT agents."""
    ao = AgentOrchestrator(name="cmpt_test")
    
    register_cmpt_agents(ao)
    
    success = await register_cmpt_agents.test(ao, verbose=True)
    
    return 0 if success else 1


if __name__ == "__main__":
    exit_code = asyncio.run(test_cmpt_agents())
    exit(exit_code)