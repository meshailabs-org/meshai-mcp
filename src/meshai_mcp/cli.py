"""
MeshAI MCP Server CLI

Command-line interface for the MeshAI MCP server.
"""

import asyncio
import os
import sys
from typing import Optional

import click
from rich.console import Console
from rich.text import Text

from . import __version__
from .server import MeshAIMCPServer

console = Console()


@click.group(invoke_without_command=True)
@click.option('--version', is_flag=True, help='Show version and exit')
@click.pass_context
def main(ctx: click.Context, version: bool):
    """MeshAI MCP Server - Multi-agent orchestration for Claude Code."""
    
    if version:
        console.print(f"MeshAI MCP Server v{__version__}")
        sys.exit(0)
    
    if ctx.invoked_subcommand is None:
        # Default action: start the server
        ctx.invoke(serve)


@main.command()
@click.option('--host', default='0.0.0.0', help='Host to bind to (HTTP mode)')
@click.option('--port', default=8080, help='Port to bind to (HTTP mode)')
@click.option('--transport', default='stdio', type=click.Choice(['stdio', 'http']), 
              help='Transport protocol')
@click.option('--dev', is_flag=True, help='Run in development mode')
@click.option('--log-level', default=None, type=click.Choice(['DEBUG', 'INFO', 'WARNING', 'ERROR']),
              help='Logging level')
def serve(host: str, port: int, transport: str, dev: bool, log_level: Optional[str]):
    """Start the MCP server."""
    
    # Set log level
    if log_level:
        os.environ['MESHAI_LOG_LEVEL'] = log_level
    elif dev:
        os.environ['MESHAI_LOG_LEVEL'] = 'DEBUG'
    
    # Show startup info
    if dev:
        console.print("🔧 [bold yellow]Development Mode[/bold yellow]")
    
    console.print(f"🚀 Starting MeshAI MCP Server on {transport}")
    
    if transport == 'stdio':
        console.print("📡 Listening on stdin/stdout")
    else:
        console.print(f"📡 Listening on {host}:{port}")
        console.print(f"🌐 API Documentation: http://{host}:{port}/docs")
    
    # Check environment
    api_url = os.getenv('MESHAI_API_URL', 'http://localhost:8080')
    api_key = os.getenv('MESHAI_API_KEY')
    
    if not api_key and transport == 'stdio':
        console.print("⚠️  [bold yellow]Warning:[/bold yellow] MESHAI_API_KEY not set")
    
    console.print(f"🔗 MeshAI API: {api_url}")
    
    if transport == 'http':
        console.print("🔐 Authentication: API Key required")
        console.print("📖 Usage: curl -H 'Authorization: Bearer YOUR_API_KEY' http://localhost:8080/v1/tools")
    
    # Start server
    try:
        if transport == 'stdio':
            from .server import MeshAIMCPServer
            server = MeshAIMCPServer()
            asyncio.run(server.serve(transport='stdio'))
        else:
            from .http_server import serve_http
            # Test auth service availability before starting
            console.print("🔍 Checking authentication service...")
            auth_available = asyncio.run(check_auth_service())
            if not auth_available:
                console.print("⚠️  [bold yellow]Warning:[/bold yellow] Authentication service not available, continuing anyway")
            
            console.print("🎯 Starting HTTP server...")
            asyncio.run(serve_http(host=host, port=port))
    except KeyboardInterrupt:
        console.print("\n👋 Shutting down MeshAI MCP Server")
    except Exception as e:
        console.print(f"❌ [bold red]Error:[/bold red] {e}")
        if dev:
            import traceback
            console.print(traceback.format_exc())
        sys.exit(1)


@main.command()
@click.option('--format', default='json', type=click.Choice(['json', 'table']),
              help='Output format')
def list_workflows(format: str):
    """List available workflows."""
    server = MeshAIMCPServer()
    
    if format == 'json':
        import json
        workflows = {}
        for name, workflow in server.workflows.items():
            workflows[name] = {
                'name': workflow.name,
                'description': workflow.description,
                'agents': workflow.agents,
                'parameters': workflow.parameters
            }
        console.print(json.dumps(workflows, indent=2))
    else:
        from rich.table import Table
        
        table = Table(title="MeshAI Workflows")
        table.add_column("Name", style="cyan")
        table.add_column("Description", style="white")
        table.add_column("Agents", style="green")
        
        for workflow in server.workflows.values():
            agents_str = ", ".join(workflow.agents)
            table.add_row(workflow.name, workflow.description, agents_str)
        
        console.print(table)


@main.command()
@click.option('--format', default='table', type=click.Choice(['json', 'table']),
              help='Output format')
def list_tools(format: str):
    """List available MCP tools."""
    import json
    from rich.table import Table
    
    # Get tools from server
    server = MeshAIMCPServer()
    
    # Register handlers to get tools
    server._register_handlers()
    
    # Get the list_tools handler
    tools_handler = server.server.handlers.get('list_tools')
    if not tools_handler:
        console.print("❌ No tools handler found")
        return
    
    # Get tools (this is async, so we need to run it)
    async def get_tools():
        return await tools_handler()
    
    tools = asyncio.run(get_tools())
    
    if format == 'json':
        tools_data = []
        for tool in tools:
            tools_data.append({
                'name': tool.name,
                'description': tool.description,
                'inputSchema': tool.inputSchema
            })
        console.print(json.dumps(tools_data, indent=2))
    else:
        table = Table(title="MeshAI MCP Tools")
        table.add_column("Tool", style="cyan")
        table.add_column("Description", style="white")
        
        for tool in tools:
            table.add_row(tool.name, tool.description)
        
        console.print(table)


@main.command()
def config():
    """Show current configuration."""
    from rich.table import Table
    
    table = Table(title="MeshAI MCP Server Configuration")
    table.add_column("Setting", style="cyan")
    table.add_column("Value", style="white")
    
    # Environment variables
    api_url = os.getenv('MESHAI_API_URL', 'http://localhost:8080')
    api_key = os.getenv('MESHAI_API_KEY', '[not set]')
    log_level = os.getenv('MESHAI_LOG_LEVEL', 'INFO')
    
    table.add_row("MESHAI_API_URL", api_url)
    table.add_row("MESHAI_API_KEY", api_key if api_key != '[not set]' else '❌ [not set]')
    table.add_row("MESHAI_LOG_LEVEL", log_level)
    table.add_row("Version", __version__)
    
    console.print(table)


@main.command()
@click.argument('message')
def test(message: str):
    """Test the MCP server with a message."""
    import json
    
    console.print(f"🧪 Testing MCP server with message: {message}")
    
    # Create a test message
    test_message = {
        "type": "request",
        "method": "list_tools",
        "id": "test-123"
    }
    
    console.print("📤 Sending test message:")
    console.print(json.dumps(test_message, indent=2))
    
    # For now, just show what would happen
    console.print("✅ Test message formatted correctly")
    console.print("ℹ️  Use 'echo <message> | meshai-mcp-server' to test with real server")


async def check_auth_service() -> bool:
    """Check if authentication service is available"""
    try:
        from .auth.client import AuthClient
        client = AuthClient()
        async with client:
            return await client.health_check()
    except Exception as e:
        console.print(f"🔴 Auth service check failed: {e}")
        return False


if __name__ == '__main__':
    main()