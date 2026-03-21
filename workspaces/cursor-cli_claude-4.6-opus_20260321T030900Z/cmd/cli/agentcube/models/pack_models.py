"""Pack-time options and metadata helpers."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class MetadataOptions:
    """Options used when packing or updating agent workspace metadata."""

    name: str = "agent"
    version: str = "0.1.0"
    description: str = ""
    author: str = ""
    base_image: str = "python:3.11-slim"
    port: int = 8080
    entrypoint: str | None = None
    cmd: list[str] | None = None
    env: dict[str, str] = field(default_factory=dict)
    labels: dict[str, str] = field(default_factory=dict)
    image: str = ""
    namespace: str = "default"
    kube_context: str | None = None

    @classmethod
    def from_options(cls, options: dict[str, Any] | None = None, **kwargs: Any) -> MetadataOptions:
        """Build from a mapping, CLI kwargs, or both (kwargs override mapping)."""
        data: dict[str, Any] = {}
        if options:
            data.update(options)
        data.update(kwargs)
        known = {
            "name",
            "version",
            "description",
            "author",
            "base_image",
            "port",
            "entrypoint",
            "cmd",
            "env",
            "labels",
            "image",
            "namespace",
            "kube_context",
        }
        filtered = {k: v for k, v in data.items() if k in known}
        return cls(**filtered)
