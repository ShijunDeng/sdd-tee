#!/usr/bin/env bash
# End-to-end runner: kind cluster, CRDs, optional Helm deploy, Go e2e tests.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
CLUSTER_NAME="${KIND_CLUSTER_NAME:-agentcube-e2e}"
SKIP_HELM="${AGENTCUBE_E2E_SKIP_HELM:-1}"
NAMESPACE="${AGENTCUBE_E2E_NAMESPACE:-agentcube-e2e}"

export PATH="${PATH:-}"

if ! command -v kind >/dev/null 2>&1; then
  echo "kind is required (https://kind.sigs.k8s.io/)." >&2
  exit 1
fi

if ! kind get clusters 2>/dev/null | grep -qx "${CLUSTER_NAME}"; then
  echo ">> Creating kind cluster ${CLUSTER_NAME}"
  kind create cluster --name "${CLUSTER_NAME}"
fi

echo ">> Applying CRDs"
kubectl apply -f "${ROOT}/manifests/charts/base/crds/"

if [[ "${SKIP_HELM}" != "1" ]]; then
  if ! command -v helm >/dev/null 2>&1; then
    echo "helm not found; set AGENTCUBE_E2E_SKIP_HELM=1 to skip chart install." >&2
    exit 1
  fi
  echo ">> Installing Helm chart into ${NAMESPACE}"
  kubectl create namespace "${NAMESPACE}" 2>/dev/null || true
  helm upgrade --install agentcube "${ROOT}/manifests/charts/base" \
    --namespace "${NAMESPACE}" --create-namespace --wait --timeout 10m
fi

echo ">> Running Go e2e tests"
cd "${ROOT}"
go test -tags=e2e -count=1 -v ./test/e2e/... "${@}"
