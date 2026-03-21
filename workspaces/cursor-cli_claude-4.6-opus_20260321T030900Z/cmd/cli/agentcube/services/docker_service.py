"""Docker SDK wrapper for local image lifecycle."""

from __future__ import annotations

from typing import Any

import docker
from docker.errors import DockerException


class DockerService:
    """Build, inspect, push, and remove images via docker-py."""

    def __init__(self) -> None:
        self._client: docker.DockerClient | None = None

    @property
    def client(self) -> docker.DockerClient:
        if self._client is None:
            self._client = docker.from_env()
        return self._client

    def check_docker_available(self) -> bool:
        """Return True if the Docker daemon responds to ping."""
        try:
            self.client.ping()
        except DockerException:
            return False
        return True

    def build_image(
        self,
        context_path: str,
        tag: str,
        dockerfile: str = "Dockerfile",
        build_args: dict[str, str] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Build an image from context; returns build summary."""
        if not self.check_docker_available():
            raise DockerException("Docker daemon is not available")
        image, log_iter = self.client.images.build(
            path=context_path,
            tag=tag,
            dockerfile=dockerfile,
            buildargs=build_args or {},
            rm=True,
            **kwargs,
        )
        logs = [str(line) for line in log_iter]
        return {"image_id": image.id, "tag": tag, "logs": logs}

    def get_image_info(self, tag_or_id: str) -> dict[str, Any]:
        """Return id, tags, size, and created for an image."""
        img = self.client.images.get(tag_or_id)
        attrs = img.attrs
        return {
            "id": img.id,
            "tags": attrs.get("RepoTags") or [],
            "size": attrs.get("Size"),
            "created": attrs.get("Created"),
        }

    def push_image(self, repository: str, tag: str | None = None) -> list[str]:
        """Push image; returns streamed log lines."""
        if not self.check_docker_available():
            raise DockerException("Docker daemon is not available")
        lines: list[str] = []
        for line in self.client.images.push(repository, tag=tag, stream=True, decode=True):
            lines.append(str(line))
        return lines

    def remove_image(self, tag_or_id: str, force: bool = False) -> None:
        """Remove a local image."""
        self.client.images.remove(tag_or_id, force=force)
