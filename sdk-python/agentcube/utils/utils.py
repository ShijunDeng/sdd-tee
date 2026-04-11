"""Utility functions for AgentCube SDK."""


def read_token_from_file(file_path: str) -> str:
    """Read and return the contents of a token file.

    Args:
        file_path: Path to the token file

    Returns:
        Stripped contents of the file, or empty string if file not found
    """
    try:
        with open(file_path, 'r') as f:
            return f.read().strip()
    except FileNotFoundError:
        return ""
