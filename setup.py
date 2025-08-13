#!/usr/bin/env python3
"""
MeshAI MCP Server Setup
Model Context Protocol server for AI agent orchestration
"""

from setuptools import setup, find_packages
import os

# Read version from __init__.py
def get_version():
    init_file = os.path.join(os.path.dirname(__file__), 'src', 'meshai_mcp', '__init__.py')
    with open(init_file, 'r') as f:
        for line in f:
            if line.startswith('__version__'):
                return line.split('=')[1].strip().strip('"\'')
    return '0.1.0'

# Read README
def get_long_description():
    readme_file = os.path.join(os.path.dirname(__file__), 'README.md')
    if os.path.exists(readme_file):
        with open(readme_file, 'r', encoding='utf-8') as f:
            return f.read()
    return "MeshAI MCP Server for Claude Code and other MCP-compatible tools"

setup(
    name="meshai-mcp-server",
    version=get_version(),
    author="MeshAI Labs",
    author_email="dev@meshai.dev",
    description="Model Context Protocol server for MeshAI multi-agent orchestration",
    long_description=get_long_description(),
    long_description_content_type="text/markdown",
    url="https://github.com/meshailabs/meshai-mcp",
    project_urls={
        "Bug Tracker": "https://github.com/meshailabs/meshai-mcp/issues",
        "Documentation": "https://docs.meshai.dev/mcp",
        "Source": "https://github.com/meshailabs/meshai-mcp",
        "MeshAI Platform": "https://meshai.dev",
    },
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "Topic :: Software Development :: Libraries :: Python Modules",
        "Topic :: Scientific/Engineering :: Artificial Intelligence",
        "Topic :: Communications :: Chat",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Operating System :: OS Independent",
        "Environment :: Console",
    ],
    package_dir={"": "src"},
    packages=find_packages(where="src"),
    python_requires=">=3.8",
    install_requires=[
        "httpx>=0.25.0",
        "structlog>=23.2.0",
        "pydantic>=2.5.0",
        "websockets>=11.0.0",
        "tenacity>=8.2.0",
        "python-dotenv>=1.0.0",
        "click>=8.0.0",
        "rich>=13.0.0",
    ],
    extras_require={
        "dev": [
            "pytest>=7.4.0",
            "pytest-asyncio>=0.21.0",
            "pytest-mock>=3.12.0",
            "pytest-cov>=4.0.0",
            "black>=23.0.0",
            "isort>=5.12.0",
            "flake8>=6.0.0",
            "mypy>=1.0.0",
            "watchdog>=3.0.0",
            "pre-commit>=3.0.0",
        ],
        "docs": [
            "mkdocs>=1.5.0",
            "mkdocs-material>=9.0.0",
            "mkdocs-mermaid2-plugin>=1.0.0",
        ],
        "mcp": [
            # Official MCP package when available
            # "mcp>=0.1.0",
        ],
    },
    entry_points={
        "console_scripts": [
            "meshai-mcp-server=meshai_mcp.server:main",
            "meshai-mcp=meshai_mcp.cli:main",
        ],
    },
    include_package_data=True,
    package_data={
        "meshai_mcp": ["config/*.json", "config/*.yaml"],
    },
    keywords=[
        "ai", "agents", "mcp", "claude", "orchestration", 
        "multi-agent", "protocol", "meshai", "automation"
    ],
    zip_safe=False,
)