"""makemcp: a minimal, dependency-free MCP framework for servers and clients."""
from .server import MakeMCP
from .banner import BANNER, TAGLINE, COPYRIGHT
from .types import Tool, Resource, Prompt, TextContent, ImageContent, EmbeddedResource
from .client import MakeMCPClient, Client
from .exceptions import MakeMCPError, ToolError, ResourceError, PromptError, AuthError

__version__ = "1.0.0"
__all__ = [
    "MakeMCP", "Tool", "Resource", "Prompt",
    "TextContent", "ImageContent", "EmbeddedResource",
    "MakeMCPClient", "Client",
    "MakeMCPError", "ToolError", "ResourceError", "PromptError", "AuthError",
    "BANNER", "TAGLINE", "COPYRIGHT",
]
