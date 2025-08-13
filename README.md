# MeshAI MCP Server

[![Build Status](https://github.com/meshailabs/meshai-mcp/workflows/Build%20and%20Push%20Docker%20Images/badge.svg)](https://github.com/meshailabs/meshai-mcp/actions)
[![Docker Image](https://img.shields.io/badge/docker-ghcr.io%2Fmeshailabs%2Fmeshai--mcp--server-blue)](https://ghcr.io/meshailabs/meshai-mcp-server)
[![PyPI version](https://badge.fury.io/py/meshai-mcp-server.svg)](https://badge.fury.io/py/meshai-mcp-server)
[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)

A standalone Model Context Protocol (MCP) server that enables Claude Code and other MCP-compatible tools to leverage MeshAI's multi-agent orchestration capabilities.

## 🚀 Features

- **🤖 Multi-Agent Workflows**: 6 pre-configured workflows for code review, refactoring, debugging, documentation, and more
- **🧠 Intelligent Agent Selection**: Automatically selects appropriate AI agents based on task content
- **🔧 Framework Agnostic**: Works with agents built on LangChain, CrewAI, AutoGen, and other frameworks
- **🐋 Docker Ready**: Full Docker support with development and production configurations
- **📦 Easy Installation**: Available as PyPI package or Docker container
- **🔄 Fallback Protocol**: Works without official MCP package using built-in implementation

## 📋 Quick Start

### Option 1: Docker with stdio (Claude Code)

```bash
# Run with Docker for Claude Code integration
docker run -it \
  -e MESHAI_API_URL=http://localhost:8080 \
  -e MESHAI_API_KEY=your-api-key \
  ghcr.io/meshailabs/meshai-mcp-server:latest

# Or with docker-compose
git clone https://github.com/meshailabs/meshai-mcp.git
cd meshai-mcp
cp .env.template .env  # Edit with your settings
docker-compose up
```

### Option 2: HTTP Server Mode

```bash
# Run as HTTP API server
docker run -p 8080:8080 \
  -e MESHAI_API_URL=http://localhost:8080 \
  ghcr.io/meshailabs/meshai-mcp-server:latest \
  meshai-mcp-server serve --transport http

# Test the HTTP API
curl -H "Authorization: Bearer dev_your-api-key" \
     http://localhost:8080/v1/tools
```

### Option 3: PyPI Installation

```bash
# Install from PyPI
pip install meshai-mcp-server

# Run in stdio mode (for Claude Code)
export MESHAI_API_URL=http://localhost:8080
export MESHAI_API_KEY=your-api-key
meshai-mcp-server

# Or run as HTTP server
meshai-mcp-server serve --transport http --port 8080
```

### Option 4: Development Setup

```bash
# Clone and install
git clone https://github.com/meshailabs/meshai-mcp.git
cd meshai-mcp
pip install -e ".[dev]"

# Run in development mode
python -m meshai_mcp.cli serve --dev --transport http
```

## 🔧 Configuration

### Environment Variables

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `MESHAI_API_URL` | MeshAI API endpoint | `http://localhost:8080` | Yes |
| `MESHAI_API_KEY` | API key for authentication | None | For stdio mode |
| `MESHAI_LOG_LEVEL` | Logging level | `INFO` | No |

### 🔐 Authentication

#### For HTTP Mode:
- **API Key Required**: Pass via `Authorization: Bearer YOUR_API_KEY` header
- **Development Keys**: Use `dev_` prefix for testing (e.g., `dev_test123`)
- **Rate Limiting**: 100 requests/hour for development, configurable for production

#### For stdio Mode:
- **Environment Variable**: Set `MESHAI_API_KEY` for backend communication
- **No HTTP Auth**: Authentication handled by Claude Code

### Claude Code Integration

#### stdio Transport (Recommended):

```json
{
  "servers": {
    "meshai": {
      "command": "docker",
      "args": [
        "run", "--rm", "-i",
        "-e", "MESHAI_API_URL=${MESHAI_API_URL}",
        "-e", "MESHAI_API_KEY=${MESHAI_API_KEY}",
        "ghcr.io/meshailabs/meshai-mcp-server:latest"
      ],
      "transport": "stdio"
    }
  }
}
```

#### HTTP Transport (For hosted deployments):

```json
{
  "servers": {
    "meshai": {
      "command": "curl",
      "args": [
        "-X", "POST",
        "-H", "Authorization: Bearer ${MESHAI_MCP_API_KEY}",
        "-H", "Content-Type: application/json",
        "-d", "@-",
        "https://your-mcp-server.com/v1/mcp"
      ],
      "transport": "http"
    }
  }
}
```

#### Local pip Installation:

```json
{
  "servers": {
    "meshai": {
      "command": "meshai-mcp-server",
      "transport": "stdio",
      "env": {
        "MESHAI_API_URL": "${MESHAI_API_URL}",
        "MESHAI_API_KEY": "${MESHAI_API_KEY}"
      }
    }
  }
}
```

## 🛠️ Available Workflows

### 1. Code Review (`mesh_code_review`)
Comprehensive code review with security and best practices analysis.
- **Agents**: code-reviewer, security-analyzer, best-practices-advisor

### 2. Refactor & Optimize (`mesh_refactor_optimize`)
Refactor code with performance optimization and test generation.
- **Agents**: code-optimizer, performance-analyzer, test-generator

### 3. Debug & Fix (`mesh_debug_fix`)
Debug issues and generate tests for fixes.
- **Agents**: debugger-expert, log-analyzer, test-generator

### 4. Document & Explain (`mesh_document_explain`)
Generate documentation and explanations with examples.
- **Agents**: doc-writer, code-explainer, example-generator

### 5. Architecture Review (`mesh_architecture_review`)
Comprehensive architecture analysis and recommendations.
- **Agents**: system-architect, performance-analyst, security-auditor

### 6. Feature Development (`mesh_feature_development`)
End-to-end feature development from design to testing.
- **Agents**: product-designer, senior-developer, test-engineer, doc-writer

## 🌐 HTTP API Usage

### Starting HTTP Server

```bash
# Using Docker
docker run -p 8080:8080 \
  -e MESHAI_API_URL=http://localhost:8080 \
  ghcr.io/meshailabs/meshai-mcp-server:latest \
  meshai-mcp-server serve --transport http

# Using pip
meshai-mcp-server serve --transport http --port 8080
```

### API Endpoints

| Endpoint | Method | Description | Auth Required |
|----------|--------|-------------|---------------|
| `/health` | GET | Health check | No |
| `/v1/tools` | GET | List available tools | Yes |
| `/v1/workflows` | GET | List workflows | Yes |
| `/v1/resources` | GET | List resources | Yes |
| `/v1/mcp` | POST | Execute MCP request | Yes |
| `/v1/stats` | GET | Usage statistics | Yes |
| `/docs` | GET | API documentation | No |

### Usage Examples

```bash
# Health check (no auth required)
curl http://localhost:8080/health

# List available tools
curl -H "Authorization: Bearer dev_test123" \
     http://localhost:8080/v1/tools

# Execute a workflow
curl -X POST \
     -H "Authorization: Bearer dev_test123" \
     -H "Content-Type: application/json" \
     -d '{"method":"mesh_code_review","id":"test","params":{"files":"app.py"}}' \
     http://localhost:8080/v1/mcp

# Get usage stats
curl -H "Authorization: Bearer dev_test123" \
     http://localhost:8080/v1/stats
```

## 🐋 Docker Deployment

### Development Setup

```bash
# Development with hot reload
docker-compose -f docker-compose.dev.yml up

# Run tests
docker-compose -f docker-compose.dev.yml run --rm mcp-tests

# With mock API
docker-compose -f docker-compose.dev.yml --profile mock up
```

### Production Considerations

For production deployment:
- Use proper API key management
- Set up rate limiting and monitoring
- Configure HTTPS/TLS termination
- Implement proper logging and metrics
- Consider using a reverse proxy (nginx, Traefik)
- Set resource limits and scaling policies

## 🧪 Development

### Setup Development Environment

```bash
# Clone repository
git clone https://github.com/meshailabs/meshai-mcp.git
cd meshai-mcp

# Install in development mode
pip install -e ".[dev]"

# Install pre-commit hooks
pre-commit install

# Run tests
pytest tests/ -v

# Run with coverage
pytest tests/ -v --cov=src/meshai_mcp --cov-report=html
```

### Code Quality

```bash
# Format code
black src tests
isort src tests

# Type checking
mypy src/meshai_mcp

# Linting
flake8 src tests
```

### Building Docker Images

```bash
# Build production image
docker build -t meshai-mcp-server .

# Build development image
docker build -f Dockerfile.dev --target development -t meshai-mcp-server:dev .

# Multi-architecture build
docker buildx build --platform linux/amd64,linux/arm64 -t meshai-mcp-server:multi .
```

## 📚 Documentation

- [MCP Protocol Specification](https://spec.modelcontextprotocol.io/)
- [Claude Code Documentation](https://docs.anthropic.com/claude/docs/claude-code)
- [MeshAI Platform Documentation](https://docs.meshai.dev)

## 🤝 Contributing

We welcome contributions! Please see our [Contributing Guide](CONTRIBUTING.md) for details.

### Development Workflow

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests for new functionality
5. Run the test suite
6. Submit a pull request

## 📝 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🆘 Support

- GitHub Issues: [Report bugs or request features](https://github.com/meshailabs/meshai-mcp/issues)
- Documentation: [docs.meshai.dev](https://docs.meshai.dev)
- Discord: [Join our community](https://discord.gg/meshai)

## 🗺️ Roadmap

- [ ] HTTP transport support for MCP
- [ ] WebSocket transport for real-time communication
- [ ] Custom workflow configuration via YAML
- [ ] Plugin system for custom agents
- [ ] Prometheus metrics integration
- [ ] Official MCP package integration when available

---

Built with ❤️ by the [MeshAI Labs](https://meshai.dev) team.
