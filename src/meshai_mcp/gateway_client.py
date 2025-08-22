"""
Gateway Client for Public MCP Server

Provides safe communication with the private tenant gateway service.
Contains no sensitive tenant logic - all security is handled by the private service.
"""

import asyncio
import json
import os
import structlog
from datetime import datetime
from typing import Dict, Any, Optional
import aiohttp

from .auth.models import UserContext
from .tenant_context import MCPForwardRequest, MCPForwardResponse, sanitize_mcp_response

logger = structlog.get_logger(__name__)


class GatewayClientConfig:
    """Configuration for gateway client"""
    
    def __init__(
        self,
        gateway_url: str = None,
        timeout_seconds: int = 30,
        retry_attempts: int = 3,
        retry_delay_seconds: float = 1.0,
        enable_circuit_breaker: bool = True
    ):
        if gateway_url is None:
            gateway_url = os.getenv('MESHAI_GATEWAY_URL', 'http://localhost:8001')
        self.gateway_url = gateway_url.rstrip('/')
        self.timeout_seconds = timeout_seconds
        self.retry_attempts = retry_attempts
        self.retry_delay_seconds = retry_delay_seconds
        self.enable_circuit_breaker = enable_circuit_breaker


class CircuitBreakerState:
    """Simple circuit breaker for gateway communication"""
    
    def __init__(self, failure_threshold: int = 5, recovery_timeout: int = 60):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failure_count = 0
        self.last_failure_time: Optional[datetime] = None
        self.state = "closed"  # closed, open, half-open
    
    def record_success(self):
        """Record successful request"""
        self.failure_count = 0
        self.state = "closed"
    
    def record_failure(self):
        """Record failed request"""
        self.failure_count += 1
        self.last_failure_time = datetime.utcnow()
        
        if self.failure_count >= self.failure_threshold:
            self.state = "open"
    
    def can_execute(self) -> bool:
        """Check if request can be executed"""
        if self.state == "closed":
            return True
        
        if self.state == "open":
            if (self.last_failure_time and 
                (datetime.utcnow() - self.last_failure_time).seconds >= self.recovery_timeout):
                self.state = "half-open"
                return True
            return False
        
        # half-open state
        return True


class TenantGatewayClient:
    """
    Client for communicating with the private tenant gateway service.
    
    This client is responsible for:
    1. Forwarding authenticated MCP requests to the private gateway
    2. Handling retries and circuit breaking
    3. Sanitizing responses for the public server
    4. Managing connection pooling
    
    It contains NO tenant isolation logic - all security is in the private service.
    """
    
    def __init__(self, config: GatewayClientConfig):
        self.config = config
        self.session: Optional[aiohttp.ClientSession] = None
        self.circuit_breaker = CircuitBreakerState() if config.enable_circuit_breaker else None
        
        # Request tracking
        self._active_requests = 0
        self._total_requests = 0
        self._failed_requests = 0
    
    async def __aenter__(self):
        await self.start()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.stop()
    
    async def start(self):
        """Initialize the client session"""
        if self.session is None:
            timeout = aiohttp.ClientTimeout(total=self.config.timeout_seconds)
            self.session = aiohttp.ClientSession(timeout=timeout)
            
            logger.info(
                "Gateway client started",
                gateway_url=self.config.gateway_url,
                timeout=self.config.timeout_seconds
            )
    
    async def stop(self):
        """Clean up the client session"""
        if self.session:
            await self.session.close()
            self.session = None
            
            logger.info("Gateway client stopped")
    
    async def forward_mcp_request(
        self,
        user: UserContext,
        mcp_message: Dict[str, Any],
        request_id: str,
        client_ip: Optional[str] = None,
        user_agent: Optional[str] = None
    ) -> MCPForwardResponse:
        """
        Forward MCP request to private gateway with authentication context.
        
        This method handles the safe forwarding of requests without any tenant logic.
        All tenant isolation and security is handled by the private gateway.
        """
        
        # Check circuit breaker
        if self.circuit_breaker and not self.circuit_breaker.can_execute():
            logger.warning("Circuit breaker open, rejecting request")
            return MCPForwardResponse(
                success=False,
                error={
                    "code": -32603,
                    "message": "Gateway service temporarily unavailable"
                }
            )
        
        # Track request
        self._active_requests += 1
        self._total_requests += 1
        
        try:
            # Prepare request payload
            payload = {
                "user_context": {
                    "user_id": str(user.user_id),
                    "tenant_id": str(user.tenant_id) if user.tenant_id else None,
                    "permissions": user.permissions,
                    "rate_limit": user.rate_limit,
                    "metadata": {
                        **user.metadata,
                        "client_ip": client_ip,
                        "user_agent": user_agent,
                        "forwarded_from": "public_mcp_server"
                    }
                },
                "mcp_message": mcp_message,
                "request_id": request_id
            }
            
            # Execute request with retries
            response = await self._execute_with_retries(payload)
            
            # Record success
            if self.circuit_breaker:
                self.circuit_breaker.record_success()
            
            return response
            
        except Exception as e:
            # Record failure
            if self.circuit_breaker:
                self.circuit_breaker.record_failure()
            
            self._failed_requests += 1
            
            logger.error(
                "Error forwarding MCP request",
                error=str(e),
                request_id=request_id,
                user_id=str(user.user_id)
            )
            
            return MCPForwardResponse(
                success=False,
                error={
                    "code": -32603,
                    "message": f"Gateway communication error: {str(e)}"
                }
            )
        
        finally:
            self._active_requests -= 1
    
    async def _execute_with_retries(self, payload: Dict[str, Any]) -> MCPForwardResponse:
        """Execute request with retry logic"""
        
        last_error = None
        
        for attempt in range(self.config.retry_attempts):
            try:
                return await self._execute_request(payload)
                
            except Exception as e:
                last_error = e
                
                if attempt < self.config.retry_attempts - 1:
                    delay = self.config.retry_delay_seconds * (2 ** attempt)  # Exponential backoff
                    logger.warning(
                        "Request failed, retrying",
                        attempt=attempt + 1,
                        delay=delay,
                        error=str(e)
                    )
                    await asyncio.sleep(delay)
                else:
                    logger.error(
                        "All retry attempts failed",
                        attempts=self.config.retry_attempts,
                        error=str(e)
                    )
        
        raise last_error
    
    async def _execute_request(self, payload: Dict[str, Any]) -> MCPForwardResponse:
        """Execute single request to gateway"""
        
        if not self.session:
            raise RuntimeError("Client session not initialized")
        
        url = f"{self.config.gateway_url}/api/v1/mcp/execute"
        
        async with self.session.post(
            url,
            json=payload,
            headers={
                "Content-Type": "application/json",
                "User-Agent": "MeshAI-MCP-Public-Server/1.0"
            }
        ) as response:
            
            if response.status == 200:
                data = await response.json()
                
                return MCPForwardResponse(
                    success=data.get("success", False),
                    result=data.get("result"),
                    error=data.get("error"),
                    usage_recorded=data.get("usage_recorded", False),
                    quota_remaining=data.get("quota_remaining"),
                    processing_time=data.get("processing_time", 0.0)
                )
            
            elif response.status == 400:
                error_data = await response.json() if response.content_type == "application/json" else {}
                return MCPForwardResponse(
                    success=False,
                    error={
                        "code": -32602,
                        "message": error_data.get("detail", "Bad request")
                    }
                )
            
            elif response.status == 401:
                return MCPForwardResponse(
                    success=False,
                    error={
                        "code": -32001,
                        "message": "Authentication failed"
                    }
                )
            
            elif response.status == 403:
                return MCPForwardResponse(
                    success=False,
                    error={
                        "code": -32002,
                        "message": "Access denied"
                    }
                )
            
            elif response.status == 429:
                return MCPForwardResponse(
                    success=False,
                    error={
                        "code": -32003,
                        "message": "Rate limit exceeded"
                    }
                )
            
            else:
                error_text = await response.text()
                raise aiohttp.ClientResponseError(
                    request_info=response.request_info,
                    history=response.history,
                    status=response.status,
                    message=f"Gateway error: {error_text}"
                )
    
    async def health_check(self) -> bool:
        """Check if gateway service is healthy"""
        
        if not self.session:
            return False
        
        try:
            url = f"{self.config.gateway_url}/health"
            
            async with self.session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get("status") == "healthy"
                return False
                
        except Exception as e:
            logger.warning("Gateway health check failed", error=str(e))
            return False
    
    async def get_service_info(self) -> Dict[str, Any]:
        """Get service information from gateway"""
        
        if not self.session:
            return {"error": "Client not initialized"}
        
        try:
            url = f"{self.config.gateway_url}/health"
            
            async with self.session.get(url) as response:
                if response.status == 200:
                    return await response.json()
                return {"error": f"HTTP {response.status}"}
                
        except Exception as e:
            return {"error": str(e)}
    
    def get_client_stats(self) -> Dict[str, Any]:
        """Get client statistics"""
        
        success_rate = 0.0
        if self._total_requests > 0:
            success_rate = ((self._total_requests - self._failed_requests) / self._total_requests) * 100
        
        circuit_breaker_state = None
        if self.circuit_breaker:
            circuit_breaker_state = {
                "state": self.circuit_breaker.state,
                "failure_count": self.circuit_breaker.failure_count,
                "last_failure": self.circuit_breaker.last_failure_time.isoformat() if self.circuit_breaker.last_failure_time else None
            }
        
        return {
            "gateway_url": self.config.gateway_url,
            "active_requests": self._active_requests,
            "total_requests": self._total_requests,
            "failed_requests": self._failed_requests,
            "success_rate": success_rate,
            "circuit_breaker": circuit_breaker_state
        }


# Global client instance
_gateway_client: Optional[TenantGatewayClient] = None


def get_gateway_client() -> TenantGatewayClient:
    """Get or create global gateway client instance"""
    global _gateway_client
    
    if _gateway_client is None:
        config = GatewayClientConfig()
        _gateway_client = TenantGatewayClient(config)
    
    return _gateway_client


async def initialize_gateway_client(config: Optional[GatewayClientConfig] = None):
    """Initialize global gateway client"""
    global _gateway_client
    
    if _gateway_client:
        await _gateway_client.stop()
    
    if config is None:
        config = GatewayClientConfig()
    
    _gateway_client = TenantGatewayClient(config)
    await _gateway_client.start()


async def shutdown_gateway_client():
    """Shutdown global gateway client"""
    global _gateway_client
    
    if _gateway_client:
        await _gateway_client.stop()
        _gateway_client = None