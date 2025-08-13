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

### Option 1: Docker (Recommended)

```bash
# Run with Docker
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

### Option 2: PyPI Installation

```bash
# Install from PyPI
pip install meshai-mcp-server

# Run the server
export MESHAI_API_URL=http://localhost:8080
export MESHAI_API_KEY=your-api-key
meshai-mcp-server
```

### Option 3: Development Setup

```bash
# Clone and install
git clone https://github.com/meshailabs/meshai-mcp.git
cd meshai-mcp
pip install -e ".[dev]"

# Run in development mode
python -m meshai_mcp.server --dev
```

## 🔧 Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `MESHAI_API_URL` | MeshAI API endpoint | `http://localhost:8080` |
| `MESHAI_API_KEY` | API key for authentication | None |
| `MESHAI_LOG_LEVEL` | Logging level | `INFO` |

### Claude Code Integration

Add to your Claude Code MCP configuration:

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

Or if installed via pip:

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

## 🐋 Docker Deployment

### Production Deployment

```bash
# Using docker-compose
docker-compose -f docker-compose.yml up -d

# Using Docker directly
docker run -d \
  --name meshai-mcp-server \
  --restart unless-stopped \
  -e MESHAI_API_URL=https://api.meshai.dev \
  -e MESHAI_API_KEY=your-production-key \
  ghcr.io/meshailabs/meshai-mcp-server:latest
```

### Development with Hot Reload

```bash
# Development setup
docker-compose -f docker-compose.dev.yml up

# Run tests
docker-compose -f docker-compose.dev.yml run --rm mcp-tests

# With mock API
docker-compose -f docker-compose.dev.yml --profile mock up
```

### Kubernetes Deployment

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: meshai-mcp-server
spec:
  replicas: 3
  selector:
    matchLabels:
      app: meshai-mcp-server
  template:
    metadata:
      labels:
        app: meshai-mcp-server
    spec:
      containers:
      - name: meshai-mcp-server
        image: ghcr.io/meshailabs/meshai-mcp-server:latest
        env:
        - name: MESHAI_API_URL
          value: "https://api.meshai.dev"
        - name: MESHAI_API_KEY
          valueFrom:
            secretKeyRef:
              name: meshai-secrets
              key: api-key
        resources:
          requests:
            memory: "128Mi"
            cpu: "100m"
          limits:
            memory: "256Mi"
            cpu: "200m"
```

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
