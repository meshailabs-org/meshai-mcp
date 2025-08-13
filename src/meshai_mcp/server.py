"""
MeshAI MCP Server for Claude Code Integration

This MCP server enables Claude Code to orchestrate multiple AI agents
through the Model Context Protocol (MCP) standard.
"""

import asyncio
import json
import logging
import os
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, asdict
import httpx
import structlog

logger = structlog.get_logger(__name__)

# MCP Protocol imports - use official package if available, otherwise use fallback
try:
    from mcp.server import Server
    from mcp.types import (
        Resource, Tool, TextContent, ImageContent,
        CallToolRequest, CallToolResult, GetResourceRequest,
        ListResourcesRequest, ListToolsRequest
    )
    from mcp.server.stdio import stdio_server
    MCP_AVAILABLE = True
except ImportError:
    logger.info("Official MCP package not found, using fallback implementation")
    from .protocol import (
        Server, Resource, Tool, TextContent, ImageContent,
        CallToolRequest, CallToolResult, GetResourceRequest,
        ListResourcesRequest, ListToolsRequest, stdio_server
    )
    MCP_AVAILABLE = False


@dataclass
class MeshAIWorkflow:
    """Represents a MeshAI workflow available through MCP."""
    name: str
    agents: List[str]
    description: str
    parameters: Dict[str, Any] = None


class MeshAIMCPServer:
    """
    MCP Server that bridges Claude Code with MeshAI's multi-agent orchestration.
    
    This server exposes MeshAI capabilities as MCP tools and resources,
    allowing Claude Code to seamlessly orchestrate multiple AI agents.
    """
    
    def __init__(self):
        self.server = Server("meshai")
        self.mesh_endpoint = os.getenv("MESHAI_API_URL", "http://localhost:8080")
        self.api_key = os.getenv("MESHAI_API_KEY")
        
        # Define available workflows
        self.workflows = {
            "code-review": MeshAIWorkflow(
                name="code-review",
                agents=["code-reviewer", "security-analyzer", "best-practices-advisor"],
                description="Comprehensive code review with security and best practices analysis",
                parameters={
                    "files": "List of files to review",
                    "depth": "Review depth: standard, comprehensive, security-focused",
                    "focus_areas": "Specific areas to focus on (optional)"
                }
            ),
            "refactor-optimize": MeshAIWorkflow(
                name="refactor-optimize", 
                agents=["code-optimizer", "performance-analyzer", "test-generator"],
                description="Refactor code with performance optimization and test generation",
                parameters={
                    "files": "Files to refactor",
                    "goals": "Refactoring goals: performance, readability, maintainability",
                    "preserve_api": "Whether to preserve existing API contracts"
                }
            ),
            "debug-fix": MeshAIWorkflow(
                name="debug-fix",
                agents=["debugger-expert", "log-analyzer", "test-generator"],
                description="Debug issues and generate tests for fixes",
                parameters={
                    "issue_description": "Description of the bug or issue",
                    "error_logs": "Error logs or stack traces (optional)",
                    "affected_files": "Files that might be affected"
                }
            ),
            "document-explain": MeshAIWorkflow(
                name="document-explain",
                agents=["doc-writer", "code-explainer", "example-generator"],
                description="Generate documentation and explanations with examples",
                parameters={
                    "files": "Files to document",
                    "audience": "Target audience: developers, users, contributors",
                    "style": "Documentation style: api, tutorial, reference"
                }
            ),
            "architecture-review": MeshAIWorkflow(
                name="architecture-review",
                agents=["system-architect", "performance-analyst", "security-auditor"],
                description="Comprehensive architecture analysis and recommendations",
                parameters={
                    "scope": "Architecture scope: module, service, system",
                    "focus": "Analysis focus: scalability, security, performance",
                    "constraints": "Any architectural constraints or requirements"
                }
            ),
            "feature-development": MeshAIWorkflow(
                name="feature-development", 
                agents=["product-designer", "senior-developer", "test-engineer", "doc-writer"],
                description="End-to-end feature development from design to testing",
                parameters={
                    "feature_description": "Detailed feature description",
                    "requirements": "Functional and non-functional requirements",
                    "include_tests": "Whether to generate tests",
                    "include_docs": "Whether to generate documentation"
                }
            )
        }
        
        self._register_handlers()
    
    def _register_handlers(self):
        """Register MCP protocol handlers."""
        
        @self.server.list_resources()
        async def list_resources() -> List[Resource]:
            """List available MeshAI resources."""
            resources = []
            
            # Workflow definitions as resources
            for workflow_name, workflow in self.workflows.items():
                resources.append(Resource(
                    uri=f"meshai://workflow/{workflow_name}",
                    name=f"MeshAI Workflow: {workflow.name}",
                    description=workflow.description,
                    mimeType="application/json"
                ))
            
            # Agent registry as resource
            resources.append(Resource(
                uri="meshai://agents/registry",
                name="MeshAI Agent Registry",
                description="Available AI agents in the MeshAI registry",
                mimeType="application/json"
            ))
            
            return resources
        
        @self.server.get_resource()
        async def get_resource(request: GetResourceRequest) -> str:
            """Get MeshAI resource content."""
            uri = request.uri
            
            if uri.startswith("meshai://workflow/"):
                workflow_name = uri.split("/")[-1]
                if workflow_name in self.workflows:
                    workflow = self.workflows[workflow_name]
                    return json.dumps(asdict(workflow), indent=2)
                else:
                    raise ValueError(f"Workflow not found: {workflow_name}")
            
            elif uri == "meshai://agents/registry":
                # Fetch available agents from MeshAI registry
                try:
                    async with httpx.AsyncClient() as client:
                        response = await client.get(
                            f"{self.mesh_endpoint}/agents",
                            headers={"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
                        )
                        if response.status_code == 200:
                            return response.text
                        else:
                            return json.dumps({"error": "Failed to fetch agent registry"})
                except Exception as e:
                    return json.dumps({"error": str(e)})
            
            else:
                raise ValueError(f"Unknown resource URI: {uri}")
        
        @self.server.list_tools()
        async def list_tools() -> List[Tool]:
            """List available MeshAI tools."""
            tools = []
            
            # Multi-agent execution tool
            tools.append(Tool(
                name="mesh_execute",
                description="Execute a task using MeshAI's multi-agent orchestration",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "task": {
                            "type": "string",
                            "description": "Task description for the agents to execute"
                        },
                        "workflow": {
                            "type": "string", 
                            "description": "Predefined workflow name (optional)",
                            "enum": list(self.workflows.keys())
                        },
                        "agents": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Specific agents to use (optional, overrides workflow)"
                        },
                        "context": {
                            "type": "object",
                            "description": "Additional context for the task (file contents, project info, etc.)"
                        },
                        "routing_strategy": {
                            "type": "string",
                            "description": "How agents should collaborate",
                            "enum": ["sequential", "parallel", "collaborative", "hierarchical"],
                            "default": "collaborative"
                        }
                    },
                    "required": ["task"]
                }
            ))
            
            # Workflow-specific tools
            for workflow_name, workflow in self.workflows.items():
                tools.append(Tool(
                    name=f"mesh_{workflow_name.replace('-', '_')}",
                    description=f"Execute {workflow.description}",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            **{param: {"type": "string", "description": desc} 
                               for param, desc in (workflow.parameters or {}).items()},
                            "context": {
                                "type": "object",
                                "description": "Additional context (file contents, etc.)"
                            }
                        },
                        "required": list((workflow.parameters or {}).keys())[:1]  # First param required
                    }
                ))
            
            # Agent discovery tool
            tools.append(Tool(
                name="mesh_discover_agents",
                description="Discover available agents and their capabilities",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "capability": {
                            "type": "string",
                            "description": "Filter agents by capability (optional)"
                        },
                        "framework": {
                            "type": "string", 
                            "description": "Filter agents by framework (optional)"
                        }
                    }
                }
            ))
            
            return tools
        
        @self.server.call_tool()
        async def call_tool(request: CallToolRequest) -> CallToolResult:
            """Execute MeshAI tools."""
            tool_name = request.params.name
            arguments = request.params.arguments or {}
            
            try:
                if tool_name == "mesh_execute":
                    result = await self._execute_multi_agent_task(
                        task=arguments.get("task"),
                        workflow=arguments.get("workflow"),
                        agents=arguments.get("agents"),
                        context=arguments.get("context", {}),
                        routing_strategy=arguments.get("routing_strategy", "collaborative")
                    )
                
                elif tool_name == "mesh_discover_agents":
                    result = await self._discover_agents(
                        capability=arguments.get("capability"),
                        framework=arguments.get("framework")
                    )
                
                elif tool_name.startswith("mesh_") and tool_name != "mesh_execute":
                    # Workflow-specific tool
                    workflow_name = tool_name[5:].replace("_", "-")  # Remove "mesh_" prefix
                    if workflow_name in self.workflows:
                        workflow = self.workflows[workflow_name]
                        
                        # Build task description from workflow and arguments
                        task = f"Execute {workflow.description}"
                        if arguments:
                            task += f" with parameters: {arguments}"
                        
                        result = await self._execute_multi_agent_task(
                            task=task,
                            workflow=workflow_name,
                            context=arguments.get("context", {}),
                            routing_strategy="collaborative"
                        )
                    else:
                        result = {"error": f"Unknown workflow: {workflow_name}"}
                
                else:
                    result = {"error": f"Unknown tool: {tool_name}"}
                
                # Format result for MCP
                content = []
                if "error" in result:
                    content.append(TextContent(
                        type="text",
                        text=f"❌ Error: {result['error']}"
                    ))
                else:
                    # Format successful result
                    formatted_result = self._format_result_for_claude_code(result)
                    content.append(TextContent(
                        type="text", 
                        text=formatted_result
                    ))
                
                return CallToolResult(content=content)
                
            except Exception as e:
                logger.error(f"Tool execution failed: {e}")
                return CallToolResult(
                    content=[TextContent(type="text", text=f"❌ Tool execution failed: {str(e)}")]
                )
    
    async def _execute_multi_agent_task(
        self,
        task: str,
        workflow: str = None,
        agents: List[str] = None,
        context: Dict[str, Any] = None,
        routing_strategy: str = "collaborative"
    ) -> Dict[str, Any]:
        """Execute a task using MeshAI's multi-agent orchestration."""
        
        try:
            # Determine agents to use
            if agents:
                target_agents = agents
            elif workflow and workflow in self.workflows:
                target_agents = self.workflows[workflow].agents
                logger.info(f"Using workflow '{workflow}' with agents: {target_agents}")
            else:
                # Auto-select agents based on task
                target_agents = await self._auto_select_agents(task)
            
            # Prepare context
            enhanced_context = {
                "claude_code_integration": True,
                "original_task": task,
                "mcp_request": True,
                **(context or {})
            }
            
            # Prepare task payload
            payload = {
                "task": task,
                "agents": target_agents,
                "context": enhanced_context,
                "routing_strategy": routing_strategy,
                "return_intermediate": True,
                "claude_code_mcp": True
            }
            
            # Execute through MeshAI
            async with httpx.AsyncClient(timeout=180.0) as client:
                response = await client.post(
                    f"{self.mesh_endpoint}/multi-agent/execute",
                    json=payload,
                    headers={"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
                )
                
                if response.status_code == 200:
                    result = response.json()
                    return result
                else:
                    logger.error(f"MeshAI request failed: {response.status_code}")
                    return {"error": f"MeshAI request failed: {response.text}"}
                    
        except Exception as e:
            logger.error(f"Multi-agent task execution failed: {e}")
            return {"error": str(e)}
    
    async def _discover_agents(
        self,
        capability: str = None,
        framework: str = None
    ) -> Dict[str, Any]:
        """Discover available agents in MeshAI registry."""
        
        try:
            params = {}
            if capability:
                params["capability"] = capability
            if framework:
                params["framework"] = framework
            
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.mesh_endpoint}/agents",
                    params=params,
                    headers={"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
                )
                
                if response.status_code == 200:
                    return response.json()
                else:
                    return {"error": f"Agent discovery failed: {response.text}"}
                    
        except Exception as e:
            return {"error": str(e)}
    
    async def _auto_select_agents(self, task: str) -> List[str]:
        """Auto-select appropriate agents based on task content."""
        task_lower = task.lower()
        selected_agents = []
        
        # Code review keywords
        if any(keyword in task_lower for keyword in ["review", "analyze", "check", "audit"]):
            selected_agents.append("code-reviewer")
        
        # Security keywords
        if any(keyword in task_lower for keyword in ["security", "vulnerability", "safe"]):
            selected_agents.append("security-analyzer")
        
        # Performance keywords  
        if any(keyword in task_lower for keyword in ["optimize", "performance", "speed", "memory"]):
            selected_agents.append("performance-optimizer")
        
        # Testing keywords
        if any(keyword in task_lower for keyword in ["test", "spec", "coverage"]):
            selected_agents.append("test-generator")
        
        # Documentation keywords
        if any(keyword in task_lower for keyword in ["document", "explain", "comment", "readme"]):
            selected_agents.append("doc-writer")
        
        # Debugging keywords
        if any(keyword in task_lower for keyword in ["debug", "fix", "error", "bug"]):
            selected_agents.append("debugger-expert")
        
        # Architecture keywords
        if any(keyword in task_lower for keyword in ["architecture", "design", "structure"]):
            selected_agents.append("system-architect")
        
        # Default to code-reviewer if no specific agents identified
        if not selected_agents:
            selected_agents = ["code-reviewer"]
        
        logger.info(f"Auto-selected agents for task: {selected_agents}")
        return selected_agents
    
    def _format_result_for_claude_code(self, result: Dict[str, Any]) -> str:
        """Format MeshAI results for Claude Code display."""
        
        if "error" in result:
            return f"❌ Error: {result['error']}"
        
        output = "🤖 **Multi-Agent Task Results**\n\n"
        
        if "agent_results" in result:
            agents_used = list(result["agent_results"].keys())
            output += f"**Agents Used:** {', '.join(agents_used)}\n\n"
            
            for agent_id, agent_result in result["agent_results"].items():
                agent_name = agent_id.replace("-", " ").title()
                output += f"## 🔹 {agent_name}\n\n"
                output += f"{agent_result.get('result', 'No result available')}\n\n"
                
                # Add recommendations if available
                if "recommendations" in agent_result:
                    output += "**Recommendations:**\n"
                    for rec in agent_result["recommendations"]:
                        output += f"• {rec}\n"
                    output += "\n"
        
        # Add summary if available
        if "summary" in result:
            output += f"## 📋 Summary\n\n{result['summary']}\n\n"
        
        return output
    
    async def serve(self, transport: str = "stdio"):
        """Start the MCP server."""
        logger.info(f"Starting MeshAI MCP server with {transport} transport")
        logger.info(f"Using {'official' if MCP_AVAILABLE else 'fallback'} MCP implementation")
        
        if transport == "stdio":
            # Serve over stdio (standard for local MCP servers)
            await stdio_server(self.server)
        else:
            raise ValueError(f"Unsupported transport: {transport}")


# Main entry point for MCP server
async def main():
    """Main entry point for MeshAI MCP server."""
    server = MeshAIMCPServer()
    await server.serve()


if __name__ == "__main__":
    asyncio.run(main())