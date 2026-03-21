"""General utilities."""

from __future__ import annotations

from pathlib import Path


def read_token_from_file(path: str | Path) -> str:
    """Read a bearer token or API key from disk, stripping whitespace."""
    p = Path(path).expanduser()
    if not p.is_file():
        raise FileNotFoundError(f"Token file not found: {p}")
    return p.read_text(encoding="utf-8").strip()
