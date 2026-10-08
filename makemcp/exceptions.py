"""Shared exceptions (lightweight, no traceback overhead on hot path)."""


class MakeMCPError(Exception):
    code = -32603

    def __init__(self, message: str, code: int | None = None, data=None):
        super().__init__(message)
        if code is not None:
            self.code = code
        self.data = data


class ToolError(MakeMCPError):
    pass


class ResourceError(MakeMCPError):
    pass


class PromptError(MakeMCPError):
    pass


class AuthError(MakeMCPError):
    code = -32001
