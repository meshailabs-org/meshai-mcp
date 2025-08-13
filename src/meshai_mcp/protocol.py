"""
Fallback MCP Protocol Implementation for MeshAI

This module provides a minimal MCP protocol implementation for when 
the official MCP package is not available. It allows the MeshAI MCP 
server to function with basic stdio transport.
"""

import json
import sys
import asyncio
from typing import Dict, List, Any, Optional, Callable
from dataclasses import dataclass, asdict
from enum import Enum
import structlog

logger = structlog.get_logger(__name__)


class MessageType(str, Enum):
    """MCP message types"""
    REQUEST = "request"
    RESPONSE = "response"
    NOTIFICATION = "notification"
    ERROR = "error"


@dataclass
class Resource:
    """MCP Resource definition"""
    uri: str
    name: str
    description: str
    mimeType: str = "application/json"


@dataclass
class Tool:
    """MCP Tool definition"""
    name: str
    description: str
    inputSchema: Dict[str, Any]


@dataclass
class TextContent:
    """Text content for tool results"""
    type: str = "text"
    text: str = ""


@dataclass
class ImageContent:
    """Image content for tool results"""
    type: str = "image"
    data: str = ""  # Base64 encoded
    mimeType: str = "image/png"


@dataclass
class CallToolRequest:
    """Tool call request"""
    id: str
    params: Any


@dataclass
class CallToolResult:
    """Tool call result"""
    content: List[Any]


@dataclass
class GetResourceRequest:
    """Resource request"""
    uri: str


@dataclass
class ListResourcesRequest:
    """List resources request"""
    pass


@dataclass  
class ListToolsRequest:
    """List tools request"""
    pass


class Server:
    """
    Minimal MCP Server implementation for stdio transport.
    
    This provides a basic implementation compatible with Claude Code's
    MCP protocol over stdio (standard input/output).
    """
    
    def __init__(self, name: str):
        self.name = name
        self.resources: List[Resource] = []
        self.tools: List[Tool] = []
        self.handlers: Dict[str, Callable] = {}
        self._running = False
        
    def list_resources(self):
        """Decorator for list resources handler"""
        def decorator(func):
            self.handlers["list_resources"] = func
            return func
        return decorator
    
    def get_resource(self):
        """Decorator for get resource handler"""
        def decorator(func):
            self.handlers["get_resource"] = func
            return func
        return decorator
    
    def list_tools(self):
        """Decorator for list tools handler"""
        def decorator(func):
            self.handlers["list_tools"] = func
            return func
        return decorator
    
    def call_tool(self):
        """Decorator for call tool handler"""
        def decorator(func):
            self.handlers["call_tool"] = func
            return func
        return decorator
    
    async def handle_message(self, message: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Handle incoming MCP message"""
        try:
            msg_type = message.get("type")
            method = message.get("method")
            msg_id = message.get("id")
            params = message.get("params", {})
            
            if msg_type != MessageType.REQUEST:
                return None
            
            result = None
            error = None
            
            # Route to appropriate handler
            if method == "list_resources":
                handler = self.handlers.get("list_resources")
                if handler:
                    resources = await handler()
                    result = {
                        "resources": [asdict(r) for r in resources]
                    }
            
            elif method == "get_resource":
                handler = self.handlers.get("get_resource")
                if handler:
                    request = GetResourceRequest(uri=params.get("uri"))
                    content = await handler(request)
                    result = {"content": content}
            
            elif method == "list_tools":
                handler = self.handlers.get("list_tools")
                if handler:
                    tools = await handler()
                    result = {
                        "tools": [asdict(t) for t in tools]
                    }
            
            elif method == "call_tool":
                handler = self.handlers.get("call_tool")
                if handler:
                    request = CallToolRequest(
                        id=msg_id,
                        params=type('Params', (), params)()
                    )
                    # Set params attributes
                    for k, v in params.items():
                        setattr(request.params, k, v)
                    
                    tool_result = await handler(request)
                    
                    # Convert result content
                    content = []
                    for item in tool_result.content:
                        if isinstance(item, TextContent):
                            content.append({"type": "text", "text": item.text})
                        elif isinstance(item, ImageContent):
                            content.append({
                                "type": "image",
                                "data": item.data,
                                "mimeType": item.mimeType
                            })
                        else:
                            content.append(item)
                    
                    result = {"content": content}
            
            else:
                error = {"code": -32601, "message": f"Method not found: {method}"}
            
            # Build response
            response = {
                "type": MessageType.RESPONSE,
                "id": msg_id
            }
            
            if error:
                response["error"] = error
            else:
                response["result"] = result
            
            return response
            
        except Exception as e:
            logger.error(f"Error handling message: {e}")
            return {
                "type": MessageType.RESPONSE,
                "id": message.get("id"),
                "error": {
                    "code": -32603,
                    "message": f"Internal error: {str(e)}"
                }
            }
    
    async def run(self):
        """Run the MCP server over stdio"""
        self._running = True
        logger.info(f"Starting MCP server '{self.name}' over stdio")
        
        # Send initialization message
        init_msg = {
            "type": MessageType.NOTIFICATION,
            "method": "initialized",
            "params": {
                "name": self.name,
                "version": "0.1.0"
            }
        }
        self._write_message(init_msg)
        
        # Main message loop
        while self._running:
            try:
                # Read from stdin
                line = await asyncio.get_event_loop().run_in_executor(
                    None, sys.stdin.readline
                )
                
                if not line:
                    break
                
                line = line.strip()
                if not line:
                    continue
                
                # Parse JSON message
                try:
                    message = json.loads(line)
                except json.JSONDecodeError:
                    logger.error(f"Invalid JSON message: {line}")
                    continue
                
                # Handle message
                response = await self.handle_message(message)
                if response:
                    self._write_message(response)
                    
            except KeyboardInterrupt:
                break
            except Exception as e:
                logger.error(f"Error in message loop: {e}")
        
        logger.info("MCP server stopped")
    
    def _write_message(self, message: Dict[str, Any]):
        """Write message to stdout"""
        try:
            json_str = json.dumps(message)
            sys.stdout.write(json_str + "\n")
            sys.stdout.flush()
        except Exception as e:
            logger.error(f"Error writing message: {e}")


async def stdio_server(server: Server):
    """Run MCP server over stdio transport"""
    await server.run()