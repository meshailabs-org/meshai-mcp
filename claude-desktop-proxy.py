#!/usr/bin/env python3
"""
MeshAI MCP Cloud Proxy for Claude Desktop
Proxies stdio MCP requests to the cloud-deployed HTTP server
"""

import sys
import json
import os
import requests
from typing import Dict, Any

# Configuration
MCP_SERVER_URL = "https://meshai-mcp-server-staging-zype6jntia-uc.a.run.app"
API_KEY = os.environ.get("MESHAI_API_KEY", "msk_YOUR_KEY_HERE")

def proxy_request():
    """Read JSON-RPC from stdin and forward to HTTP server"""
    
    # Set up session with auth headers
    session = requests.Session()
    session.headers.update({
        "Content-Type": "application/json",
        "Authorization": f"Bearer {API_KEY}"
    })
    
    # Process incoming requests
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
            
        try:
            # Parse the JSON-RPC request
            request = json.loads(line)
            
            # Forward to cloud server
            response = session.post(
                f"{MCP_SERVER_URL}/v1/mcp",
                json=request,
                timeout=30
            )
            
            # Return the response
            if response.status_code == 200:
                print(json.dumps(response.json()))
            else:
                # Return error in JSON-RPC format
                error_response = {
                    "jsonrpc": "2.0",
                    "id": request.get("id"),
                    "error": {
                        "code": response.status_code,
                        "message": f"HTTP {response.status_code}",
                        "data": response.text
                    }
                }
                print(json.dumps(error_response))
                
            sys.stdout.flush()
            
        except json.JSONDecodeError as e:
            # Return parsing error
            error_response = {
                "jsonrpc": "2.0",
                "id": None,
                "error": {
                    "code": -32700,
                    "message": "Parse error",
                    "data": str(e)
                }
            }
            print(json.dumps(error_response))
            sys.stdout.flush()
            
        except Exception as e:
            # Return general error
            error_response = {
                "jsonrpc": "2.0",
                "id": None,
                "error": {
                    "code": -32603,
                    "message": "Internal error",
                    "data": str(e)
                }
            }
            print(json.dumps(error_response))
            sys.stdout.flush()

if __name__ == "__main__":
    proxy_request()