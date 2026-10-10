"""makemcp: a minimal, dependency-free MCP framework for servers and clients."""
from .server import MakeMCP
from .banner import BANNER, TAGLINE, COPYRIGHT
from .convert import (python_to_app, openapi_to_app, commands_to_app,
                      github_to_app, parse_github_target, summarize_app,
                      config_to_app, convert_target, analyze_target,
                      render_server_module)
from .types import Tool, Resource, Prompt, TextContent, ImageContent, EmbeddedResource
from .client import MakeMCPClient, Client
from .exceptions import MakeMCPError, ToolError, ResourceError, PromptError, AuthError

__version__ = "1.3.1"
__all__ = [
    "MakeMCP", "Tool", "Resource", "Prompt",
    "TextContent", "ImageContent", "EmbeddedResource",
    "MakeMCPClient", "Client",
    "MakeMCPError", "ToolError", "ResourceError", "PromptError", "AuthError",
    "BANNER", "TAGLINE", "COPYRIGHT",
    "python_to_app", "openapi_to_app", "commands_to_app",
    "github_to_app", "parse_github_target", "summarize_app",
    "config_to_app", "convert_target", "analyze_target",
    "render_server_module",
]
