"""Typed errors for AgentCube SDK clients."""


class AgentCubeError(Exception):
    """Base error for SDK operations."""


class SessionError(AgentCubeError):
    """Control-plane session lifecycle failures."""


class DataPlaneError(AgentCubeError):
    """Data-plane HTTP or protocol failures."""


class CommandExecutionError(DataPlaneError):
    """Remote command exited non-zero."""

    def __init__(self, message: str, *, exit_code: int, stderr: str, command: str) -> None:
        super().__init__(message)
        self.exit_code = exit_code
        self.stderr = stderr
        self.command = command
