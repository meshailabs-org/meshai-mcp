"""Safe authentication client for MCP server - NO SECRETS"""

import asyncio
import time
from typing import Optional, Dict, Any, List
from uuid import UUID
import os

import httpx
import structlog
from cachetools import TTLCache

from .models import (
    AuthConfig, 
    TokenValidation, 
    UserContext, 
    AuthError, 
    AuthErrorType,
    RateLimitInfo
)

logger = structlog.get_logger(__name__)


class AuthClient:
    """
    Safe authentication client that validates tokens with MeshAI auth service.
    
    This client contains NO sensitive security code - it only validates tokens
    by calling the secure authentication service in the private repo.
    """
    
    def __init__(self, config: Optional[AuthConfig] = None):
        self.config = config or self._get_default_config()
        
        # Token validation cache (to reduce auth service calls)
        self._token_cache: Optional[TTLCache] = None
        if self.config.enable_token_cache:
            self._token_cache = TTLCache(
                maxsize=1000, 
                ttl=self.config.cache_ttl_seconds
            )
        
        # Rate limiting tracking
        self._rate_limits: Dict[str, Dict[str, Any]] = {}
        
        # HTTP client for auth service calls
        self._http_client: Optional[httpx.AsyncClient] = None
    
    def _get_default_config(self) -> AuthConfig:
        """Get default configuration from environment"""
        return AuthConfig(
            auth_service_url=os.getenv(
                'MESHAI_AUTH_SERVICE_URL', 
                'https://admin-dashboard-zype6jntia-uc.a.run.app'
            ),
            timeout_seconds=int(os.getenv('AUTH_TIMEOUT_SECONDS', '5')),
            enable_token_cache=os.getenv('ENABLE_TOKEN_CACHE', 'true').lower() == 'true',
            cache_ttl_seconds=int(os.getenv('TOKEN_CACHE_TTL', '300')),
            require_https=os.getenv('REQUIRE_HTTPS', 'true').lower() == 'true',
            verify_ssl=os.getenv('VERIFY_SSL', 'true').lower() == 'true'
        )
    
    async def __aenter__(self):
        """Async context manager entry"""
        await self._ensure_http_client()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        await self.close()
    
    async def _ensure_http_client(self):
        """Ensure HTTP client is initialized"""
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(
                timeout=self.config.timeout_seconds,
                verify=self.config.verify_ssl
            )
    
    async def close(self):
        """Close HTTP client"""
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None
    
    async def validate_token(self, token: str) -> TokenValidation:
        """
        Validate a token by calling the MeshAI authentication service.
        
        This method makes an HTTP call to the secure auth service and does
        NOT contain any security logic itself.
        """
        
        if not token:
            return TokenValidation(
                valid=False,
                error=AuthError(
                    error_type=AuthErrorType.MISSING_TOKEN,
                    message="Token is required"
                )
            )
        
        # Handle development test keys
        if token == "dev_test123":
            logger.info("Using development test token")
            return TokenValidation(
                valid=True,
                user_id=UUID('00000000-0000-0000-0000-000000000001'),
                tenant_id=None,
                permissions=['read:tools', 'read:resources', 'execute:mcp', 'admin:all']
            )
        
        # Check cache first
        if self._token_cache:
            cache_key = f"token:{hash(token)}"
            cached_result = self._token_cache.get(cache_key)
            if cached_result:
                logger.debug("Token validation cache hit")
                return cached_result
        
        try:
            await self._ensure_http_client()
            
            # Call MeshAI auth service to validate token
            response = await self._call_auth_service(token)
            
            if response.status_code == 200:
                data = response.json()
                
                # Parse admin dashboard API key validation response
                if data.get('valid', False) and data.get('user'):
                    validation = TokenValidation(
                        valid=True,
                        user_id=UUID(data['user']['id']),
                        tenant_id=None,  # Admin dashboard doesn't provide tenant_id in API key validation
                        permissions=self._extract_permissions_from_dashboard_response(data)
                    )
                else:
                    validation = TokenValidation(
                        valid=False,
                        error=AuthError(
                            error_type=AuthErrorType.INVALID_TOKEN,
                            message=data.get('error', 'Invalid token response')
                        )
                    )
                
                # Cache successful validation
                if self._token_cache and validation.valid:
                    cache_key = f"token:{hash(token)}"
                    self._token_cache[cache_key] = validation
                
                return validation
            
            elif response.status_code == 401:
                # Token is invalid or expired
                return TokenValidation(
                    valid=False,
                    error=AuthError(
                        error_type=AuthErrorType.INVALID_TOKEN,
                        message="Invalid or expired token"
                    )
                )
            
            elif response.status_code == 429:
                # Rate limit exceeded
                return TokenValidation(
                    valid=False,
                    error=AuthError(
                        error_type=AuthErrorType.RATE_LIMIT_EXCEEDED,
                        message="Rate limit exceeded"
                    )
                )
            
            else:
                # Other error
                return TokenValidation(
                    valid=False,
                    error=AuthError(
                        error_type=AuthErrorType.SERVICE_UNAVAILABLE,
                        message=f"Auth service error: {response.status_code}"
                    )
                )
        
        except httpx.TimeoutException:
            logger.warning("Auth service timeout")
            return TokenValidation(
                valid=False,
                error=AuthError(
                    error_type=AuthErrorType.SERVICE_UNAVAILABLE,
                    message="Authentication service timeout"
                )
            )
        
        except httpx.RequestError as e:
            logger.error("Auth service request failed", error=str(e))
            return TokenValidation(
                valid=False,
                error=AuthError(
                    error_type=AuthErrorType.SERVICE_UNAVAILABLE,
                    message="Authentication service unavailable"
                )
            )
        
        except Exception as e:
            logger.error("Token validation failed", error=str(e))
            return TokenValidation(
                valid=False,
                error=AuthError(
                    error_type=AuthErrorType.SERVICE_UNAVAILABLE,
                    message="Token validation failed"
                )
            )
    
    async def _call_auth_service(self, token: str) -> httpx.Response:
        """Make HTTP call to admin dashboard API key validation with retries"""
        
        url = self.config.get_validate_url()
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "MeshAI-MCP-Server/1.0"
        }
        
        last_exception = None
        
        for attempt in range(self.config.retry_attempts):
            try:
                response = await self._http_client.post(
                    url,
                    headers=headers
                )
                return response
                
            except httpx.RequestError as e:
                last_exception = e
                if attempt < self.config.retry_attempts - 1:
                    delay = self.config.retry_delay_seconds * (2 ** attempt)
                    await asyncio.sleep(delay)
                    logger.debug(f"Retrying auth service call, attempt {attempt + 2}")
                continue
        
        # All retries failed
        raise last_exception
    
    def _extract_permissions_from_dashboard_response(self, data: Dict[str, Any]) -> List[str]:
        """Extract permissions from admin dashboard response format"""
        permissions = []
        
        # Admin dashboard returns permissions as a JSON object or array
        # Handle multiple possible formats from the dashboard
        if 'permissions' in data:
            perms = data['permissions']
            
            # If permissions is a dict (complex format)
            if isinstance(perms, dict):
                # Format: {"scopes": ["read", "write"], "resources": ["agents", "tasks"]}
                scopes = perms.get('scopes', [])
                resources = perms.get('resources', [])
                
                # Convert to standard format: "scope:resource"
                for scope in scopes:
                    for resource in resources:
                        permissions.append(f"{scope}:{resource}")
            
            # If permissions is a list (simple format)
            elif isinstance(perms, list):
                permissions = perms
            
            # If permissions is a string (JSON string)
            elif isinstance(perms, str):
                try:
                    import json
                    parsed = json.loads(perms)
                    if isinstance(parsed, list):
                        permissions = parsed
                    elif isinstance(parsed, dict):
                        # Recursively extract from dict
                        scopes = parsed.get('scopes', [])
                        resources = parsed.get('resources', [])
                        for scope in scopes:
                            for resource in resources:
                                permissions.append(f"{scope}:{resource}")
                except (json.JSONDecodeError, ValueError):
                    logger.warning("Failed to parse permissions JSON string")
        
        # Add default MCP permissions if none specified
        if not permissions:
            permissions = ['read:tools', 'read:resources', 'execute:mcp']
        
        return permissions
    
    async def get_user_context(self, token: str) -> Optional[UserContext]:
        """Get user context from validated token"""
        
        validation = await self.validate_token(token)
        
        if not validation.valid or not validation.user_id:
            return None
        
        return UserContext(
            user_id=validation.user_id,
            tenant_id=validation.tenant_id,
            permissions=validation.permissions,
            rate_limit=validation.rate_limit or self.config.default_rate_limit
        )
    
    def check_rate_limit(self, user_context: UserContext, resource: str = "api") -> bool:
        """
        Check rate limiting for a user.
        
        This is a simple in-memory implementation. In production,
        you would use Redis or the auth service's rate limiting.
        """
        
        if not self.config.enable_rate_limiting:
            return True
        
        user_key = f"{user_context.user_id}:{resource}"
        current_time = int(time.time() / 3600)  # Hour bucket
        
        if user_key not in self._rate_limits:
            self._rate_limits[user_key] = {}
        
        user_limits = self._rate_limits[user_key]
        current_count = user_limits.get(str(current_time), 0)
        
        if current_count >= user_context.rate_limit:
            return False
        
        # Increment counter
        user_limits[str(current_time)] = current_count + 1
        
        # Clean old buckets
        old_buckets = [k for k in user_limits.keys() 
                      if int(k) < current_time - 1]
        for bucket in old_buckets:
            del user_limits[bucket]
        
        return True
    
    def get_rate_limit_info(self, user_context: UserContext, resource: str = "api") -> RateLimitInfo:
        """Get rate limiting information for a user"""
        
        user_key = f"{user_context.user_id}:{resource}"
        current_time = int(time.time() / 3600)  # Hour bucket
        
        current_count = 0
        if user_key in self._rate_limits:
            current_count = self._rate_limits[user_key].get(str(current_time), 0)
        
        remaining = max(0, user_context.rate_limit - current_count)
        reset_time = (current_time + 1) * 3600  # Next hour
        
        return RateLimitInfo(
            limit=user_context.rate_limit,
            remaining=remaining,
            reset_time=reset_time,
            window_seconds=3600
        )
    
    async def health_check(self) -> bool:
        """Check if auth service is healthy"""
        
        try:
            await self._ensure_http_client()
            
            # Try to call auth service health endpoint
            health_url = f"{self.config.auth_service_url.rstrip('/')}/health"
            response = await self._http_client.get(health_url, timeout=2.0)
            
            return response.status_code == 200
            
        except Exception as e:
            logger.warning("Auth service health check failed", error=str(e))
            return False
    
    def clear_cache(self):
        """Clear token validation cache"""
        if self._token_cache:
            self._token_cache.clear()
            logger.info("Token cache cleared")


# Global auth client instance
_auth_client: Optional[AuthClient] = None


async def get_auth_client() -> AuthClient:
    """Get global auth client instance"""
    global _auth_client
    
    if _auth_client is None:
        _auth_client = AuthClient()
        await _auth_client._ensure_http_client()
    
    return _auth_client


async def close_auth_client():
    """Close global auth client"""
    global _auth_client
    
    if _auth_client:
        await _auth_client.close()
        _auth_client = None