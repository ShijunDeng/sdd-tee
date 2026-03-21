#!/usr/bin/env bash
# Copyright 2026 The Volcano Authors.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT}"

CONTROLLER_GEN="${CONTROLLER_GEN:-}"
if [[ -z "${CONTROLLER_GEN}" ]]; then
  if command -v controller-gen &>/dev/null; then
    CONTROLLER_GEN="controller-gen"
  else
    CONTROLLER_GEN="$(go env GOPATH 2>/dev/null)/bin/controller-gen"
  fi
fi

run_crd() {
  echo ">> controller-gen: CRDs + deepcopy"
  if ! command -v "${CONTROLLER_GEN}" &>/dev/null && [[ ! -x "${CONTROLLER_GEN}" ]]; then
    echo "Install: go install sigs.k8s.io/controller-tools/cmd/controller-gen@latest"
    exit 1
  fi
  mkdir -p "${ROOT}/manifests/charts/base/crds"
  "${CONTROLLER_GEN}" crd:crdVersions=v1 \
    paths="./pkg/apis/..." \
    output:crd:artifacts:config="${ROOT}/manifests/charts/base/crds"
  "${CONTROLLER_GEN}" object:headerFile="${ROOT}/hack/boilerplate.go.txt" paths="./pkg/apis/..."
  echo ">> done"
}

run_client() {
  echo ">> client-gen (k8s.io/code-generator)"
  local cg=""
  for d in "${ROOT}/vendor/k8s.io/code-generator" "$(go env GOPATH 2>/dev/null)/pkg/mod/k8s.io/code-generator@v0.31.3"; do
    if [[ -f "${d}/generate-groups.sh" ]]; then
      cg="${d}/generate-groups.sh"
      break
    fi
  done
  if [[ -z "${cg}" ]]; then
    echo "code-generator not found; run: go mod download && go get k8s.io/code-generator@v0.31.3"
    exit 1
  fi
  bash "${cg}" "deepcopy,client,informer,lister" \
    github.com/volcano-sh/agentcube/client-go \
    github.com/volcano-sh/agentcube/pkg/apis \
    "runtime:v1alpha1,agentsandbox:v1alpha1" \
    --go-header-file "${ROOT}/hack/boilerplate.go.txt" \
    --output-base "${ROOT}/.."
  echo ">> client output under ${ROOT}/../github.com/volcano-sh/agentcube/client-go — move into repo client-go/ or set GOPATH-style tree"
}

case "${1:-all}" in
  crd) run_crd ;;
  client) run_client ;;
  all)
    run_crd
    run_client || echo ">> client generation skipped"
    ;;
  *) echo "usage: $0 [crd|client|all]"; exit 1 ;;
esac
