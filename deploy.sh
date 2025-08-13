#!/bin/bash

# MeshAI MCP Server Deployment Script

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Print functions
print_info() {
    echo -e "${BLUE}ℹ️  $1${NC}"
}

print_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
}

# Script information
print_info "MeshAI MCP Server Deployment Script"
echo

# Check if Docker is available
if ! command -v docker &> /dev/null; then
    print_error "Docker is not installed. Please install Docker first."
    exit 1
fi

# Check if docker-compose is available
if ! command -v docker-compose &> /dev/null && ! docker compose version &> /dev/null; then
    print_error "Docker Compose is not installed. Please install Docker Compose first."
    exit 1
fi

# Set compose command
if docker compose version &> /dev/null; then
    COMPOSE_CMD="docker compose"
else
    COMPOSE_CMD="docker-compose"
fi

# Default values
MODE="production"
BUILD_IMAGES="false"
PULL_IMAGES="true"

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --dev|--development)
            MODE="development"
            shift
            ;;
        --build)
            BUILD_IMAGES="true"
            PULL_IMAGES="false"
            shift
            ;;
        --no-pull)
            PULL_IMAGES="false"
            shift
            ;;
        --help|-h)
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --dev, --development    Deploy in development mode"
            echo "  --build                 Build images locally instead of pulling"
            echo "  --no-pull              Don't pull images from registry"
            echo "  --help, -h             Show this help message"
            echo ""
            echo "Environment variables:"
            echo "  MESHAI_API_URL         MeshAI API endpoint (default: http://localhost:8080)"
            echo "  MESHAI_API_KEY         MeshAI API key"
            echo "  MESHAI_LOG_LEVEL       Log level (default: INFO)"
            exit 0
            ;;
        *)
            print_error "Unknown option: $1"
            exit 1
            ;;
    esac
done

print_info "Deploying MeshAI MCP Server in $MODE mode"

# Check environment variables
if [ -z "$MESHAI_API_URL" ]; then
    print_warning "MESHAI_API_URL not set, using default: http://localhost:8080"
    export MESHAI_API_URL="http://localhost:8080"
fi

if [ -z "$MESHAI_API_KEY" ]; then
    print_warning "MESHAI_API_KEY not set. Some features may not work."
fi

if [ -z "$MESHAI_LOG_LEVEL" ]; then
    if [ "$MODE" = "development" ]; then
        export MESHAI_LOG_LEVEL="DEBUG"
    else
        export MESHAI_LOG_LEVEL="INFO"
    fi
fi

# Create .env file if it doesn't exist
if [ ! -f .env ]; then
    print_info "Creating .env file from template"
    cp .env.template .env
    print_warning "Please edit .env file with your configuration"
fi

# Choose compose file
if [ "$MODE" = "development" ]; then
    COMPOSE_FILE="docker-compose.dev.yml"
else
    COMPOSE_FILE="docker-compose.yml"
fi

print_info "Using compose file: $COMPOSE_FILE"

# Build or pull images
if [ "$BUILD_IMAGES" = "true" ]; then
    print_info "Building Docker images..."
    $COMPOSE_CMD -f $COMPOSE_FILE build
    print_success "Images built successfully"
elif [ "$PULL_IMAGES" = "true" ]; then
    print_info "Pulling Docker images..."
    $COMPOSE_CMD -f $COMPOSE_FILE pull || {
        print_warning "Failed to pull images, will try to build locally"
        $COMPOSE_CMD -f $COMPOSE_FILE build
    }
    print_success "Images ready"
fi

# Start services
print_info "Starting MeshAI MCP Server..."
$COMPOSE_CMD -f $COMPOSE_FILE up -d

# Check if services started successfully
sleep 5

if $COMPOSE_CMD -f $COMPOSE_FILE ps | grep -q "meshai-mcp-server.*Up"; then
    print_success "MeshAI MCP Server started successfully!"
    echo
    print_info "Server Details:"
    echo "  • Mode: $MODE"
    echo "  • API URL: $MESHAI_API_URL"
    echo "  • Log Level: $MESHAI_LOG_LEVEL"
    echo
    print_info "Useful Commands:"
    echo "  • View logs: $COMPOSE_CMD -f $COMPOSE_FILE logs -f"
    echo "  • Stop server: $COMPOSE_CMD -f $COMPOSE_FILE down"
    echo "  • Restart server: $COMPOSE_CMD -f $COMPOSE_FILE restart"
    echo "  • View status: $COMPOSE_CMD -f $COMPOSE_FILE ps"
    echo
    
    if [ "$MODE" = "development" ]; then
        print_info "Development Commands:"
        echo "  • Run tests: $COMPOSE_CMD -f $COMPOSE_FILE run --rm mcp-tests"
        echo "  • Start with mock API: $COMPOSE_CMD -f $COMPOSE_FILE --profile mock up"
    fi
    
    echo
    print_info "Claude Code Configuration:"
    echo '  Add this to your MCP configuration:'
    echo '  {'
    echo '    "servers": {'
    echo '      "meshai": {'
    echo '        "command": "docker",'
    echo '        "args": ['
    echo '          "run", "--rm", "-i",'
    echo "          \"-e\", \"MESHAI_API_URL=$MESHAI_API_URL\","
    if [ -n "$MESHAI_API_KEY" ]; then
        echo "          \"-e\", \"MESHAI_API_KEY=$MESHAI_API_KEY\","
    fi
    echo '          "ghcr.io/meshailabs/meshai-mcp-server:latest"'
    echo '        ],'
    echo '        "transport": "stdio"'
    echo '      }'
    echo '    }'
    echo '  }'
else
    print_error "Failed to start MeshAI MCP Server"
    print_info "Checking logs..."
    $COMPOSE_CMD -f $COMPOSE_FILE logs
    exit 1
fi