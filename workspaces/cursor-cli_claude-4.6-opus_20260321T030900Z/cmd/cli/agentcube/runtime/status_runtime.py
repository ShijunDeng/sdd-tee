"""Aggregate deployment status for an agent workspace."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from agentcube.services.agentcube_provider import AgentCubeProvider
from agentcube.services.k8s_provider import KubernetesProvider
from agentcube.services.metadata_service import MetadataService


class StatusRuntime:
    """Read Kubernetes or AgentRuntime status keyed by workspace metadata."""

    def get_status(self, workspace_path: str | Path, provider: str | None = None) -> dict[str, Any]:
        """
        Return provider-specific status.

        If provider is None, uses metadata label ``publish_provider`` when set, else ``k8s``.
        """
        root = Path(workspace_path).resolve()
        svc = MetadataService(root)
        meta = svc.load_metadata()
        prov = provider or meta.labels.get("publish_provider") or "k8s"
        kube_context = meta.labels.get("kube_context")
        name = meta.name
        namespace = meta.namespace

        if prov == "agentcube":
            ac = AgentCubeProvider(kube_context=kube_context)
            cr = ac.get_agent_runtime(name, namespace)
            return {"provider": prov, "agent_runtime": cr}
        k8s = KubernetesProvider(kube_context=kube_context)
        st = k8s.get_agent_status(name, namespace)
        return {"provider": prov, **st}
