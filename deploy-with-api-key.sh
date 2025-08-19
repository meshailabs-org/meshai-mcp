#!/bin/bash

# Deploy MCP server with custom API key validation

echo "Deploying MeshAI MCP Server with API key validation..."

# Build and push the Docker image
docker build -t gcr.io/meshv1/meshai-mcp-server:latest .
docker push gcr.io/meshv1/meshai-mcp-server:latest

# Deploy to Cloud Run with environment variables
gcloud run deploy meshai-mcp-server-staging \
  --image gcr.io/meshv1/meshai-mcp-server:latest \
  --platform managed \
  --region us-central1 \
  --allow-unauthenticated \
  --set-env-vars="MESHAI_API_URL=https://mesh-runtime-zype6jntia-uc.a.run.app,MESHAI_LOG_LEVEL=INFO,ENVIRONMENT=production,MESHAI_AUTH_SERVICE_URL=https://meshai-admin-dashboard-96062037338.us-central1.run.app" \
  --min-instances=0 \
  --max-instances=10 \
  --memory=1Gi \
  --timeout=60 \
  --port=8080

echo "Deployment complete!"
echo "MCP Server URL: https://meshai-mcp-server-staging-96062037338.us-central1.run.app"