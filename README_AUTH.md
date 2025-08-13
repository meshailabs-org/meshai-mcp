# MeshAI MCP Server Authentication

This document describes how the MeshAI MCP Server integrates with the secure MeshAI authentication service.

## Overview

The MCP server now requires authentication for all API endpoints (except health checks and documentation). Authentication is handled by calling the secure MeshAI authentication service - **no sensitive security code is contained in this public repository**.

## Security Architecture

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│  MCP Client     │───▶│  MCP Server     │───▶│  Auth Service   │
│  (Public)       │    │  (Public)       │    │  (Private Repo) │
└─────────────────┘    └─────────────────┘    └─────────────────┘
       │                       │                       │
       │ Bearer Token          │ Token Validation      │ JWT + Database
       │                       │ HTTP Request          │ Full Security Logic
       │                       │                       │
       └───────────────────────┼───────────────────────┘
                               │
                         ✓ Safe Integration
                         ✗ No Security Code
                         ✗ No Secrets/Keys
```

## Environment Configuration

Set these environment variables to configure authentication:

```bash
# Required: MeshAI authentication service URL
MESHAI_AUTH_SERVICE_URL=https://auth.meshai.com

# Optional: Authentication client settings
AUTH_TIMEOUT_SECONDS=5
ENABLE_TOKEN_CACHE=true
TOKEN_CACHE_TTL=300
REQUIRE_HTTPS=true
VERIFY_SSL=true
```

## How It Works

### 1. Token Validation Flow

1. Client sends request with `Authorization: Bearer <token>` header
2. MCP server extracts token from request
3. MCP server calls auth service: `POST /auth/validate {"token": "<token>"}`
4. Auth service validates token and returns user context
5. MCP server processes request with authenticated user context

### 2. Rate Limiting

- Rate limits are enforced per-user based on their subscription plan
- Rate limit info is returned in response headers:
  - `X-RateLimit-Limit`: Requests per hour limit
  - `X-RateLimit-Remaining`: Remaining requests
  - `X-RateLimit-Reset`: Reset time (Unix timestamp)

### 3. User Context

Authenticated requests include user context:

```json
{
  "user_id": "123e4567-e89b-12d3-a456-426614174000",
  "tenant_id": "987fcdeb-51a2-43d1-9f4e-123456789abc",
  "permissions": ["read:agents", "write:workflows"],
  "rate_limit": 1000
}
```

## API Endpoints

### Authentication Required

All endpoints under `/v1/` require authentication:

- `POST /v1/mcp` - MCP protocol requests
- `GET /v1/tools` - List available tools
- `GET /v1/resources` - List available resources
- `GET /v1/workflows` - List workflows
- `GET /v1/user/info` - Get user information

### Public Endpoints

These endpoints do not require authentication:

- `GET /` - API information
- `GET /health` - Health check
- `GET /docs` - API documentation
- `GET /redoc` - Alternative documentation

## Usage Examples

### 1. Basic Request

```bash
curl -X POST "http://localhost:8080/v1/mcp" \
  -H "Authorization: Bearer your-auth-token" \
  -H "Content-Type: application/json" \
  -d '{
    "type": "request",
    "method": "tools/list",
    "id": "1",
    "params": {}
  }'
```

### 2. Check User Info

```bash
curl -X GET "http://localhost:8080/v1/user/info" \
  -H "Authorization: Bearer your-auth-token"
```

### 3. Health Check (No Auth)

```bash
curl -X GET "http://localhost:8080/health"
```

## Error Responses

### 401 Unauthorized

```json
{
  "error": "Unauthorized",
  "message": "Invalid or expired token"
}
```

### 403 Forbidden

```json
{
  "error": "Authorization failed",
  "detail": "Missing permissions: write:agents"
}
```

### 429 Rate Limited

```json
{
  "error": "Rate limit exceeded",
  "limit": 1000,
  "reset": 1640995200
}
```

## Security Notes

### What's Safe (In Public Repo)

✅ **Authentication Client**: Validates tokens by calling auth service  
✅ **Rate Limiting**: Simple in-memory rate limiting  
✅ **Token Caching**: Caches validation results to reduce auth service calls  
✅ **Error Handling**: Safe error responses without leaking information  
✅ **Middleware**: Request processing and user context injection  

### What's NOT Here (In Private Repo)

❌ **JWT Secrets**: All JWT signing/verification keys  
❌ **Password Hashing**: Bcrypt and password security logic  
❌ **Database Access**: User/tenant data and permissions  
❌ **Token Generation**: Creating new tokens  
❌ **Security Configuration**: Encryption keys, security settings  

## Development & Testing

### Running Locally

1. Start the MeshAI auth service (private repo)
2. Set environment variables
3. Start MCP server:

```bash
cd meshai-mcp
python -m meshai_mcp.http_server
```

### Testing Authentication

Use development tokens for testing:

```bash
# This will work with default development setup
curl -X GET "http://localhost:8080/v1/user/info" \
  -H "Authorization: Bearer dev_test_token_123"
```

## Integration with Other Services

The MCP server can be integrated with other MeshAI services:

1. **Agent Registry**: Access user's registered agents
2. **Workflow Engine**: Execute authenticated workflows  
3. **Analytics**: Track usage per user/tenant
4. **Billing**: Enforce plan limits and usage

All integrations use the same secure authentication flow.

## Troubleshooting

### Common Issues

1. **"Authentication service unavailable"**
   - Check `MESHAI_AUTH_SERVICE_URL` environment variable
   - Verify auth service is running and accessible
   - Check network connectivity

2. **"Invalid or expired token"**
   - Token may be malformed or expired
   - Check token format: should be JWT or API key
   - Verify token is still valid in auth service

3. **"Rate limit exceeded"**
   - User has exceeded their plan's rate limit
   - Check rate limit headers in previous responses
   - Wait for rate limit reset time

### Health Check

Check if authentication is working:

```bash
curl "http://localhost:8080/health"
```

Response includes auth service status:

```json
{
  "status": "healthy",
  "service": "meshai-mcp-server",
  "auth_service": "healthy",
  "timestamp": "2025-01-13T10:00:00Z"
}
```