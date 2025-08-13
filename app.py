#!/usr/bin/env python3
"""
Simple test application for Cloud Run deployment
"""

import os
from fastapi import FastAPI
from fastapi.responses import JSONResponse

app = FastAPI(title="MeshAI MCP Server Test")

@app.get("/")
async def root():
    return {"message": "MeshAI MCP Server is running", "status": "ok"}

@app.get("/health")
async def health():
    return {"status": "healthy", "environment": os.getenv("ENVIRONMENT", "unknown")}

@app.get("/v1/tools")
async def list_tools():
    return {
        "tools": [
            {"name": "test_tool", "description": "A test tool for verification"}
        ]
    }

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)