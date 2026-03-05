"""Basic tests for MCP client module.

Run with: python -m pytest agentorchestrator/utils/test_mcp_client_basic.py -v
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from agentorchestrator.utils.mcp_client import (
    create_bearer_token,
    parse_sse_response,
    MCPSession,
)


def test_create_bearer_token():
    """Test JWT bearer token creation."""
    token = create_bearer_token(
        email="test@example.com",
        name="Test User",
        preferred_username="testuser",
        server_secret="secret123",
    )
    
    # Token should be a base64-encoded string
    assert isinstance(token, str)
    assert len(token) > 0
    
    # Should be decodable
    import base64
    decoded = base64.b64decode(token)
    assert b"server_secret" in decoded
    assert b"user_id_token" in decoded


def test_parse_sse_response():
    """Test SSE response parsing."""
    # Test valid SSE response
    sse_text = 'data: {"result": {"tools": [{"name": "test"}]}}\n\n'
    result = parse_sse_response(sse_text)
    
    assert isinstance(result, dict)
    assert "result" in result
    assert "tools" in result["result"]
    assert result["result"]["tools"][0]["name"] == "test"
    
    # Test empty response
    empty_result = parse_sse_response("")
    assert empty_result == {}
    
    # Test multi-line data
    multi_line = 'data: {"result":\ndata: {"value": 123}}\n\n'
    multi_result = parse_sse_response(multi_line)
    assert "result" in multi_result


@pytest.mark.asyncio
async def test_bearer_token_caching():
    """Test that bearer tokens are cached properly."""
    from agentorchestrator.utils import mcp_client
    
    # Reset cache
    mcp_client._bearer_token = None
    mcp_client._bearer_token_expires = None
    mcp_client._bearer_token_secret = None
    
    with patch.dict('os.environ', {
        'MCP_USER_EMAIL': 'test@example.com',
        'MCP_SECRET': 'secret123'
    }):
        # First call should generate token
        token1 = await mcp_client.get_bearer_token_async()
        assert token1 is not None
        
        # Second call should return cached token
        token2 = await mcp_client.get_bearer_token_async()
        assert token1 == token2
        
        # Force refresh should generate new token
        token3 = await mcp_client.get_bearer_token_async(force_refresh=True)
        assert token3 is not None


@pytest.mark.asyncio
async def test_mcp_session_context_manager():
    """Test MCPSession context manager lifecycle."""
    with patch('agentorchestrator.utils.mcp_client.initialize_mcp_session') as mock_init:
        # Mock the initialization
        mock_client = AsyncMock()
        mock_init.return_value = ("session-123", mock_client)
        
        # Test context manager
        async with MCPSession(
            endpoint="http://test.example.com",
            client_secret="secret123"
        ) as session:
            assert session.session_id == "session-123"
            assert session.client == mock_client
        
        # Client should be closed after context exit
        mock_client.aclose.assert_called_once()


@pytest.mark.asyncio
async def test_mcp_session_missing_config():
    """Test MCPSession raises error when configuration is missing."""
    with patch.dict('os.environ', {}, clear=True):
        with pytest.raises(ValueError, match="MCP server URL not configured"):
            async with MCPSession() as session:
                pass


def test_token_generation_validation():
    """Test that token generation validates required fields."""
    from agentorchestrator.utils import mcp_client
    
    # Reset cache
    mcp_client._bearer_token = None
    
    with patch.dict('os.environ', {}, clear=True):
        # Missing email should raise error
        with pytest.raises(ValueError, match="User email not configured"):
            import asyncio
            asyncio.run(mcp_client.get_bearer_token_async())


if __name__ == "__main__":
    pytest.main([__file__, "-v"])