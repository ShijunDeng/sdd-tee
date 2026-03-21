"""AgentRuntime custom resource publishing."""

from __future__ import annotations

from typing import Any

try:
    from kubernetes import client, config
    from kubernetes.client import ApiException
except ImportError as exc:  # pragma: no cover
    _K8S_IMPORT_ERROR = exc
    client = None  # type: ignore[assignment]
    config = None  # type: ignore[assignment]
    ApiException = Exception  # type: ignore[misc,assignment]
else:
    _K8S_IMPORT_ERROR = None

AGENTRUNTIME_GROUP = "agentcube.io"
AGENTRUNTIME_VERSION = "v1alpha1"
AGENTRUNTIME_PLURAL = "agentruntimes"


class AgentCubeProviderError(RuntimeError):
    """Raised when CR operations fail."""


class AgentCubeProvider:
    """Manage AgentRuntime CRs via the Kubernetes custom objects API."""

    def __init__(self, kube_context: str | None = None) -> None:
        if _K8S_IMPORT_ERROR is not None:
            raise AgentCubeProviderError(
                "kubernetes package is required; install agentcube-cli[k8s]"
            ) from _K8S_IMPORT_ERROR
        try:
            if kube_context:
                config.load_kube_config(context=kube_context)
            else:
                config.load_kube_config()
        except Exception:
            config.load_incluster_config()
        self.custom = client.CustomObjectsApi()

    def deploy_agent_runtime(
        self,
        name: str,
        namespace: str,
        image: str,
        port: int,
        labels: dict[str, str] | None = None,
        extra_spec: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Create or replace an AgentRuntime custom resource."""
        body: dict[str, Any] = {
            "apiVersion": f"{AGENTRUNTIME_GROUP}/{AGENTRUNTIME_VERSION}",
            "kind": "AgentRuntime",
            "metadata": {
                "name": name,
                "namespace": namespace,
                "labels": labels or {},
            },
            "spec": {
                "image": image,
                "port": port,
                **(extra_spec or {}),
            },
        }
        try:
            self.custom.create_namespaced_custom_object(
                group=AGENTRUNTIME_GROUP,
                version=AGENTRUNTIME_VERSION,
                namespace=namespace,
                plural=AGENTRUNTIME_PLURAL,
                body=body,
            )
        except ApiException as e:
            if e.status == 409:
                self.custom.replace_namespaced_custom_object(
                    group=AGENTRUNTIME_GROUP,
                    version=AGENTRUNTIME_VERSION,
                    namespace=namespace,
                    plural=AGENTRUNTIME_PLURAL,
                    name=name,
                    body=body,
                )
            else:
                raise AgentCubeProviderError(str(e)) from e
        return {"name": name, "namespace": namespace, "kind": "AgentRuntime"}

    def get_agent_runtime(self, name: str, namespace: str) -> dict[str, Any]:
        """Fetch AgentRuntime status."""
        try:
            return self.custom.get_namespaced_custom_object(
                group=AGENTRUNTIME_GROUP,
                version=AGENTRUNTIME_VERSION,
                namespace=namespace,
                plural=AGENTRUNTIME_PLURAL,
                name=name,
            )
        except ApiException as e:
            raise AgentCubeProviderError(str(e)) from e
