"""Safe Authentication Client for MCP Server"""

from .client import AuthClient
from .models import TokenValidation, UserContext, AuthError

# Import middleware only when fastapi is available
try:
    from .middleware import AuthMiddleware, get_current_user, get_current_user_optional
    _MIDDLEWARE_AVAILABLE = True
except ImportError:
    AuthMiddleware = None
    get_current_user = None
    get_current_user_optional = None
    _MIDDLEWARE_AVAILABLE = False

__all__ = [
    'AuthClient',
    'TokenValidation',
    'UserContext', 
    'AuthError'
]

if _MIDDLEWARE_AVAILABLE:
    __all__.extend(['AuthMiddleware', 'get_current_user', 'get_current_user_optional'])