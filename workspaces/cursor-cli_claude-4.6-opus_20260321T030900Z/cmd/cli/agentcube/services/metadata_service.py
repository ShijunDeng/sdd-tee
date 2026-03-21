"""Load, validate, and persist agent_metadata.yaml."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, field_validator

METADATA_FILENAME = "agent_metadata.yaml"


class AgentMetadata(BaseModel):
    """Schema for agent_metadata.yaml in a workspace."""

    name: str = Field(..., min_length=1, description="Logical agent name.")
    version: str = Field(default="0.1.0", description="Semver agent version.")
    description: str = ""
    author: str = ""
    image: str = Field(default="", description="Full container image reference after build.")
    base_image: str = Field(default="python:3.11-slim", alias="baseImage")
    port: int = Field(default=8080, ge=1, le=65535)
    entrypoint: str | None = None
    cmd: list[str] | None = None
    env: dict[str, str] = Field(default_factory=dict)
    labels: dict[str, str] = Field(default_factory=dict)
    namespace: str = Field(default="default", description="Default Kubernetes namespace.")
    endpoint: str = Field(default="", description="HTTP endpoint for invoke, if known.")

    model_config = {"populate_by_name": True, "extra": "ignore"}

    @field_validator("version")
    @classmethod
    def _semverish(cls, v: str) -> str:
        if not re.match(r"^\d+\.\d+\.\d+(-[0-9A-Za-z.-]+)?(\+[0-9A-Za-z.-]+)?$", v):
            raise ValueError(f"version must look like semver major.minor.patch, got {v!r}")
        return v

    def model_dump_yaml(self) -> str:
        """Serialize to YAML with camelCase aliases where applicable."""
        data = self.model_dump(by_alias=True, exclude_none=True)
        return yaml.safe_dump(data, sort_keys=False, default_flow_style=False)


class MetadataService:
    """Filesystem operations for agent metadata."""

    def __init__(self, workspace_path: Path) -> None:
        self.workspace_path = workspace_path.resolve()
        self.metadata_path = self.workspace_path / METADATA_FILENAME

    def load_metadata(self) -> AgentMetadata:
        """Load metadata from disk or raise FileNotFoundError."""
        if not self.metadata_path.is_file():
            raise FileNotFoundError(f"Missing {self.metadata_path}")
        raw = yaml.safe_load(self.metadata_path.read_text(encoding="utf-8")) or {}
        return AgentMetadata.model_validate(raw)

    def save_metadata(self, metadata: AgentMetadata) -> None:
        """Write metadata atomically."""
        self.metadata_path.write_text(metadata.model_dump_yaml(), encoding="utf-8")

    def update_metadata(self, **fields: Any) -> AgentMetadata:
        """Merge fields into existing metadata (or defaults) and persist."""
        if self.metadata_path.is_file():
            current = self.load_metadata()
            data = current.model_dump()
        else:
            data = AgentMetadata(name="agent").model_dump()
        incoming_labels = fields.get("labels")
        if incoming_labels is not None and isinstance(incoming_labels, dict):
            merged = dict(data.get("labels") or {})
            merged.update(incoming_labels)
            fields = {**fields, "labels": merged}
        data.update({k: v for k, v in fields.items() if v is not None})
        updated = AgentMetadata.model_validate(data)
        self.save_metadata(updated)
        return updated

    def validate_workspace(self) -> list[str]:
        """Return a list of validation issues (empty if ok)."""
        issues: list[str] = []
        if not self.workspace_path.is_dir():
            issues.append(f"Workspace is not a directory: {self.workspace_path}")
            return issues
        if not self.metadata_path.is_file():
            issues.append(f"Missing {METADATA_FILENAME}")
        else:
            try:
                self.load_metadata()
            except Exception as exc:  # noqa: BLE001 — surface validation errors
                issues.append(f"Invalid {METADATA_FILENAME}: {exc}")
        dockerfile = self.workspace_path / "Dockerfile"
        if not dockerfile.is_file():
            issues.append("Dockerfile missing (run pack)")
        return issues
