"""Safe authentication middleware for MCP server"""

from typing import Callable, Optional
from fastapi import Request, Response, HTTPException, status, Depends
from starlette.middleware.base import BaseHTTPMiddleware
import structlog

from .client import AuthClient, get_auth_client
from .models import UserContext, AuthErrorType

logger = structlog.get_logger(__name__)


class AuthMiddleware(BaseHTTPMiddleware):
    """
    Authentication middleware for MCP server.
    
    This middleware contains NO security logic - it delegates all
    authentication to the secure MeshAI auth service.
    """
    
    def __init__(self, app, auth_client: Optional[AuthClient] = None):
        super().__init__(app)
        self.auth_client = auth_client
        
        # Paths that don't require authentication
        self.public_paths = {
            "/health",
            "/docs",
            "/redoc", 
            "/openapi.json",
            "/",
            "/favicon.ico"
        }
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Process request with authentication"""
        
        # Skip authentication for public paths
        if request.url.path in self.public_paths:
            return await call_next(request)
        
        # Skip authentication for OPTIONS requests (CORS preflight)
        if request.method == "OPTIONS":
            return await call_next(request)
        
        # Get auth client
        try:
            auth_client = self.auth_client or await get_auth_client()
        except Exception as e:
            logger.error("Failed to get auth client", error=str(e))
            return self._service_error_response("Authentication service unavailable")
        
        # Extract token from Authorization header
        token = self._extract_token(request)
        
        if not token:
            logger.warning("Missing authorization token", path=request.url.path)
            return self._unauthorized_response("Authorization token required")
        
        # Validate token with auth service
        try:
            user_context = await auth_client.get_user_context(token)
        except Exception as e:
            logger.error("Auth service error during validation", error=str(e), path=request.url.path)
            return self._service_error_response("Authentication service error")
        
        if not user_context:
            logger.warning("Invalid authorization token", path=request.url.path, token_prefix=token[:8] + "..." if len(token) > 8 else "short")
            return self._unauthorized_response("Invalid or expired token")
        
        # Check rate limiting
        if not auth_client.check_rate_limit(user_context):
            logger.warning(
                "Rate limit exceeded", 
                user_id=str(user_context.user_id),
                path=request.url.path
            )
            return self._rate_limit_response(user_context, auth_client)
        
        # Add user context to request state
        request.state.user_context = user_context
        request.state.authenticated = True
        
        # Process request
        response = await call_next(request)
        
        # Add rate limit headers
        rate_info = auth_client.get_rate_limit_info(user_context)
        response.headers["X-RateLimit-Limit"] = str(rate_info.limit)
        response.headers["X-RateLimit-Remaining"] = str(rate_info.remaining)
        response.headers["X-RateLimit-Reset"] = str(int(rate_info.reset_time))
        
        return response
    
    def _extract_token(self, request: Request) -> Optional[str]:
        """Extract token from Authorization header"""
        
        authorization = request.headers.get("Authorization")
        if not authorization:
            return None
        
        # Support both "Bearer <token>" and just "<token>"
        if authorization.startswith("Bearer "):
            return authorization[7:]  # Remove "Bearer " prefix
        
        return authorization
    
    def _unauthorized_response(self, message: str) -> Response:
        """Create unauthorized response"""
        
        return Response(
            content=f'{{"error": "Unauthorized", "message": "{message}"}}',
            status_code=status.HTTP_401_UNAUTHORIZED,
            media_type="application/json",
            headers={"WWW-Authenticate": "Bearer"}
        )
    
    def _rate_limit_response(self, user_context: UserContext, auth_client: AuthClient) -> Response:
        """Create rate limit exceeded response"""
        
        rate_info = auth_client.get_rate_limit_info(user_context)
        
        return Response(
            content=f'{{"error": "Rate limit exceeded", "limit": {rate_info.limit}, "reset": {int(rate_info.reset_time)}}}',
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            media_type="application/json",
            headers={
                "X-RateLimit-Limit": str(rate_info.limit),
                "X-RateLimit-Remaining": "0",
                "X-RateLimit-Reset": str(int(rate_info.reset_time)),
                "Retry-After": str(rate_info.window_seconds)
            }
        )
    
    def _service_error_response(self, message: str) -> Response:
        """Create service error response"""
        
        return Response(
            content=f'{{"error": "Service Unavailable", "message": "{message}"}}',
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            media_type="application/json",
            headers={"Retry-After": "60"}
        )


async def get_current_user(request: Request) -> UserContext:
    """
    FastAPI dependency to get current authenticated user.
    
    This should be used in route handlers that require authentication.
    """
    
    if not hasattr(request.state, 'user_context'):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required"
        )
    
    return request.state.user_context


async def get_current_user_optional(request: Request) -> Optional[UserContext]:
    """
    FastAPI dependency to get current user if authenticated, None otherwise.
    """
    
    if hasattr(request.state, 'user_context'):
        return request.state.user_context
    
    return None


def require_permissions(*permissions: str):
    """
    Decorator to require specific permissions.
    
    Usage:
        @require_permissions("read:agents", "write:workflows")
        async def my_endpoint(user: UserContext = Depends(get_current_user)):
            ...
    """
    
    def dependency(user_context: UserContext = Depends(get_current_user)) -> UserContext:
        missing_permissions = [
            perm for perm in permissions 
            if not user_context.has_permission(perm)
        ]
        
        if missing_permissions:
            logger.warning(
                "Insufficient permissions",
                user_id=str(user_context.user_id),
                required=list(permissions),
                missing=missing_permissions
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Missing permissions: {', '.join(missing_permissions)}"
            )
        
        return user_context
    
    return dependency


def require_tenant_access(tenant_id_param: str = "tenant_id"):
    """
    Decorator to require access to a specific tenant.
    
    Usage:
        @require_tenant_access("tenant_id")
        async def my_endpoint(tenant_id: UUID, user: UserContext = Depends(get_current_user)):
            ...
    """
    
    def dependency(
        request: Request,
        user_context: UserContext = Depends(get_current_user)
    ) -> UserContext:
        
        # Get tenant ID from path parameters
        tenant_id = request.path_params.get(tenant_id_param)
        
        if not tenant_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Missing {tenant_id_param} parameter"
            )
        
        # Check if user has access to this tenant
        if user_context.tenant_id and str(user_context.tenant_id) != str(tenant_id):
            logger.warning(
                "Tenant access denied",
                user_id=str(user_context.user_id),
                user_tenant=str(user_context.tenant_id),
                requested_tenant=str(tenant_id)
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to this tenant"
            )
        
        return user_context
    
    return dependency