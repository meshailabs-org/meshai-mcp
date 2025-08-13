"""Tests for MCP Server Authentication Integration"""

import pytest
import asyncio
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

import httpx

from meshai_mcp.auth.client import AuthClient
from meshai_mcp.auth.models import (
    AuthConfig, 
    TokenValidation, 
    UserContext, 
    AuthError, 
    AuthErrorType
)


class TestAuthClient:
    """Test cases for AuthClient"""
    
    @pytest.fixture
    def auth_config(self):
        """Create test auth configuration"""
        return AuthConfig(
            auth_service_url="http://test-auth.example.com",
            timeout_seconds=2,
            enable_token_cache=False,  # Disable cache for testing
            verify_ssl=False
        )
    
    @pytest.fixture
    def auth_client(self, auth_config):
        """Create auth client for testing"""
        return AuthClient(auth_config)
    
    @pytest.mark.asyncio
    async def test_validate_token_success(self, auth_client):
        """Test successful token validation"""
        
        # Mock HTTP response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "valid": True,
            "user_id": "123e4567-e89b-12d3-a456-426614174000",
            "tenant_id": "987fcdeb-51a2-43d1-9f4e-123456789abc",
            "permissions": ["read:agents", "write:workflows"]
        }
        
        with patch('httpx.AsyncClient.post', return_value=mock_response):
            validation = await auth_client.validate_token("test-token")
        
        assert validation.valid is True
        assert str(validation.user_id) == "123e4567-e89b-12d3-a456-426614174000"
        assert str(validation.tenant_id) == "987fcdeb-51a2-43d1-9f4e-123456789abc"
        assert "read:agents" in validation.permissions
    
    @pytest.mark.asyncio
    async def test_validate_token_invalid(self, auth_client):
        """Test invalid token validation"""
        
        # Mock HTTP response for invalid token
        mock_response = Mock()
        mock_response.status_code = 401
        
        with patch('httpx.AsyncClient.post', return_value=mock_response):
            validation = await auth_client.validate_token("invalid-token")
        
        assert validation.valid is False
        assert validation.error.error_type == AuthErrorType.INVALID_TOKEN
    
    @pytest.mark.asyncio
    async def test_validate_token_empty(self, auth_client):
        """Test empty token validation"""
        
        validation = await auth_client.validate_token("")
        
        assert validation.valid is False
        assert validation.error.error_type == AuthErrorType.MISSING_TOKEN
    
    @pytest.mark.asyncio
    async def test_validate_token_service_unavailable(self, auth_client):
        """Test token validation when service is unavailable"""
        
        with patch('httpx.AsyncClient.post', side_effect=httpx.RequestError("Connection failed")):
            validation = await auth_client.validate_token("test-token")
        
        assert validation.valid is False
        assert validation.error.error_type == AuthErrorType.SERVICE_UNAVAILABLE
    
    @pytest.mark.asyncio
    async def test_validate_token_timeout(self, auth_client):
        """Test token validation timeout"""
        
        with patch('httpx.AsyncClient.post', side_effect=httpx.TimeoutException("Timeout")):
            validation = await auth_client.validate_token("test-token")
        
        assert validation.valid is False
        assert validation.error.error_type == AuthErrorType.SERVICE_UNAVAILABLE
    
    @pytest.mark.asyncio
    async def test_validate_token_rate_limited(self, auth_client):
        """Test token validation when rate limited"""
        
        # Mock HTTP response for rate limit
        mock_response = Mock()
        mock_response.status_code = 429
        
        with patch('httpx.AsyncClient.post', return_value=mock_response):
            validation = await auth_client.validate_token("test-token")
        
        assert validation.valid is False
        assert validation.error.error_type == AuthErrorType.RATE_LIMIT_EXCEEDED
    
    @pytest.mark.asyncio
    async def test_get_user_context_success(self, auth_client):
        """Test successful user context retrieval"""
        
        # Mock successful validation
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "valid": True,
            "user_id": "123e4567-e89b-12d3-a456-426614174000",
            "tenant_id": "987fcdeb-51a2-43d1-9f4e-123456789abc",
            "permissions": ["read:agents"]
        }
        
        with patch('httpx.AsyncClient.post', return_value=mock_response):
            user_context = await auth_client.get_user_context("test-token")
        
        assert user_context is not None
        assert str(user_context.user_id) == "123e4567-e89b-12d3-a456-426614174000"
        assert str(user_context.tenant_id) == "987fcdeb-51a2-43d1-9f4e-123456789abc"
        assert user_context.has_permission("read:agents") is True
        assert user_context.has_permission("write:agents") is False
    
    @pytest.mark.asyncio
    async def test_get_user_context_invalid_token(self, auth_client):
        """Test user context retrieval with invalid token"""
        
        # Mock invalid token response
        mock_response = Mock()
        mock_response.status_code = 401
        
        with patch('httpx.AsyncClient.post', return_value=mock_response):
            user_context = await auth_client.get_user_context("invalid-token")
        
        assert user_context is None
    
    @pytest.mark.asyncio
    async def test_health_check_success(self, auth_client):
        """Test successful health check"""
        
        # Mock successful health check
        mock_response = Mock()
        mock_response.status_code = 200
        
        with patch('httpx.AsyncClient.get', return_value=mock_response):
            is_healthy = await auth_client.health_check()
        
        assert is_healthy is True
    
    @pytest.mark.asyncio
    async def test_health_check_failure(self, auth_client):
        """Test failed health check"""
        
        with patch('httpx.AsyncClient.get', side_effect=httpx.RequestError("Connection failed")):
            is_healthy = await auth_client.health_check()
        
        assert is_healthy is False
    
    def test_rate_limiting(self, auth_client):
        """Test rate limiting functionality"""
        
        user_context = UserContext(
            user_id=uuid4(),
            tenant_id=uuid4(),
            permissions=["read:agents"],
            rate_limit=2  # Very low limit for testing
        )
        
        # First two requests should succeed
        assert auth_client.check_rate_limit(user_context) is True
        assert auth_client.check_rate_limit(user_context) is True
        
        # Third request should fail
        assert auth_client.check_rate_limit(user_context) is False
        
        # Check rate limit info
        rate_info = auth_client.get_rate_limit_info(user_context)
        assert rate_info.limit == 2
        assert rate_info.remaining == 0
    
    @pytest.mark.asyncio
    async def test_token_caching(self):
        """Test token validation caching"""
        
        config = AuthConfig(
            auth_service_url="http://test-auth.example.com",
            enable_token_cache=True,
            cache_ttl_seconds=60
        )
        auth_client = AuthClient(config)
        
        # Mock successful response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "valid": True,
            "user_id": "123e4567-e89b-12d3-a456-426614174000",
            "permissions": ["read:agents"]
        }
        
        with patch('httpx.AsyncClient.post', return_value=mock_response) as mock_post:
            # First call should hit the auth service
            validation1 = await auth_client.validate_token("test-token")
            assert validation1.valid is True
            assert mock_post.call_count == 1
            
            # Second call should use cache
            validation2 = await auth_client.validate_token("test-token")
            assert validation2.valid is True
            assert mock_post.call_count == 1  # Should still be 1 (cached)
        
        await auth_client.close()
    
    @pytest.mark.asyncio
    async def test_retry_logic(self, auth_client):
        """Test retry logic on request failures"""
        
        # Mock first two calls to fail, third to succeed
        side_effects = [
            httpx.RequestError("Connection failed"),
            httpx.RequestError("Connection failed"),
            Mock(status_code=200, json=lambda: {"valid": True, "user_id": str(uuid4())})
        ]
        
        with patch('httpx.AsyncClient.post', side_effect=side_effects) as mock_post:
            validation = await auth_client.validate_token("test-token")
            
            # Should have retried 3 times total
            assert mock_post.call_count == 3
            assert validation.valid is True
    
    @pytest.mark.asyncio
    async def test_context_manager(self, auth_config):
        """Test auth client as context manager"""
        
        async with AuthClient(auth_config) as client:
            assert client._http_client is not None
            
            # Mock response for validation
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"valid": False}
            
            with patch('httpx.AsyncClient.post', return_value=mock_response):
                validation = await client.validate_token("test-token")
                assert validation.valid is False
        
        # Client should be closed after context manager


class TestUserContext:
    """Test cases for UserContext"""
    
    def test_user_context_permissions(self):
        """Test user context permission checking"""
        
        user_context = UserContext(
            user_id=uuid4(),
            tenant_id=uuid4(),
            permissions=["read:agents", "write:workflows", "admin:tenant"]
        )
        
        # Test single permission
        assert user_context.has_permission("read:agents") is True
        assert user_context.has_permission("delete:agents") is False
        
        # Test any permission
        assert user_context.has_any_permission(["read:agents", "delete:agents"]) is True
        assert user_context.has_any_permission(["delete:agents", "delete:workflows"]) is False
        
        # Test all permissions
        assert user_context.has_all_permissions(["read:agents", "write:workflows"]) is True
        assert user_context.has_all_permissions(["read:agents", "delete:agents"]) is False
    
    def test_user_context_defaults(self):
        """Test user context with default values"""
        
        user_context = UserContext(
            user_id=uuid4(),
            tenant_id=None,
            permissions=["read:agents"]
        )
        
        assert user_context.tenant_id is None
        assert user_context.rate_limit == 1000  # Default
        assert user_context.metadata == {}  # Default


class TestAuthConfig:
    """Test cases for AuthConfig"""
    
    def test_auth_config_defaults(self):
        """Test auth config default values"""
        
        config = AuthConfig()
        
        assert config.auth_service_url == "http://localhost:8000"
        assert config.timeout_seconds == 5
        assert config.enable_token_cache is True
        assert config.cache_ttl_seconds == 300
        assert config.require_https is True
    
    def test_get_validate_url(self):
        """Test validate URL generation"""
        
        config = AuthConfig(
            auth_service_url="https://auth.example.com",
            validate_endpoint="/auth/validate"
        )
        
        assert config.get_validate_url() == "https://auth.example.com/auth/validate"
        
        # Test with trailing slash
        config.auth_service_url = "https://auth.example.com/"
        assert config.get_validate_url() == "https://auth.example.com/auth/validate"


if __name__ == "__main__":
    pytest.main([__file__])