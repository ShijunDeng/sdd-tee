"""Build container images and bump semver patch."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import semver

from agentcube.services.docker_service import DockerService
from agentcube.services.metadata_service import MetadataService


class BuildRuntime:
    """Local Docker image build with automatic patch version bump."""

    def __init__(self, docker: DockerService | None = None) -> None:
        self.docker = docker or DockerService()

    def build(self, workspace_path: str | Path, **options: Any) -> dict[str, Any]:
        """
        Bump patch version in metadata, build image, persist image ref.

        Options:
            image_prefix: optional registry/repo prefix (default: metadata name)
            tag_as_latest: if True, also tag as latest
        """
        root = Path(workspace_path).resolve()
        svc = MetadataService(root)
        meta = svc.load_metadata()
        ver = semver.Version.parse(meta.version)
        new_ver = str(ver.bump_patch())
        image_prefix = options.get("image_prefix") or meta.name
        tag = options.get("tag") or new_ver
        full_tag = f"{image_prefix}:{tag}"

        result = self.docker.build_image(str(root), full_tag)
        meta = meta.model_copy(update={"version": new_ver, "image": full_tag})
        svc.save_metadata(meta)

        if options.get("tag_as_latest"):
            img = self.docker.client.images.get(full_tag)
            img.tag(image_prefix, tag="latest")

        return {
            "workspace": str(root),
            "version": new_ver,
            "image": full_tag,
            "image_id": result.get("image_id"),
            "logs": result.get("logs", []),
        }
