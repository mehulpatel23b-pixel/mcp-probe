"""Exceptions used across mcp-probe."""


class MCPError(Exception):
    """Base class for all mcp-probe errors."""


class MCPConnectionError(MCPError):
    """The server process could not be started or the connection died."""


class MCPProtocolError(MCPError):
    """The server answered with a JSON-RPC error or a malformed frame."""


class MCPTimeoutError(MCPError):
    """The server did not answer within the configured timeout."""
