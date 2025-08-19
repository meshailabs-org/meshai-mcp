#!/bin/bash
# MeshAI MCP Cloud Proxy for Claude Desktop
# This script proxies stdio MCP requests to the cloud-deployed HTTP server

# Configuration
MCP_SERVER_URL="https://meshai-mcp-server-staging-zype6jntia-uc.a.run.app"
API_KEY="${MESHAI_API_KEY:-msk_YOUR_KEY_HERE}"

# Read from stdin and forward to HTTP server
while IFS= read -r line; do
    # Send the request to the cloud server
    response=$(echo "$line" | curl -s -X POST \
        -H "Content-Type: application/json" \
        -H "Authorization: Bearer $API_KEY" \
        -d @- \
        "$MCP_SERVER_URL/v1/mcp")
    
    # Output the response
    echo "$response"
done