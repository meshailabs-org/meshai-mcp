"""Safe authentication models for public MCP server"""

from datetime import datetime
from typing import Optional, List, Dict, Any
from dataclasses import dataclass
from uuid import UUID
from enum import Enum


class AuthErrorType(str, Enum):
    """Authentication error types"""
    INVALID_TOKEN = "invalid_token"
    EXPIRED_TOKEN = "expired_token"
    MISSING_TOKEN = "missing_token"
    INSUFFICIENT_PERMISSIONS = "insufficient_permissions"
    RATE_LIMIT_EXCEEDED = "rate_limit_exceeded"
    SERVICE_UNAVAILABLE = "service_unavailable"


@dataclass
class AuthError:
    """Authentication error"""
    error_type: AuthErrorType
    message: str
    details: Optional[Dict[str, Any]] = None


@dataclass
class TokenValidation:
    """Token validation result"""
    valid: bool
    user_id: Optional[UUID] = None
    tenant_id: Optional[UUID] = None
    permissions: List[str] = None
    rate_limit: Optional[int] = None
    error: Optional[AuthError] = None
    
    def __post_init__(self):
        if self.permissions is None:
            self.permissions = []


@dataclass
class UserContext:
    """User context for authenticated requests"""
    user_id: UUID
    tenant_id: Optional[UUID]
    permissions: List[str]
    rate_limit: int = 1000
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}
    
    def has_permission(self, permission: str) -> bool:
        """Check if user has a specific permission"""
        return permission in self.permissions
    
    def has_any_permission(self, permissions: List[str]) -> bool:
        """Check if user has any of the specified permissions"""
        return any(perm in self.permissions for perm in permissions)
    
    def has_all_permissions(self, permissions: List[str]) -> bool:
        """Check if user has all of the specified permissions"""
        return all(perm in self.permissions for perm in permissions)


@dataclass
class RateLimitInfo:
    """Rate limiting information"""
    limit: int
    remaining: int
    reset_time: float  # Unix timestamp
    window_seconds: int = 3600  # 1 hour default


@dataclass
class AuthConfig:
    """Authentication configuration for MCP server"""
    
    # MeshAI API endpoints
    auth_service_url: str = "https://meshai-admin-dashboard-96062037338.us-central1.run.app"
    validate_endpoint: str = "/api/validate-key"
    
    # Request configuration
    timeout_seconds: int = 5
    retry_attempts: int = 3
    retry_delay_seconds: float = 1.0
    
    # Caching
    enable_token_cache: bool = True
    cache_ttl_seconds: int = 300  # 5 minutes
    
    # Rate limiting
    enable_rate_limiting: bool = True
    default_rate_limit: int = 100  # requests per hour
    
    # Security
    require_https: bool = True
    verify_ssl: bool = True
    
    def get_validate_url(self) -> str:
        """Get full validation endpoint URL"""
        return f"{self.auth_service_url.rstrip('/')}{self.validate_endpoint}"