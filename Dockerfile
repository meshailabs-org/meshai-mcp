# MeshAI MCP Server Dockerfile
FROM python:3.11-slim

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Create application user
RUN groupadd --gid 1000 meshai && \
    useradd --uid 1000 --gid meshai --shell /bin/bash --create-home meshai

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY src/ ./src/
COPY setup.py .
COPY README.md .
COPY LICENSE .

# Install the package
RUN pip install -e .

# Change ownership to meshai user
RUN chown -R meshai:meshai /app

# Switch to non-root user
USER meshai

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD echo '{"type":"request","method":"list_tools","id":"health"}' | python -m meshai_mcp.server || exit 1

# Expose port for HTTP mode (if needed later)
EXPOSE 8080

# Default command
CMD ["meshai-mcp-server"]