"""Core data containers (slots for speed + low memory)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass(slots=True)
class TextContent:
    text: str
    type: str = "text"

    def to_dict(self) -> dict:
        return {"type": "text", "text": self.text}


@dataclass(slots=True)
class ImageContent:
    data: str  # base64
    mimeType: str = "image/png"
    type: str = "image"

    def to_dict(self) -> dict:
        return {"type": "image", "data": self.data, "mimeType": self.mimeType}


@dataclass(slots=True)
class EmbeddedResource:
    uri: str
    text: str | None = None
    mimeType: str = "text/plain"
    type: str = "resource"

    def to_dict(self) -> dict:
        d = {"type": "resource", "resource": {"uri": self.uri, "mimeType": self.mimeType}}
        if self.text is not None:
            d["resource"]["text"] = self.text
        return d


@dataclass(slots=True)
class Tool:
    name: str
    fn: Callable
    description: str = ""
    schema: dict = field(default_factory=dict)
    tags: set = field(default_factory=set)
    cache_ttl: float | None = None
    timeout: float | None = None
    is_async: bool = False

    def to_dict(self) -> dict:
        return {"name": self.name, "description": self.description,
                "inputSchema": self.schema}


@dataclass(slots=True)
class Resource:
    uri: str
    fn: Callable
    name: str = ""
    description: str = ""
    mimeType: str = "text/plain"
    is_async: bool = False

    def to_dict(self) -> dict:
        return {"uri": self.uri, "name": self.name or self.uri,
                "description": self.description, "mimeType": self.mimeType}


@dataclass(slots=True)
class Prompt:
    name: str
    fn: Callable
    description: str = ""
    arguments: list = field(default_factory=list)
    is_async: bool = False

    def to_dict(self) -> dict:
        return {"name": self.name, "description": self.description,
                "arguments": self.arguments}
