"""
MeshAI MCP Server

Model Context Protocol server for integrating MeshAI multi-agent orchestration
with Claude Code and other MCP-compatible tools.
"""

__version__ = "0.1.0"
__author__ = "MeshAI Labs"
__email__ = "dev@meshai.dev"

from .server import MeshAIMCPServer
from .protocol import Server, Resource, Tool, TextContent, ImageContent

__all__ = [
    "MeshAIMCPServer",
    "Server", 
    "Resource",
    "Tool",
    "TextContent", 
    "ImageContent"
]