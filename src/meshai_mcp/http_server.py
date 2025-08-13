"""
HTTP Transport for MeshAI MCP Server

Provides HTTP/REST API endpoints for MCP protocol communication.
"""

import asyncio
import json
import os
from typing import Dict, Any, Optional
from datetime import datetime, timedelta

from fastapi import FastAPI, HTTPException, Depends, Request, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.responses import JSONResponse
import httpx
import structlog
from pydantic import BaseModel

from .server import MeshAIMCPServer
from .protocol import MessageType

logger = structlog.get_logger(__name__)

# Authentication
security = HTTPBearer()

# Rate limiting storage (in production, use Redis)
rate_limit_storage: Dict[str, Dict[str, Any]] = {}

class MCPRequest(BaseModel):
    """HTTP request body for MCP calls"""
    type: str = MessageType.REQUEST
    method: str
    id: str
    params: Optional[Dict[str, Any]] = None

class MCPResponse(BaseModel):
    """HTTP response body for MCP calls"""
    type: str
    id: str
    result: Optional[Dict[str, Any]] = None
    error: Optional[Dict[str, Any]] = None

class AuthError(Exception):
    """Authentication error"""
    pass

class RateLimitError(Exception):
    """Rate limit exceeded error"""
    pass


async def validate_api_key(token: str) -> Optional[Dict[str, Any]]:
    """
    Validate API key against MeshAI API.
    
    In production, this should call the actual MeshAI user service.
    For now, we'll implement a simple validation.
    """
    
    # Check for development/test tokens
    if token.startswith('dev_') or token.startswith('test_'):
        return {
            "user_id": "dev-user",
            "plan": "development",
            "rate_limit": 1000  # requests per hour
        }
    
    # Validate against MeshAI API
    meshai_api_url = os.getenv('MESHAI_API_URL', 'http://localhost:8080')
    
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(
                f"{meshai_api_url}/auth/validate",
                headers={"Authorization": f"Bearer {token}"}
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                logger.warning(f"API key validation failed: {response.status_code}")
                return None
                
    except Exception as e:
        logger.error(f"Failed to validate API key: {e}")
        return None


def check_rate_limit(user_id: str, rate_limit: int = 100) -> bool:
    """
    Check if user has exceeded rate limit.
    
    Args:
        user_id: User identifier
        rate_limit: Requests per hour limit
        
    Returns:
        True if within limit, False if exceeded
    """
    
    now = datetime.utcnow()
    hour_key = now.strftime("%Y-%m-%d-%H")
    
    if user_id not in rate_limit_storage:
        rate_limit_storage[user_id] = {}
    
    user_storage = rate_limit_storage[user_id]
    
    # Clean old entries (keep last 2 hours)
    cutoff = now - timedelta(hours=2)
    to_remove = [
        key for key in user_storage.keys() 
        if datetime.strptime(key, "%Y-%m-%d-%H") < cutoff
    ]
    for key in to_remove:
        del user_storage[key]
    
    # Check current hour usage
    current_usage = user_storage.get(hour_key, 0)
    
    if current_usage >= rate_limit:
        return False
    
    # Increment usage
    user_storage[hour_key] = current_usage + 1
    return True


async def authenticate_request(credentials: HTTPAuthorizationCredentials = Depends(security)) -> Dict[str, Any]:
    """
    Authenticate HTTP request using API key.
    
    Returns:
        User information dictionary
        
    Raises:
        AuthError: If authentication fails
        RateLimitError: If rate limit exceeded
    """
    
    if not credentials:
        raise AuthError("Missing authorization header")
    
    token = credentials.credentials
    user = await validate_api_key(token)
    
    if not user:
        raise AuthError("Invalid API key")
    
    # Check rate limiting
    rate_limit = user.get('rate_limit', 100)
    if not check_rate_limit(user['user_id'], rate_limit):
        raise RateLimitError(f"Rate limit exceeded: {rate_limit} requests/hour")
    
    return user


def create_http_app() -> FastAPI:
    """Create FastAPI application for MCP HTTP transport."""
    
    app = FastAPI(
        title="MeshAI MCP Server",
        description="HTTP API for MeshAI Multi-Agent Orchestration via MCP",
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc"
    )
    
    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Configure appropriately for production
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # Initialize MCP server
    mcp_server = MeshAIMCPServer()
    
    @app.exception_handler(AuthError)
    async def auth_error_handler(request: Request, exc: AuthError):
        return JSONResponse(
            status_code=401,
            content={"error": "Authentication failed", "detail": str(exc)}
        )
    
    @app.exception_handler(RateLimitError)
    async def rate_limit_error_handler(request: Request, exc: RateLimitError):
        return JSONResponse(
            status_code=429,
            content={"error": "Rate limit exceeded", "detail": str(exc)}
        )
    
    @app.get("/health")
    async def health_check():
        """Health check endpoint."""
        return {
            "status": "healthy",
            "service": "meshai-mcp-server",
            "timestamp": datetime.utcnow().isoformat()
        }
    
    @app.get("/")
    async def root():
        """Root endpoint with API information."""
        return {
            "service": "MeshAI MCP Server",
            "version": "0.1.0",
            "transport": "http",
            "endpoints": {
                "mcp": "/v1/mcp",
                "health": "/health",
                "docs": "/docs"
            }
        }
    
    @app.post("/v1/mcp", response_model=MCPResponse)
    async def handle_mcp_request(
        request: MCPRequest,
        user: Dict[str, Any] = Depends(authenticate_request)
    ) -> MCPResponse:
        """
        Handle MCP protocol requests over HTTP.
        
        This endpoint accepts MCP requests and routes them to the appropriate handlers.
        """
        
        logger.info(f"MCP request from user {user['user_id']}: {request.method}")
        
        try:
            # Convert HTTP request to MCP message format
            mcp_message = {
                "type": request.type,
                "method": request.method,
                "id": request.id,
                "params": request.params or {}
            }
            
            # Add user context to the request
            mcp_message["params"]["_user"] = user
            
            # Handle the message using the MCP server
            response = await mcp_server.server.handle_message(mcp_message)
            
            if response:
                return MCPResponse(
                    type=response["type"],
                    id=response["id"],
                    result=response.get("result"),
                    error=response.get("error")
                )
            else:
                # No response expected (notification)
                return MCPResponse(
                    type=MessageType.RESPONSE,
                    id=request.id,
                    result={"status": "accepted"}
                )
                
        except Exception as e:
            logger.error(f"Error handling MCP request: {e}")
            return MCPResponse(
                type=MessageType.RESPONSE,
                id=request.id,
                error={
                    "code": -32603,
                    "message": f"Internal error: {str(e)}"
                }
            )
    
    @app.get("/v1/tools")
    async def list_tools(user: Dict[str, Any] = Depends(authenticate_request)):
        """List available MCP tools."""
        
        try:
            # Get tools using the MCP server
            handler = mcp_server.server.handlers.get("list_tools")
            if not handler:
                raise HTTPException(status_code=500, detail="Tools handler not available")
            
            tools = await handler()
            
            return {
                "tools": [
                    {
                        "name": tool.name,
                        "description": tool.description,
                        "inputSchema": tool.inputSchema
                    }
                    for tool in tools
                ]
            }
            
        except Exception as e:
            logger.error(f"Error listing tools: {e}")
            raise HTTPException(status_code=500, detail=str(e))
    
    @app.get("/v1/resources")
    async def list_resources(user: Dict[str, Any] = Depends(authenticate_request)):
        """List available MCP resources."""
        
        try:
            # Get resources using the MCP server
            handler = mcp_server.server.handlers.get("list_resources")
            if not handler:
                raise HTTPException(status_code=500, detail="Resources handler not available")
            
            resources = await handler()
            
            return {
                "resources": [
                    {
                        "uri": resource.uri,
                        "name": resource.name,
                        "description": resource.description,
                        "mimeType": resource.mimeType
                    }
                    for resource in resources
                ]
            }
            
        except Exception as e:
            logger.error(f"Error listing resources: {e}")
            raise HTTPException(status_code=500, detail=str(e))
    
    @app.get("/v1/workflows")
    async def list_workflows(user: Dict[str, Any] = Depends(authenticate_request)):
        """List available MeshAI workflows."""
        
        workflows = []
        for name, workflow in mcp_server.workflows.items():
            workflows.append({
                "name": workflow.name,
                "description": workflow.description,
                "agents": workflow.agents,
                "parameters": workflow.parameters
            })
        
        return {"workflows": workflows}
    
    @app.get("/v1/stats")
    async def get_stats(user: Dict[str, Any] = Depends(authenticate_request)):
        """Get server statistics."""
        
        # Basic stats (in production, use proper metrics storage)
        user_usage = rate_limit_storage.get(user['user_id'], {})
        current_hour = datetime.utcnow().strftime("%Y-%m-%d-%H")
        current_usage = user_usage.get(current_hour, 0)
        
        return {
            "user_id": user['user_id'],
            "plan": user.get('plan', 'unknown'),
            "rate_limit": user.get('rate_limit', 100),
            "current_usage": current_usage,
            "remaining": max(0, user.get('rate_limit', 100) - current_usage)
        }
    
    return app


async def serve_http(host: str = "0.0.0.0", port: int = 8080):
    """
    Run the MCP server with HTTP transport.
    
    Args:
        host: Host to bind to
        port: Port to bind to
    """
    
    import uvicorn
    
    app = create_http_app()
    
    logger.info(f"Starting MeshAI MCP Server HTTP transport on {host}:{port}")
    
    config = uvicorn.Config(
        app=app,
        host=host,
        port=port,
        log_level="info",
        access_log=True
    )
    
    server = uvicorn.Server(config)
    await server.serve()


if __name__ == "__main__":
    asyncio.run(serve_http())