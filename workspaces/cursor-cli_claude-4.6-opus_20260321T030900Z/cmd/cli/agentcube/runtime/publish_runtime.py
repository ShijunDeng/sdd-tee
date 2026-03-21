"""Publish agents to AgentRuntime CR or plain Kubernetes."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from agentcube.services.agentcube_provider import AgentCubeProvider
from agentcube.services.k8s_provider import KubernetesProvider
from agentcube.services.metadata_service import MetadataService


class PublishRuntime:
    """Route publish to the selected provider."""

    def publish(self, workspace_path: str | Path, **options: Any) -> dict[str, Any]:
        """
        Deploy using provider.

        Required options:
            provider: 'agentcube' | 'k8s'
        """
        root = Path(workspace_path).resolve()
        svc = MetadataService(root)
        meta = svc.load_metadata()
        if not meta.image:
            raise ValueError("metadata.image is empty; run build first")

        provider = options.get("provider")
        if provider not in ("agentcube", "k8s"):
            raise ValueError("provider must be 'agentcube' or 'k8s'")

        kube_context = options.get("kube_context") or meta.labels.get("kube_context")
        namespace = options.get("namespace") or meta.namespace
        name = options.get("name") or meta.name
        labels = {**meta.labels, **(options.get("labels") or {})}
        if provider:
            labels.setdefault("publish_provider", provider)

        if provider == "agentcube":
            ac = AgentCubeProvider(kube_context=kube_context)
            out = ac.deploy_agent_runtime(
                name=name,
                namespace=namespace,
                image=meta.image,
                port=meta.port,
                labels=labels,
                extra_spec=options.get("extra_spec"),
            )
        else:
            k8s = KubernetesProvider(kube_context=kube_context)
            out = k8s.deploy_agent(
                name=name,
                namespace=namespace,
                image=meta.image,
                port=meta.port,
                labels=labels,
            )
            if options.get("wait", True):
                k8s.wait_for_deployment_ready(name, namespace)
        svc.update_metadata(labels=labels)
        return {"provider": provider, **out}
