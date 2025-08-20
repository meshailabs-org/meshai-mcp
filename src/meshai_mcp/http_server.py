"""
HTTP Transport for MeshAI MCP Server

Provides HTTP/REST API endpoints for MCP protocol communication.
Uses secure authentication via MeshAI auth service.
"""

import asyncio
import json
import os
from typing import Dict, Any, Optional, Union
from datetime import datetime, timedelta

from fastapi import FastAPI, HTTPException, Depends, Request, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import structlog
from pydantic import BaseModel

from .server import MeshAIMCPServer
from .auth.client import AuthClient, get_auth_client
from .auth.middleware import AuthMiddleware, get_current_user, get_current_user_optional
from .auth.models import UserContext, AuthConfig
from .gateway_client import get_gateway_client, initialize_gateway_client, shutdown_gateway_client
from .tenant_context import (
    extract_tenant_context, validate_mcp_message, TenantContextValidator,
    MCPRequestPreprocessor
)

logger = structlog.get_logger(__name__)

class MCPRequest(BaseModel):
    """HTTP request body for MCP calls - JSON-RPC 2.0 format"""
    jsonrpc: str = "2.0"
    method: str
    id: Optional[Union[str, int]] = None  # Optional for notifications
    params: Optional[Dict[str, Any]] = None

class MCPErrorResponse(BaseModel):
    """Error response for JSON-RPC 2.0"""
    jsonrpc: str = "2.0"
    id: Optional[Union[str, int]] = None
    error: Dict[str, Any]

class MCPSuccessResponse(BaseModel):
    """Success response for JSON-RPC 2.0"""
    jsonrpc: str = "2.0"
    id: Optional[Union[str, int]] = None
    result: Dict[str, Any]

class MCPNotificationResponse(BaseModel):
    """Response for notifications (no response needed)"""
    pass


def create_http_app() -> FastAPI:
    """Create FastAPI application for MCP HTTP transport with secure authentication."""
    
    app = FastAPI(
        title="MeshAI MCP Server",
        description="HTTP API for MeshAI Multi-Agent Orchestration via MCP",
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc"
    )
    
    # Initialize authentication
    auth_config = AuthConfig()
    auth_client = AuthClient(auth_config)
    
    # Add authentication middleware (processes all requests)
    app.add_middleware(AuthMiddleware, auth_client=auth_client)
    
    # CORS middleware (add after auth middleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Configure appropriately for production
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # Initialize MCP server
    mcp_server = MeshAIMCPServer()
    
    @app.on_event("startup")
    async def startup_event():
        """Initialize services on startup"""
        try:
            # Initialize the auth client first
            await auth_client._ensure_http_client()
            logger.info("Auth client initialized")
            
            # Initialize gateway client
            await initialize_gateway_client()
            logger.info("Gateway client initialized")
        except Exception as e:
            logger.error("Failed to initialize services", error=str(e))
    
    @app.on_event("shutdown")
    async def shutdown_event():
        """Clean up services on shutdown"""
        try:
            # Shutdown gateway client
            await shutdown_gateway_client()
            logger.info("Gateway client shut down")
            
            # Close auth client
            await auth_client.close()
            logger.info("Auth client shut down")
        except Exception as e:
            logger.error("Error shutting down services", error=str(e))
    
    @app.get("/health")
    async def health_check():
        """Health check endpoint."""
        auth_healthy = await auth_client.health_check()
        
        # Check gateway health
        gateway_healthy = False
        try:
            gateway_client = get_gateway_client()
            gateway_healthy = await gateway_client.health_check()
        except Exception as e:
            logger.warning("Gateway health check failed", error=str(e))
        
        overall_status = "healthy"
        if not auth_healthy:
            overall_status = "degraded"
        if not gateway_healthy:
            overall_status = "degraded" if overall_status == "healthy" else "unhealthy"
        
        return {
            "status": overall_status,
            "service": "meshai-mcp-server",
            "services": {
                "auth_service": "healthy" if auth_healthy else "unavailable",
                "gateway_service": "healthy" if gateway_healthy else "unavailable"
            },
            "timestamp": datetime.utcnow().isoformat()
        }
    
    @app.get("/")
    async def root():
        """Root endpoint with API information."""
        return {
            "service": "MeshAI MCP Server",
            "version": "0.1.0",
            "transport": "http",
            "authentication": "required",
            "endpoints": {
                "mcp": "/v1/mcp",
                "health": "/health",
                "docs": "/docs"
            }
        }
    
    @app.post("/v1/mcp", response_model=Union[MCPSuccessResponse, MCPErrorResponse, MCPNotificationResponse])
    async def handle_mcp_request(
        request: MCPRequest,
        http_request: Request,
        user: UserContext = Depends(get_current_user)
    ) -> Union[MCPSuccessResponse, MCPErrorResponse, MCPNotificationResponse]:
        """
        Handle MCP protocol requests over HTTP with authentication.
        
        This endpoint forwards authenticated requests to the private tenant gateway
        which handles all tenant isolation and security logic.
        """
        
        # Generate request ID
        request_id = f"mcp_{int(datetime.utcnow().timestamp() * 1000)}_{user.user_id}"
        
        logger.info(
            "MCP request from authenticated user",
            user_id=str(user.user_id),
            tenant_id=str(user.tenant_id) if user.tenant_id else None,
            method=request.method,
            request_id=request_id,
            is_notification=request.id is None
        )
        
        # Check if this is a notification (no ID field)
        is_notification = request.id is None
        
        try:
            # For notifications, handle them and return 204 No Content
            if is_notification:
                logger.info(f"Handling notification: {request.method}")
                
                # Handle common notification methods
                if request.method == "notifications/initialized":
                    logger.info("Client initialized notification received")
                elif request.method == "notifications/roots/list_changed":
                    logger.info("Roots list changed notification received")
                elif request.method.startswith("notifications/"):
                    logger.info(f"Unknown notification method: {request.method}")
                
                # For notifications, return empty response with 204 status
                from fastapi import Response
                return Response(status_code=204)
            
            # Validate tenant access (basic check only)
            if not TenantContextValidator.validate_tenant_access(user):
                return MCPErrorResponse(
                    id=request.id if request.id is not None else request_id,
                    error={
                        "code": -32002,
                        "message": "Tenant access required for MCP operations"
                    }
                )
            
            # Validate MCP permissions (basic check only)
            if not TenantContextValidator.validate_mcp_permission(user):
                return MCPErrorResponse(
                    id=request.id if request.id is not None else request_id,
                    error={
                        "code": -32002,
                        "message": "Insufficient permissions for MCP operations"
                    }
                )
            
            # Convert HTTP request to MCP message format
            # Ensure ID is string for consistency
            msg_id = str(request.id) if request.id is not None else request_id
            mcp_message = {
                "jsonrpc": "2.0",
                "method": request.method,
                "id": msg_id,
                "params": request.params or {}
            }
            
            # Validate message structure
            validation = validate_mcp_message(mcp_message)
            if not validation["valid"]:
                return MCPErrorResponse(
                    id=request.id if request.id is not None else request_id,
                    error={
                        "code": -32602,
                        "message": f"Invalid request: {', '.join(validation['errors'])}"
                    }
                )
            
            # Validate request size
            if not MCPRequestPreprocessor.validate_request_size(mcp_message):
                return MCPErrorResponse(
                    id=request.id if request.id is not None else request_id,
                    error={
                        "code": -32602,
                        "message": "Request too large"
                    }
                )
            
            # Add request metadata
            client_ip = http_request.client.host if http_request.client else None
            user_agent = http_request.headers.get("user-agent")
            
            processed_message = MCPRequestPreprocessor.add_request_metadata(
                mcp_message, user, request_id, client_ip, user_agent
            )
            
            # Forward to production gateway
            gateway_client = get_gateway_client()
            
            if not await gateway_client.health_check():
                logger.warning("Gateway health check failed")
                return MCPErrorResponse(
                    id=request.id if request.id is not None else request_id,
                    error={
                        "code": -32603,
                        "message": "Gateway service unavailable"
                    }
                )
            
            # Forward request to private gateway
            gateway_response = await gateway_client.forward_mcp_request(
                user=user,
                mcp_message=processed_message,
                request_id=request_id,
                client_ip=client_ip,
                user_agent=user_agent
            )
            
            # Convert gateway response to MCP response
            if gateway_response.success:
                return MCPSuccessResponse(
                    id=request.id if request.id is not None else request_id,
                    result=gateway_response.result or {}
                )
            else:
                return MCPErrorResponse(
                    id=request.id if request.id is not None else request_id,
                    error=gateway_response.error
                )
                
        except Exception as e:
            logger.error(
                "Error handling MCP request",
                error=str(e),
                user_id=str(user.user_id),
                method=request.method,
                request_id=request_id
            )
            return MCPErrorResponse(
                id=request.id if request.id is not None else request_id,
                error={
                    "code": -32603,
                    "message": f"Internal error: {str(e)}"
                }
            )
    
    @app.get("/v1/tools")
    async def list_tools(
        http_request: Request,
        user: UserContext = Depends(get_current_user)
    ):
        """List available MCP tools for authenticated user via gateway."""
        
        logger.info("Listing tools", user_id=str(user.user_id))
        
        try:
            # Basic validation
            if not TenantContextValidator.validate_tenant_access(user):
                raise HTTPException(status_code=403, detail="Tenant access required")
            
            # Create MCP request for list_tools
            request_id = f"tools_{int(datetime.utcnow().timestamp() * 1000)}"
            mcp_message = {
                "type": "request",
                "method": "list_tools",
                "id": request_id,
                "params": {}
            }
            
            # Forward to gateway
            gateway_client = get_gateway_client()
            client_ip = http_request.client.host if http_request.client else None
            user_agent = http_request.headers.get("user-agent")
            
            gateway_response = await gateway_client.forward_mcp_request(
                user=user,
                mcp_message=mcp_message,
                request_id=request_id,
                client_ip=client_ip,
                user_agent=user_agent
            )
            
            if gateway_response.success:
                return gateway_response.result
            else:
                error_msg = gateway_response.error.get("message", "Unknown error") if gateway_response.error else "Unknown error"
                raise HTTPException(status_code=500, detail=error_msg)
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error("Error listing tools", error=str(e), user_id=str(user.user_id))
            raise HTTPException(status_code=500, detail=str(e))
    
    @app.get("/v1/resources")
    async def list_resources(
        http_request: Request,
        resource_type: Optional[str] = None,
        limit: int = 50,
        user: UserContext = Depends(get_current_user)
    ):
        """List available MCP resources for authenticated user via gateway."""
        
        logger.info("Listing resources", user_id=str(user.user_id))
        
        try:
            # Basic validation
            if not TenantContextValidator.validate_tenant_access(user):
                raise HTTPException(status_code=403, detail="Tenant access required")
            
            # Create MCP request for list_resources
            request_id = f"resources_{int(datetime.utcnow().timestamp() * 1000)}"
            mcp_message = {
                "type": "request",
                "method": "list_resources",
                "id": request_id,
                "params": {
                    "resource_type": resource_type,
                    "limit": limit
                }
            }
            
            # Forward to gateway
            gateway_client = get_gateway_client()
            client_ip = http_request.client.host if http_request.client else None
            user_agent = http_request.headers.get("user-agent")
            
            gateway_response = await gateway_client.forward_mcp_request(
                user=user,
                mcp_message=mcp_message,
                request_id=request_id,
                client_ip=client_ip,
                user_agent=user_agent
            )
            
            if gateway_response.success:
                return gateway_response.result
            else:
                error_msg = gateway_response.error.get("message", "Unknown error") if gateway_response.error else "Unknown error"
                raise HTTPException(status_code=500, detail=error_msg)
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error("Error listing resources", error=str(e), user_id=str(user.user_id))
            raise HTTPException(status_code=500, detail=str(e))
    
    @app.get("/v1/workflows")
    async def list_workflows(
        http_request: Request,
        status: Optional[str] = None,
        limit: int = 50,
        user: UserContext = Depends(get_current_user)
    ):
        """List available MeshAI workflows for authenticated user via gateway."""
        
        logger.info("Listing workflows", user_id=str(user.user_id))
        
        try:
            # Basic validation
            if not TenantContextValidator.validate_tenant_access(user):
                raise HTTPException(status_code=403, detail="Tenant access required")
            
            # Create MCP request for list_workflows
            request_id = f"workflows_{int(datetime.utcnow().timestamp() * 1000)}"
            mcp_message = {
                "type": "request",
                "method": "list_workflows",
                "id": request_id,
                "params": {
                    "status": status,
                    "limit": limit
                }
            }
            
            # Forward to gateway
            gateway_client = get_gateway_client()
            client_ip = http_request.client.host if http_request.client else None
            user_agent = http_request.headers.get("user-agent")
            
            gateway_response = await gateway_client.forward_mcp_request(
                user=user,
                mcp_message=mcp_message,
                request_id=request_id,
                client_ip=client_ip,
                user_agent=user_agent
            )
            
            if gateway_response.success:
                return gateway_response.result
            else:
                error_msg = gateway_response.error.get("message", "Unknown error") if gateway_response.error else "Unknown error"
                raise HTTPException(status_code=500, detail=error_msg)
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error("Error listing workflows", error=str(e), user_id=str(user.user_id))
            raise HTTPException(status_code=500, detail=str(e))
    
    @app.get("/v1/user/info")
    async def get_user_info(user: UserContext = Depends(get_current_user)):
        """Get current user information."""
        
        return {
            "user_id": str(user.user_id),
            "tenant_id": str(user.tenant_id) if user.tenant_id else None,
            "permissions": user.permissions,
            "rate_limit": user.rate_limit,
            "metadata": user.metadata
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