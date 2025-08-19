# Claude Desktop Configuration for Cloud-Deployed MeshAI MCP Server

## Server Details
- **MCP Server URL**: https://meshai-mcp-server-staging-zype6jntia-uc.a.run.app
- **Health Check**: https://meshai-mcp-server-staging-zype6jntia-uc.a.run.app/health
- **Transport**: HTTP with Bearer token authentication

## Step 1: Get Your API Key

1. Go to: https://admin-dashboard-zype6jntia-uc.a.run.app
2. Navigate to the "API Keys" tab
3. Click "Create API Key"
4. Name it (e.g., "Claude Desktop MCP")
5. Save the generated key (starts with `msk_`)

## Step 2: Configure Claude Desktop

### Option A: Direct HTTP Configuration (Try This First)

Add this to your Claude Desktop configuration file:

```json
{
  "mcpServers": {
    "meshai": {
      "url": "https://meshai-mcp-server-staging-zype6jntia-uc.a.run.app/v1/mcp",
      "transport": "http",
      "headers": {
        "Authorization": "Bearer msk_YOUR_ACTUAL_KEY_HERE"
      }
    }
  }
}
```

### Option B: Using Python Proxy (If Option A doesn't work)

1. Install requests if needed:
   ```bash
   pip install requests
   ```

2. Configure Claude Desktop to use the proxy script:

   ```json
   {
     "mcpServers": {
       "meshai": {
         "command": "python3",
         "args": ["/path/to/meshai-mcp/claude-desktop-proxy.py"],
         "transport": "stdio",
         "env": {
           "MESHAI_API_KEY": "msk_YOUR_ACTUAL_KEY_HERE"
         }
       }
     }
   }
   ```

### Option C: Using cURL (Alternative)

```json
{
  "mcpServers": {
    "meshai": {
      "command": "bash",
      "args": ["-c", "while read line; do echo \"$line\" | curl -s -X POST -H 'Content-Type: application/json' -H 'Authorization: Bearer msk_YOUR_KEY_HERE' -d @- https://meshai-mcp-server-staging-zype6jntia-uc.a.run.app/v1/mcp; done"],
      "transport": "stdio"
    }
  }
}
```

## Step 3: Test Your Configuration

After configuring Claude Desktop, you should be able to use these MeshAI workflows:

- `mesh_code_review` - Comprehensive code review
- `mesh_refactor_optimize` - Code refactoring and optimization
- `mesh_debug_fix` - Debug and fix issues
- `mesh_document_explain` - Documentation generation
- `mesh_architecture_review` - Architecture analysis
- `mesh_feature_development` - Feature development

## Testing the Connection

You can test the MCP server directly with:

```bash
# Test health endpoint
curl https://meshai-mcp-server-staging-zype6jntia-uc.a.run.app/health

# Test with your API key (list available tools)
curl -X POST https://meshai-mcp-server-staging-zype6jntia-uc.a.run.app/v1/mcp \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer msk_YOUR_KEY_HERE" \
  -d '{"jsonrpc":"2.0","method":"tools/list","id":1}'
```

## Troubleshooting

1. **401 Unauthorized**: Check your API key is correct and starts with `msk_`
2. **Connection refused**: Ensure the URL is correct
3. **No response**: Check if the service is running at https://meshai-mcp-server-staging-zype6jntia-uc.a.run.app/health

## Support

- Dashboard: https://admin-dashboard-zype6jntia-uc.a.run.app
- API Keys Management: https://admin-dashboard-zype6jntia-uc.a.run.app (API Keys tab)
- Service Status: https://meshai-mcp-server-staging-zype6jntia-uc.a.run.app/health