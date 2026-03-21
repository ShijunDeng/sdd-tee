"""Kubernetes Deployment + NodePort publishing."""

from __future__ import annotations

import time
from typing import Any

try:
    from kubernetes import client, config
    from kubernetes.client import ApiException
except ImportError as exc:  # pragma: no cover - optional dep
    _K8S_IMPORT_ERROR = exc
    client = None  # type: ignore[assignment]
    config = None  # type: ignore[assignment]
    ApiException = Exception  # type: ignore[misc,assignment]
else:
    _K8S_IMPORT_ERROR = None


class KubernetesProviderError(RuntimeError):
    """Raised when Kubernetes client is missing or API calls fail."""


class KubernetesProvider:
    """Deploy agent workloads as Deployment + NodePort Service."""

    def __init__(self, kube_context: str | None = None) -> None:
        if _K8S_IMPORT_ERROR is not None:
            raise KubernetesProviderError(
                "kubernetes package is required; install agentcube-cli[k8s]"
            ) from _K8S_IMPORT_ERROR
        try:
            if kube_context:
                config.load_kube_config(context=kube_context)
            else:
                config.load_kube_config()
        except Exception:
            config.load_incluster_config()

        self.apps = client.AppsV1Api()
        self.core = client.CoreV1Api()

    def deploy_agent(
        self,
        name: str,
        namespace: str,
        image: str,
        port: int,
        labels: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Create or patch Deployment and NodePort Service for the agent."""
        labels = labels or {"app": name, "agentcube.io/agent": name}
        deployment = client.V1Deployment(
            metadata=client.V1ObjectMeta(name=name, namespace=namespace, labels=labels),
            spec=client.V1DeploymentSpec(
                replicas=1,
                selector=client.V1LabelSelector(match_labels={"app": name}),
                template=client.V1PodTemplateSpec(
                    metadata=client.V1ObjectMeta(labels={"app": name}),
                    spec=client.V1PodSpec(
                        containers=[
                            client.V1Container(
                                name="agent",
                                image=image,
                                ports=[client.V1ContainerPort(container_port=port)],
                            )
                        ]
                    ),
                ),
            ),
        )
        service = client.V1Service(
            metadata=client.V1ObjectMeta(name=f"{name}-svc", namespace=namespace, labels=labels),
            spec=client.V1ServiceSpec(
                type="NodePort",
                selector={"app": name},
                ports=[client.V1ServicePort(port=port, target_port=port)],
            ),
        )
        try:
            self.apps.create_namespaced_deployment(namespace, deployment)
        except ApiException as e:
            if e.status == 409:
                self.apps.patch_namespaced_deployment(name, namespace, deployment)
            else:
                raise KubernetesProviderError(str(e)) from e
        try:
            self.core.create_namespaced_service(namespace, service)
        except ApiException as e:
            if e.status == 409:
                self.core.patch_namespaced_service(f"{name}-svc", namespace, service)
            else:
                raise KubernetesProviderError(str(e)) from e
        return {"deployment": name, "service": f"{name}-svc", "namespace": namespace}

    def wait_for_deployment_ready(
        self,
        name: str,
        namespace: str,
        timeout_seconds: int = 300,
        poll_interval: float = 2.0,
    ) -> dict[str, Any]:
        """Poll until Deployment reports available replicas."""
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            dep = self.apps.read_namespaced_deployment(name, namespace)
            status = dep.status
            desired = status.replicas or 0
            ready = status.ready_replicas or 0
            if desired > 0 and ready >= desired:
                return {"ready": True, "replicas": desired}
            time.sleep(poll_interval)
        raise KubernetesProviderError(f"Timeout waiting for Deployment/{name} in {namespace}")

    def get_agent_status(self, name: str, namespace: str) -> dict[str, Any]:
        """Summarize Deployment and Service NodePort."""
        try:
            dep = self.apps.read_namespaced_deployment(name, namespace)
        except ApiException as e:
            raise KubernetesProviderError(str(e)) from e
        try:
            svc = self.core.read_namespaced_service(f"{name}-svc", namespace)
        except ApiException:
            svc = None
        node_port: int | None = None
        if svc and svc.spec and svc.spec.ports:
            node_port = svc.spec.ports[0].node_port
        return {
            "deployment": dep.metadata.name,
            "replicas": {
                "desired": dep.status.replicas,
                "ready": dep.status.ready_replicas,
            },
            "node_port": node_port,
        }

    def delete_agent(self, name: str, namespace: str) -> dict[str, Any]:
        """Delete Deployment and associated Service."""
        deleted: list[str] = []
        try:
            self.apps.delete_namespaced_deployment(name, namespace)
            deleted.append(f"deployment/{name}")
        except ApiException as e:
            if e.status != 404:
                raise KubernetesProviderError(str(e)) from e
        try:
            self.core.delete_namespaced_service(f"{name}-svc", namespace)
            deleted.append(f"service/{name}-svc")
        except ApiException as e:
            if e.status != 404:
                raise KubernetesProviderError(str(e)) from e
        return {"deleted": deleted}
