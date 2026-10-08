"""makemcp: fast, stdlib-only MCP framework (faster & lighter than fastmcp)."""
from .server import MakeMCP
from .types import Tool, Resource, Prompt, TextContent, ImageContent, EmbeddedResource
from .client import MakeMCPClient, Client
from .exceptions import MakeMCPError, ToolError, ResourceError, PromptError, AuthError

__version__ = "1.0.0"
__all__ = [
    "MakeMCP", "Tool", "Resource", "Prompt",
    "TextContent", "ImageContent", "EmbeddedResource",
    "MakeMCPClient", "Client",
    "MakeMCPError", "ToolError", "ResourceError", "PromptError", "AuthError",
]
