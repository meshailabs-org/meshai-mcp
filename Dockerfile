# Simple Dockerfile for Cloud Run deployment
FROM python:3.11-slim

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PORT=8080

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    git \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY src/ ./src/
COPY setup.py .
COPY README.md .

# Install the package
RUN pip install -e .

# Expose port
EXPOSE 8080

# Command to run the server in HTTP mode
CMD ["meshai-mcp-server", "serve", "--transport", "http", "--host", "0.0.0.0", "--port", "8080"]