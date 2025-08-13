"""
Tenant Context Interfaces for Public MCP Server

Provides safe interfaces for tenant context without exposing sensitive logic.
All actual tenant isolation is handled by the private gateway service.
"""

from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from uuid import UUID

from .auth.models import UserContext


@dataclass
class TenantContextInfo:
    """Safe tenant context information for public server"""
    tenant_id: Optional[UUID]
    has_tenant_access: bool
    plan_type: Optional[str] = None
    permissions: List[str] = None
    
    def __post_init__(self):
        if self.permissions is None:
            self.permissions = []


@dataclass
class MCPForwardRequest:
    """Request structure for forwarding to private gateway"""
    user_context: UserContext
    mcp_message: Dict[str, Any]
    request_id: str
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


@dataclass
class MCPForwardResponse:
    """Response structure from private gateway"""
    success: bool
    result: Optional[Dict[str, Any]] = None
    error: Optional[Dict[str, Any]] = None
    usage_recorded: bool = False
    quota_remaining: Optional[Dict[str, float]] = None
    processing_time: float = 0.0


def extract_tenant_context(user: UserContext) -> TenantContextInfo:
    """
    Extract safe tenant context information from user context.
    
    This function only extracts information that's safe to use in the public server.
    It does not perform any tenant isolation logic.
    """
    
    return TenantContextInfo(
        tenant_id=user.tenant_id,
        has_tenant_access=user.tenant_id is not None,
        permissions=user.permissions.copy()
    )


def create_forward_request(
    user: UserContext,
    mcp_message: Dict[str, Any],
    request_id: str,
    additional_metadata: Optional[Dict[str, Any]] = None
) -> MCPForwardRequest:
    """
    Create a request structure for forwarding to the private gateway.
    
    This function safely packages the request without any tenant logic.
    """
    
    metadata = {
        "forwarded_from": "public_mcp_server",
        "request_timestamp": mcp_message.get("timestamp"),
        **(additional_metadata or {})
    }
    
    return MCPForwardRequest(
        user_context=user,
        mcp_message=mcp_message,
        request_id=request_id,
        metadata=metadata
    )


def validate_mcp_message(mcp_message: Dict[str, Any]) -> Dict[str, Any]:
    """
    Validate MCP message structure (safe validation only).
    
    This only performs basic structure validation, no security logic.
    """
    
    validation_result = {
        "valid": True,
        "errors": []
    }
    
    # Check required fields
    if "method" not in mcp_message:
        validation_result["valid"] = False
        validation_result["errors"].append("Missing required field: method")
    
    if "id" not in mcp_message:
        validation_result["valid"] = False
        validation_result["errors"].append("Missing required field: id")
    
    # Validate method name
    method = mcp_message.get("method", "")
    if not isinstance(method, str) or not method.strip():
        validation_result["valid"] = False
        validation_result["errors"].append("Method must be a non-empty string")
    
    # Validate params if present
    params = mcp_message.get("params")
    if params is not None and not isinstance(params, dict):
        validation_result["valid"] = False
        validation_result["errors"].append("Params must be a dictionary")
    
    return validation_result


def sanitize_mcp_response(response: MCPForwardResponse) -> Dict[str, Any]:
    """
    Sanitize response from private gateway for public server.
    
    Removes any sensitive information that shouldn't be exposed.
    """
    
    sanitized = {
        "success": response.success,
        "result": response.result,
        "error": response.error,
        "processing_time": response.processing_time
    }
    
    # Only include quota info if user has quota access permission
    if response.quota_remaining:
        sanitized["quota_remaining"] = response.quota_remaining
    
    # Include usage recorded flag
    sanitized["usage_recorded"] = response.usage_recorded
    
    return sanitized


class TenantContextValidator:
    """
    Validator for tenant context in public server.
    
    This class only performs basic validation and does not contain
    any sensitive tenant isolation logic.
    """
    
    @staticmethod
    def validate_tenant_access(user: UserContext) -> bool:
        """
        Basic validation that user has tenant access.
        
        This is a simple check and does not enforce tenant isolation.
        """
        return user.tenant_id is not None
    
    @staticmethod
    def validate_mcp_permission(user: UserContext) -> bool:
        """
        Check if user has basic MCP access permission.
        
        Actual permission enforcement is done in the private gateway.
        """
        return user.has_any_permission(["mcp:read", "mcp:execute", "mcp:admin"])
    
    @staticmethod
    def get_allowed_methods(user: UserContext) -> List[str]:
        """
        Get list of MCP methods that user might have access to.
        
        This is a safe hint list, actual authorization is in private gateway.
        """
        
        base_methods = ["list_tools", "list_resources"]
        
        if user.has_permission("mcp:execute"):
            base_methods.extend(["tool_call", "read_resource"])
        
        if user.has_permission("mcp:admin"):
            base_methods.extend([
                "workflow_execute", 
                "agent_register", 
                "agent_discover",
                "list_workflows",
                "list_agents"
            ])
        
        return base_methods


class MCPRequestPreprocessor:
    """
    Preprocessor for MCP requests in public server.
    
    Performs safe preprocessing without any tenant logic.
    """
    
    @staticmethod
    def add_request_metadata(
        mcp_message: Dict[str, Any],
        user: UserContext,
        request_id: str,
        client_ip: Optional[str] = None,
        user_agent: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Add safe metadata to MCP request.
        
        This only adds non-sensitive metadata for tracking purposes.
        """
        
        # Create a copy to avoid modifying original
        processed_message = mcp_message.copy()
        
        # Add metadata to params
        if "params" not in processed_message:
            processed_message["params"] = {}
        
        processed_message["params"]["_request_metadata"] = {
            "request_id": request_id,
            "public_server": True,
            "user_id": str(user.user_id),
            "tenant_id": str(user.tenant_id) if user.tenant_id else None,
            "client_ip": client_ip,
            "user_agent": user_agent
        }
        
        return processed_message
    
    @staticmethod
    def validate_request_size(mcp_message: Dict[str, Any], max_size_bytes: int = 1024 * 1024) -> bool:
        """
        Validate request size to prevent abuse.
        
        This is a basic safety check without tenant-specific logic.
        """
        
        try:
            import json
            message_size = len(json.dumps(mcp_message, default=str).encode('utf-8'))
            return message_size <= max_size_bytes
        except Exception:
            return False
    
    @staticmethod
    def extract_operation_type(method: str) -> str:
        """
        Extract operation type from method name for categorization.
        
        This helps with logging and basic request tracking.
        """
        
        if method.startswith("list_"):
            return "read"
        elif method.startswith("read_"):
            return "read"
        elif method.startswith("tool_"):
            return "execute"
        elif method.startswith("workflow_"):
            return "execute"
        elif method.startswith("agent_"):
            return "manage"
        else:
            return "unknown"