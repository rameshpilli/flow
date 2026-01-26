import asyncio
import os
from agentorchestrator.services.llm_gateway import LLMGatewayClient

async def test_tiktoken_support():
    """
    Test script to verify if tiktoken is supported and used for token estimation.
    """
    client = LLMGatewayClient(
        server_url="http://localhost:8080", # Doesn't need to be real for this test
        model_name="gpt-4"
    )
    
    test_text = "Hello, world! This is a test of the tiktoken tokenizer integration."
    
    # Heuristic estimation (len // 4) would be roughly 68 // 4 = 17
    # tiktoken estimation for cl100k_base should be around 15
    
    tokens = client._estimate_tokens(test_text)
    print(f"Estimated tokens for text: '{test_text}'")
    print(f"Token count: {tokens}")
    
    # Check if tiktoken is actually installed and used
    try:
        import tiktoken
        print("SUCCESS: tiktoken is installed and being used.")
    except ImportError:
        print("WARNING: tiktoken not installed, falling back to heuristic (len // 4).")

if __name__ == "__main__":
    asyncio.run(test_tiktoken_support())
