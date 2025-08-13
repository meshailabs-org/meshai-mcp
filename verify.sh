#!/bin/bash

# MeshAI MCP Server Verification Script

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

print_info() {
    echo -e "${BLUE}ℹ️  $1${NC}"
}

print_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
}

print_info "Verifying MeshAI MCP Server setup..."
echo

# Check if all required files exist
REQUIRED_FILES=(
    "src/meshai_mcp/__init__.py"
    "src/meshai_mcp/server.py"
    "src/meshai_mcp/protocol.py"
    "src/meshai_mcp/cli.py"
    "requirements.txt"
    "setup.py"
    "Dockerfile"
    "docker-compose.yml"
    "tests/test_mcp_server.py"
    ".github/workflows/docker-build.yml"
)

ALL_GOOD=true

for file in "${REQUIRED_FILES[@]}"; do
    if [ -f "$file" ]; then
        print_success "File exists: $file"
    else
        print_error "Missing file: $file"
        ALL_GOOD=false
    fi
done

echo

# Check directory structure
REQUIRED_DIRS=(
    "src/meshai_mcp"
    "tests"
    ".github/workflows"
)

for dir in "${REQUIRED_DIRS[@]}"; do
    if [ -d "$dir" ]; then
        print_success "Directory exists: $dir"
    else
        print_error "Missing directory: $dir"
        ALL_GOOD=false
    fi
done

echo

# Check if Python files have basic syntax
if command -v python3 &> /dev/null; then
    print_info "Checking Python syntax..."
    
    for py_file in src/meshai_mcp/*.py tests/*.py; do
        if [ -f "$py_file" ]; then
            if python3 -m py_compile "$py_file" 2>/dev/null; then
                print_success "Syntax OK: $py_file"
            else
                print_error "Syntax error: $py_file"
                ALL_GOOD=false
            fi
        fi
    done
else
    print_info "Python3 not found, skipping syntax check"
fi

echo

# Check Docker setup
if command -v docker &> /dev/null; then
    print_success "Docker is available"
    
    # Check if we can build the image
    print_info "Testing Docker build..."
    if docker build -t meshai-mcp-test . > /dev/null 2>&1; then
        print_success "Docker build successful"
        docker rmi meshai-mcp-test > /dev/null 2>&1 || true
    else
        print_error "Docker build failed"
        ALL_GOOD=false
    fi
else
    print_error "Docker not found"
    ALL_GOOD=false
fi

echo

# Summary
if [ "$ALL_GOOD" = true ]; then
    print_success "🎉 All checks passed! MeshAI MCP Server is ready to deploy."
    echo
    print_info "Next steps:"
    echo "  1. Set environment variables in .env file"
    echo "  2. Run: ./deploy.sh"
    echo "  3. Configure Claude Code to use the MCP server"
else
    print_error "❌ Some checks failed. Please fix the issues above."
    exit 1
fi