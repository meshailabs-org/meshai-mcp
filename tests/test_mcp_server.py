"""
Tests for MeshAI MCP Server

Tests the Model Context Protocol server implementation for Claude Code integration.
"""

import asyncio
import json
import pytest
from unittest.mock import Mock, patch, AsyncMock, MagicMock
from typing import Dict, Any, List

from meshai_mcp.server import MeshAIMCPServer, MeshAIWorkflow
from meshai_mcp.protocol import (
    Server, Resource, Tool, TextContent, CallToolRequest,
    CallToolResult, GetResourceRequest, MessageType
)


@pytest.fixture
def mcp_server():
    """Create a MeshAI MCP server instance for testing."""
    with patch.dict('os.environ', {
        'MESHAI_API_URL': 'http://test.meshai.dev',
        'MESHAI_API_KEY': 'test-api-key'
    }):
        server = MeshAIMCPServer()
        return server


@pytest.fixture
def mock_httpx_client():
    """Mock httpx AsyncClient for API calls."""
    with patch('meshai_mcp.server.httpx.AsyncClient') as mock:
        client = AsyncMock()
        mock.return_value.__aenter__.return_value = client
        yield client


class TestMeshAIMCPServer:
    """Test MeshAI MCP Server functionality."""
    
    def test_server_initialization(self, mcp_server):
        """Test that the MCP server initializes correctly."""
        assert mcp_server.mesh_endpoint == "http://test.meshai.dev"
        assert mcp_server.api_key == "test-api-key"
        assert len(mcp_server.workflows) == 6
        assert "code-review" in mcp_server.workflows
        assert "feature-development" in mcp_server.workflows
    
    def test_workflow_definitions(self, mcp_server):
        """Test workflow definitions are properly structured."""
        code_review = mcp_server.workflows["code-review"]
        assert isinstance(code_review, MeshAIWorkflow)
        assert code_review.name == "code-review"
        assert len(code_review.agents) == 3
        assert "code-reviewer" in code_review.agents
        assert "security-analyzer" in code_review.agents
        assert code_review.parameters is not None
        assert "files" in code_review.parameters
    
    @pytest.mark.asyncio
    async def test_list_resources(self, mcp_server):
        """Test listing available resources."""
        # Get the list_resources handler
        handler = mcp_server.server.handlers.get("list_resources")
        assert handler is not None
        
        resources = await handler()
        assert isinstance(resources, list)
        assert len(resources) > 0
        
        # Check workflow resources
        workflow_resources = [r for r in resources if "workflow" in r.uri]
        assert len(workflow_resources) == 6
        
        # Check agent registry resource
        registry_resources = [r for r in resources if "registry" in r.uri]
        assert len(registry_resources) == 1
        assert registry_resources[0].uri == "meshai://agents/registry"
    
    @pytest.mark.asyncio
    async def test_get_workflow_resource(self, mcp_server):
        """Test getting a specific workflow resource."""
        handler = mcp_server.server.handlers.get("get_resource")
        assert handler is not None
        
        request = GetResourceRequest(uri="meshai://workflow/code-review")
        content = await handler(request)
        
        assert isinstance(content, str)
        workflow_data = json.loads(content)
        assert workflow_data["name"] == "code-review"
        assert len(workflow_data["agents"]) == 3
    
    @pytest.mark.asyncio
    async def test_list_tools(self, mcp_server):
        """Test listing available tools."""
        handler = mcp_server.server.handlers.get("list_tools")
        assert handler is not None
        
        tools = await handler()
        assert isinstance(tools, list)
        
        # Check main execution tool
        mesh_execute = next((t for t in tools if t.name == "mesh_execute"), None)
        assert mesh_execute is not None
        assert "task" in mesh_execute.inputSchema["properties"]
        assert "workflow" in mesh_execute.inputSchema["properties"]
        
        # Check workflow-specific tools
        workflow_tools = [t for t in tools if t.name.startswith("mesh_") and t.name != "mesh_execute" and t.name != "mesh_discover_agents"]
        assert len(workflow_tools) == 6
        
        # Check agent discovery tool
        discover_tool = next((t for t in tools if t.name == "mesh_discover_agents"), None)
        assert discover_tool is not None
    
    @pytest.mark.asyncio
    async def test_execute_multi_agent_task(self, mcp_server, mock_httpx_client):
        """Test executing a multi-agent task."""
        # Mock API response
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "agent_results": {
                "code-reviewer": {"result": "Code looks good"},
                "security-analyzer": {"result": "No security issues found"}
            },
            "summary": "Task completed successfully"
        }
        mock_httpx_client.post.return_value = mock_response
        
        # Execute task
        result = await mcp_server._execute_multi_agent_task(
            task="Review this code for security issues",
            workflow="code-review",
            context={"file_path": "test.py"}
        )
        
        assert "agent_results" in result
        assert "code-reviewer" in result["agent_results"]
        assert mock_httpx_client.post.called
        
        # Check API call parameters
        call_args = mock_httpx_client.post.call_args
        assert call_args[0][0] == "http://test.meshai.dev/multi-agent/execute"
        payload = call_args[1]["json"]
        assert payload["task"] == "Review this code for security issues"
        assert payload["agents"] == ["code-reviewer", "security-analyzer", "best-practices-advisor"]
    
    @pytest.mark.asyncio
    async def test_auto_select_agents(self, mcp_server):
        """Test automatic agent selection based on task content."""
        # Test review keywords
        agents = await mcp_server._auto_select_agents("Please review this code")
        assert "code-reviewer" in agents
        
        # Test security keywords
        agents = await mcp_server._auto_select_agents("Check for security vulnerabilities")
        assert "security-analyzer" in agents
        
        # Test performance keywords
        agents = await mcp_server._auto_select_agents("Optimize this function for better performance")
        assert "performance-optimizer" in agents
        
        # Test documentation keywords
        agents = await mcp_server._auto_select_agents("Generate documentation for this module")
        assert "doc-writer" in agents
        
        # Test multiple keywords
        agents = await mcp_server._auto_select_agents("Review code and check security")
        assert "code-reviewer" in agents
        assert "security-analyzer" in agents
        
        # Test default fallback
        agents = await mcp_server._auto_select_agents("Random task with no keywords")
        assert "code-reviewer" in agents  # Default fallback
    
    @pytest.mark.asyncio
    async def test_call_tool_mesh_execute(self, mcp_server, mock_httpx_client):
        """Test calling the mesh_execute tool."""
        # Mock API response
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "agent_results": {
                "code-reviewer": {"result": "Review complete"}
            }
        }
        mock_httpx_client.post.return_value = mock_response
        
        # Prepare tool call request
        handler = mcp_server.server.handlers.get("call_tool")
        assert handler is not None
        
        request = CallToolRequest(
            id="test-123",
            params=MagicMock()
        )
        request.params.name = "mesh_execute"
        request.params.arguments = {
            "task": "Review this code",
            "workflow": "code-review"
        }
        
        result = await handler(request)
        assert isinstance(result, CallToolResult)
        assert len(result.content) > 0
        assert isinstance(result.content[0], TextContent)
    
    @pytest.mark.asyncio
    async def test_discover_agents(self, mcp_server, mock_httpx_client):
        """Test agent discovery functionality."""
        # Mock API response
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "agents": [
                {"id": "agent-1", "name": "Code Reviewer", "capabilities": ["review"]},
                {"id": "agent-2", "name": "Test Generator", "capabilities": ["testing"]}
            ]
        }
        mock_httpx_client.get.return_value = mock_response
        
        result = await mcp_server._discover_agents(capability="review")
        
        assert "agents" in result
        assert len(result["agents"]) == 2
        assert mock_httpx_client.get.called
        
        # Check API call
        call_args = mock_httpx_client.get.call_args
        assert call_args[0][0] == "http://test.meshai.dev/agents"
        assert call_args[1]["params"]["capability"] == "review"
    
    def test_format_result_for_claude_code(self, mcp_server):
        """Test formatting results for Claude Code display."""
        # Test successful result
        result = {
            "agent_results": {
                "code-reviewer": {
                    "result": "Code is clean",
                    "recommendations": ["Add more comments", "Improve error handling"]
                },
                "security-analyzer": {
                    "result": "No vulnerabilities found"
                }
            },
            "summary": "All checks passed"
        }
        
        formatted = mcp_server._format_result_for_claude_code(result)
        assert "Multi-Agent Task Results" in formatted
        assert "Code Reviewer" in formatted
        assert "Security Analyzer" in formatted
        assert "Add more comments" in formatted
        assert "All checks passed" in formatted
        
        # Test error result
        error_result = {"error": "API connection failed"}
        formatted = mcp_server._format_result_for_claude_code(error_result)
        assert "❌ Error" in formatted
        assert "API connection failed" in formatted


class TestMCPProtocolFallback:
    """Test the fallback MCP protocol implementation."""
    
    @pytest.mark.asyncio
    async def test_server_initialization(self):
        """Test fallback server initialization."""
        server = Server("test-server")
        assert server.name == "test-server"
        assert len(server.handlers) == 0
        assert not server._running
    
    @pytest.mark.asyncio
    async def test_message_handling(self):
        """Test message handling in fallback server."""
        server = Server("test-server")
        
        # Register a mock handler
        mock_handler = AsyncMock(return_value=[
            Resource(uri="test://resource", name="Test", description="Test resource")
        ])
        server.handlers["list_resources"] = mock_handler
        
        # Test handling list_resources request
        message = {
            "type": MessageType.REQUEST,
            "method": "list_resources",
            "id": "msg-123",
            "params": {}
        }
        
        response = await server.handle_message(message)
        
        assert response is not None
        assert response["type"] == MessageType.RESPONSE
        assert response["id"] == "msg-123"
        assert "result" in response
        assert "resources" in response["result"]
        assert len(response["result"]["resources"]) == 1
    
    @pytest.mark.asyncio
    async def test_error_handling(self):
        """Test error handling in fallback server."""
        server = Server("test-server")
        
        # Test unknown method
        message = {
            "type": MessageType.REQUEST,
            "method": "unknown_method",
            "id": "msg-456",
            "params": {}
        }
        
        response = await server.handle_message(message)
        
        assert response is not None
        assert "error" in response
        assert response["error"]["code"] == -32601
        assert "Method not found" in response["error"]["message"]
    
    @pytest.mark.asyncio
    async def test_tool_call_handling(self):
        """Test tool call handling in fallback server."""
        server = Server("test-server")
        
        # Register mock tool handler
        mock_handler = AsyncMock(return_value=CallToolResult(
            content=[TextContent(type="text", text="Tool executed successfully")]
        ))
        server.handlers["call_tool"] = mock_handler
        
        message = {
            "type": MessageType.REQUEST,
            "method": "call_tool",
            "id": "tool-789",
            "params": {
                "name": "test_tool",
                "arguments": {"param1": "value1"}
            }
        }
        
        response = await server.handle_message(message)
        
        assert response is not None
        assert response["type"] == MessageType.RESPONSE
        assert "result" in response
        assert "content" in response["result"]
        assert len(response["result"]["content"]) == 1
        assert response["result"]["content"][0]["type"] == "text"


@pytest.mark.asyncio
async def test_main_entry_point():
    """Test the main entry point for the MCP server."""
    with patch('meshai_mcp.server.MeshAIMCPServer') as MockServer:
        mock_instance = AsyncMock()
        MockServer.return_value = mock_instance
        
        from meshai_mcp.server import main
        
        # Run main with mocked serve
        with patch.object(mock_instance, 'serve', new_callable=AsyncMock) as mock_serve:
            await main()
            
            MockServer.assert_called_once()
            mock_serve.assert_called_once()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])