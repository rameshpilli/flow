
import asyncio
import logging
from agentorchestrator import AgentOrchestrator

# Configure logging to show our warning
logging.basicConfig(level=logging.WARNING)

async def trigger_warning():
    print("\n--- Starting Async Test ---")
    try:
        # This should trigger the warning because we are inside a running loop
        # but using the synchronous context manager.
        with AgentOrchestrator(name="test_sync_in_async") as ao:
            print("Inside synchronous context manager")
            # Just do something simple
            @ao.step
            async def noop(ctx):
                pass
            
            await ao.launch_resumable("noop_chain", {}, run_id="test")
            
    except Exception as e:
        print(f"Caught expected exception (if any): {e}")

    print("--- Finished Async Test ---\n")

if __name__ == "__main__":
    asyncio.run(trigger_warning())
