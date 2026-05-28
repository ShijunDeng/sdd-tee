#!/usr/bin/env python3
"""
SDD-TEE v5.1 Benchmark Engine

Drives the full 8-stage SDD workflow (ST-0 to ST-7) for each AR,
with accurate per-stage token tracking via LiteLLM Proxy.

Token data flow:
  1. Engine starts LiteLLM Proxy (or uses existing one)
  2. For each AR × stage: adapter runs CLI tool, CLI routes through proxy
  3. Engine records stage start/end timestamps
  4. Auditor filters LiteLLM JSONL log by time window → exact per-stage tokens
  5. Output is a schema-compliant _full.json with real token data

Usage:
  # Run with LiteLLM proxy (recommended — accurate token data)
  python3 scripts/engine.py --tool claude-code --model claude-sonnet-4 \
    --api-base http://localhost:4000 --specs-dir specs/

  # Run without proxy (token data depends on CLI tool native support)
  python3 scripts/engine.py --tool claude-code --model claude-sonnet-4 \
    --specs-dir specs/

  # Test with single AR (no real API calls)
  python3 scripts/engine.py --tool claude-code --model claude-sonnet-4 \
    --ar-limit 1 --dry-run-prompts
"""

import argparse
import fnmatch
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# ─── Setup paths ──────────────────────────────────────────────────────────

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE / "scripts"))

from schema import STAGES
from auditor import TokenAuditor, get_pricing, compute_token_cost
from equivalence import EquivalenceChecker, EquivalenceResult

# ─── AR catalog ───────────────────────────────────────────────────────────

# Import from report.py (the canonical source of AR catalog)
_mod = __import__("report")
AR_CATALOG = _mod.AR_CATALOG

STAGE_NAMES_MAP = {
    "ST-0": "AR 输入",
    "ST-1": "需求澄清",
    "ST-2": "Spec 增量设计",
    "ST-3": "Design 增量设计",
    "ST-4": "任务拆解",
    "ST-5": "开发实现",
    "ST-6": "一致性验证",
    "ST-6.5": "原始代码等价性验证",
    "ST-7": "合并归档",
}

DEFAULT_ORIGINAL_REPO = "https://github.com/ShijunDeng/agentcube.git"
DEFAULT_WORKSPACE_ROOT = BASE.parent / f"{BASE.name}-workspaces"

SOURCE_EXTS_BY_LANG = {
    "Go": {".go", ".mod", ".sum"},
    "Python": {".py", ".toml", ".txt", ".yaml", ".yml"},
    "YAML": {".yaml", ".yml"},
    "Dockerfile": {".dockerfile"},
    "Makefile": {".mk"},
    "TypeScript": {".ts", ".tsx", ".js", ".jsx", ".json", ".md", ".mdx", ".css"},
    "Markdown": {".md", ".mdx"},
}

IMPLEMENTATION_SUPPORT_NAMES = {
    "Dockerfile", "Makefile", "requirements.txt", "pyproject.toml",
    "package.json", "package-lock.json", "pnpm-lock.yaml", "yarn.lock",
}
IMPLEMENTATION_SUPPORT_EXTS = {
    ".yaml", ".yml", ".json", ".toml", ".txt", ".dockerfile",
}

SKIP_SCAN_DIRS = {
    ".git", "__pycache__", ".mypy_cache", "vendor", "node_modules",
    "agentcube-src", ".pytest_cache", ".opencode",
    ".docusaurus", "build", "dist", "coverage",
}

GENERATED_ARTIFACT_DIRS = {
    "__pycache__", ".pytest_cache", ".mypy_cache",
    "htmlcov", "node_modules", ".docusaurus", "build", "dist", "coverage",
}
LOCKFILE_NAMES = {"package-lock.json", "pnpm-lock.yaml", "yarn.lock"}
GENERATED_CACHE_FILE_NAMES = {".coverage"}
GENERATED_BINARY_NAMES = {
    "agentcube-agentd",
    "agentcube-router",
    "agentcube-workload-manager",
    "agentcube-picod",
    "kubectl-agentcube",
    "workload-manager",
    "router",
    "picod",
    "agentd",
}
GENERATED_ARTIFACT_FILES = LOCKFILE_NAMES | GENERATED_CACHE_FILE_NAMES | GENERATED_BINARY_NAMES
NON_BLOCKING_GENERATED_ARTIFACT_DIRS = {"__pycache__", ".pytest_cache", ".mypy_cache", "htmlcov"}
NON_BLOCKING_GENERATED_ARTIFACT_FILES = {".coverage"}

PLACEHOLDER_MARKER_RE = re.compile(r"\b(?:TODO|FIXME|XXX)\b")
PLACEHOLDER_PATTERNS = [
    "NotImplementedError", "pass  #",
    "placeholder", "stub implementation", "stubbed implementation",
    "mock implementation", "dummy implementation", "temporary implementation",
    "future implementation", "not yet implemented",
    "panic(\"TODO", "panic(\"not implemented",
]
ALLOWED_PLACEHOLDER_LINE_SNIPPETS = [
    "pass  # ignore errors during cleanup",
    "store placeholder",
    "store sandbox placeholder",
    "storeplaceholder",
    "sandboxstoreplaceholder",
    "buildsandboxplaceholder",
    "todo(hzxuzhonghu): make use of typed informer",
    "todo extend this to unknown resources with a client pool",
    "placeholder:",
    "testbuildsandboxplaceholder",
]
NON_BLOCKING_VALIDATION_PREFIXES: tuple[str, ...] = ()
MIN_IMPLEMENTATION_LOC_BY_AR = {
    # AR-006 extends the creation path with the delete endpoint and exact
    # lifecycle helper contracts. Some rollback helpers can already exist from
    # AR-005, so the generic 30 LOC floor encourages churn after the AR-specific
    # validators have already proven the lifecycle contract is present.
    "AR-006": 10,
}

CHANGE_DOC_EXTS = {".md", ".yaml", ".yml", ".json", ".txt"}
CHANGE_DOC_NAMES = {".openspec.yaml", "README.md", "proposal.md", "delta-spec.md",
                    "design.md", "tasks.md", "implementation.md", "verification.md"}

SPEC_KEYWORDS_BY_MODULE = {
    "pkg/apis": ["project", "sandbox-orchestration", "deployment/client-go"],
    "pkg/workloadmanager": ["project", "sandbox-orchestration"],
    "pkg/router": ["project", "session-routing"],
    "pkg/store": ["project", "session-store"],
    "pkg/picod": ["project", "code-execution"],
    "pkg/agentd": ["project", "idle-cleanup"],
    "cmd/cli": ["project", "cli-toolkit"],
    "cmd": ["project", "cli-toolkit"],
    "sdk-python": ["project", "python-sdk"],
    "manifests": ["project", "deployment"],
    "docker": ["project", "deployment"],
    ".github": ["project", "ci-cd"],
    "client-go": ["project", "deployment/client-go"],
    "integrations": ["project", "integrations"],
    "example": ["project", "integrations"],
    "docs": ["project"],
}

DEPENDENCY_METADATA_FILES = {
    "go.mod", "go.sum", "package.json", "package-lock.json", "pnpm-lock.yaml",
    "yarn.lock", "pyproject.toml", "requirements.txt", "poetry.lock",
}

EXTRA_IMPLEMENTATION_PREFIXES_BY_MODULE = {
    # Shared contracts that appear in the real agentcube tree and are needed
    # for early, compileable reconstruction of the owning module.
    "pkg/workloadmanager": ["pkg/api", "pkg/apis", "pkg/common", "pkg/store"],
    "pkg/router": ["cmd/router", "pkg/api", "pkg/common", "pkg/store"],
    "pkg/picod": ["cmd/picod", "pkg/api", "pkg/common"],
    "pkg/agentd": ["cmd/agentd", "pkg/common", "pkg/workloadmanager"],
}

EXTRA_IMPLEMENTATION_PREFIXES_BY_AR = {
    # The real store interface depends on github.com/volcano-sh/agentcube/pkg/common/types.
    # Allow this exact shared-contract subpackage without allowing broad rewrites of
    # previously generated pkg/common files.
    "AR-012": ["pkg/common/types"],
}

FORBIDDEN_DEPENDENCY_METADATA_BY_AR = {
    # The AR-008 checkpoint already carries the router dependency baseline. AR-009
    # must not churn dependency metadata while implementing only router core files.
    "AR-009": {"go.mod", "go.sum"},
    # AR-010 only adds the concrete router session manager; JWT dependencies are
    # intentionally deferred to AR-011.
    "AR-010": {"go.mod", "go.sum"},
    # AR-012 is a contract-only split; it must not add test helpers or backend deps.
    "AR-012": {"go.mod", "go.sum"},
}

WORKLOADMANAGER_PRODUCTION_AR_IDS = {"AR-004", "AR-005", "AR-006", "AR-007", "AR-008"}

WORKLOADMANAGER_REFERENCE_ORDER_BY_AR: dict[str, list[str]] = {
    "AR-004": [
        "server.go",
        "utils.go",
        "client_cache.go",
        "k8s_client.go",
    ],
    "AR-005": [
        "handlers.go",
        "workload_builder.go",
        "sandbox_helper.go",
        "k8s_client.go",
        "client_cache.go",
        "informers.go",
        "server.go",
        "sandbox_controller.go",
    ],
    "AR-006": [
        "handlers.go",
        "k8s_client.go",
        "garbage_collection.go",
        "sandbox_helper.go",
        "workload_builder.go",
        "server.go",
    ],
    "AR-007": [
        "sandbox_controller.go",
        "codeinterpreter_controller.go",
        "informers.go",
        "workload_builder.go",
        "k8s_client.go",
    ],
    "AR-008": [
        "garbage_collection.go",
        "handlers.go",
        "k8s_client.go",
        "workload_builder.go",
        "sandbox_helper.go",
        "server.go",
    ],
}

ROUTER_REFERENCE_ORDER_BY_AR: dict[str, list[str]] = {
    "AR-009": ["config.go", "server.go", "handlers.go"],
    "AR-010": ["session_manager.go"],
    "AR-011": ["jwt.go", "config.go", "server.go", "handlers.go"],
}

STORE_REFERENCE_ORDER_BY_AR: dict[str, list[str]] = {
    "AR-012": ["interface.go", "error.go"],
    "AR-013": ["store_redis.go", "store_redis_test.go", "singleton.go"],
    "AR-014": ["store_valkey.go", "store_valkey_test.go", "singleton.go"],
}

AR_IMPLEMENTATION_NOTES = {
    "AR-004": (
        "Scope split: implement the real WorkloadManager HTTP server framework, not an alternate simplified API. "
        "Use the original `pkg/workloadmanager` production interfaces: `Server`, `Config`, `NewServer`, `setupRoutes`, "
        "`Start`, `Shutdown`, response helpers, `K8sClient`, `ClientCache`, `TokenCache`, and route wiring for "
        "`/v1/agent-runtime` and `/v1/code-interpreter`. Keep this compatible with the later real sandbox handlers; "
        "do not invent separate Session/Store abstractions or route names."
    ),
    "AR-005": (
        "Scope split: implement the real sandbox creation path. Use the original production APIs in "
        "`handlers.go`, `workload_builder.go`, `sandbox_helper.go`, `k8s_client.go`, and `client_cache.go`: "
        "`handleSandboxCreate`, `extractUserK8sClient`, `createSandbox`, `buildSandboxByAgentRuntime`, "
        "`buildSandboxByCodeInterpreter`, `buildSandboxInfo`, `createSandbox`, and `createSandboxClaim`. "
        "Do not replace these with a bespoke `SandboxCreateRequest`/`Session` flow that is absent from the real project."
    ),
    "AR-006": (
        "Scope split: implement the real sandbox deletion and lifecycle path. Keep the original `handleDeleteSandbox` "
        "contract using `types.SandboxInfo`, `store.Store`, `GetSandboxBySessionID`, `DeleteSandboxBySessionID`, "
        "`deleteSandbox`, and `deleteSandboxClaim`. Do not create alternate in-memory session stores, fake lifecycle "
        "controllers, or non-original production files."
    ),
    "AR-007": (
        "Scope split: implement the real Kubernetes controller/informer layer for WorkloadManager: "
        "`sandbox_controller.go`, `codeinterpreter_controller.go`, and `informers.go`, including "
        "`SandboxReconciler`, `SandboxStatusUpdate`, `WatchSandboxOnce`, `UnWatchSandbox`, `CodeInterpreterReconciler`, "
        "`ensureSandboxTemplate`, `ensureSandboxWarmPool`, `convertToPodTemplate`, and informer cache sync wiring. "
        "Do not create local controller shims or tests-only controller definitions."
    ),
    "AR-008": (
        "Scope split: implement the real sandbox garbage collection pass and close the WorkloadManager production "
        "module. After this AR, `pkg/workloadmanager` production Go files must match the real AgentCube production "
        "file set: `auth.go`, `client_cache.go`, `codeinterpreter_controller.go`, `garbage_collection.go`, "
        "`handlers.go`, `informers.go`, `k8s_client.go`, `sandbox_controller.go`, `sandbox_helper.go`, `server.go`, "
        "`utils.go`, and `workload_builder.go`. Remove non-original shim files such as `defaults.go`, "
        "`memory_store.go`, `middleware.go`, `sandbox_creator.go`, `store.go`, or `token_cache.go`."
    ),
    "AR-009": (
        "Scope split: implement only the Router HTTP reverse-proxy core in exactly "
            "`pkg/router/config.go`, `pkg/router/server.go`, and `pkg/router/handlers.go`. Recreate the real route "
            "wiring, health handlers, concurrency middleware, session-header flow, upstream selection, reverse proxy, "
            "forwarding headers, and last-activity update calls from the original reference. Do not implement Router "
            "session manager or JWT key management yet; those belong to AR-010 and AR-011. If the core needs future "
            "collaborators to compile before those ARs, declare narrow interfaces inside the three allowed files instead "
            "of creating `session_manager.go`, `session.go`, `jwt.go`, `jwt_manager.go`, tests, `cmd/router`, or shared "
            "package rewrites. Session lookup must return `*types.SandboxInfo` from `pkg/common/types`; do not define "
            "local SandboxInfo or SandboxEntryPoint structs in `pkg/router`. Use an unexported JWT signer interface "
            "such as `tokenSigner` rather than `type JWTManager interface`, because AR-011 owns the concrete "
            "`JWTManager` type. Treat `go.mod`, `go.sum`, `pkg/api`, `pkg/store`, and `pkg/common` as read-only in AR-009."
    ),
    "AR-010": (
        "Scope split: implement only the concrete Router session manager in `pkg/router/session_manager.go` "
        "and wire the existing Router server to `NewSessionManager(store.Storage())` without replacing the "
        "AR-009 reverse-proxy core. Keep `pkg/router/config.go`, `pkg/router/server.go`, and "
        "`pkg/router/handlers.go` present and compatible. If the API error helpers are missing, update only "
        "`pkg/api/errors.go` with the original `NewSessionNotFoundError` and `NewSandboxTemplateNotFoundError` "
        "contracts. Do not implement JWT key management, `jwt.go`, `cmd/router`, tests, dependency metadata, "
        "or other shared package rewrites in AR-010; AR-011 owns JWT."
    ),
    "AR-011": (
        "Scope split: implement only Router JWT key management in `pkg/router/jwt.go` and wire the existing "
        "Router server/handler to `*JWTManager`. Preserve the AR-009/AR-010 Router core and session manager. "
        "Do not create router tests, `cmd/router`, store/common rewrites, or alternate JWT interfaces. Use the "
        "original RS256 key generation, Kubernetes Secret bootstrap, and `GenerateToken` contract."
    ),
    "AR-012": (
        "Scope split: implement only the store package contracts for this AR: Store interface, "
        "ErrNotFound, and the shared sandbox document type under `pkg/common/types/...` if it "
        "is missing. Do not modify existing `pkg/common/...` files outside that subpackage. "
        "Remove earlier temporary in-memory/empty store implementations. Do not create Redis or Valkey backend "
        "implementation files, placeholder provider constructors, or singleton wiring that depends on absent "
        "backends; those belong to AR-013 and AR-014. Keep a compileable `Storage()` singleton surface that "
        "fails explicitly for deferred providers without empty Store methods. Do not modify go.mod or go.sum in this AR."
    ),
    "AR-013": (
        "Scope split: implement the Redis backend only. It may update store wiring and Redis tests, "
        "but must not create or modify Valkey backend implementation files. Do not add placeholder "
        "Valkey constructors or call an absent initValkeyStore symbol from singleton wiring; until "
        "AR-014, a valkey STORE_TYPE branch may return an explicit unsupported-provider error. "
        "Create pkg/store/store_redis_test.go with real Redis-compatible behavior tests using "
        "miniredis or redismock; do not rely only on mocks of the Store interface. "
        "MUST import Redis as `redisv9 \"github.com/redis/go-redis/v9\"`; never use the legacy "
        "`github.com/go-redis/redis/v8` module."
    ),
    "AR-014": (
        "Scope split: implement the Valkey backend only, using the existing store interface. "
        "Create pkg/store/store_valkey.go and pkg/store/store_valkey_test.go with real "
        "Valkey-compatible behavior tests using miniredis. Update singleton wiring so "
        "STORE_TYPE=valkey calls initValkeyStore; remove any temporary unsupported/not-implemented "
        "Valkey branch. Do not create or modify Redis backend files."
    ),
    "AR-015": (
        "Scope split: implement the PicoD command execution API only. Focus on server wiring, "
        "command request/response handling, process execution, timeouts, and execute tests. "
        "Do not create file management endpoints or JWT/auth middleware; those belong to AR-016 and AR-017. "
        "Do not create auth files or auth tests, and do not make execute/server tests depend on JWT tokens, "
        "PublicKeyEnvVar, or AuthMiddleware in this AR."
    ),
    "AR-016": (
        "Scope split: implement PicoD file management only: upload, download, list, path validation, "
        "file tests, and route wiring. Do not create JWT/auth middleware; that belongs to AR-017. "
        "Do not create auth files or auth tests, and do not make file/server tests depend on JWT tokens, "
        "PublicKeyEnvVar, or AuthMiddleware in this AR."
    ),
    "AR-017": (
        "Scope split: implement PicoD JWT/auth middleware only, using the existing PicoD server. "
        "Create auth.go/auth_test.go, load the RSA public key from PICOD_AUTH_PUBLIC_KEY, protect only /api routes, "
        "and keep /health public. Auth tests must explicitly cover missing Authorization, expired JWT, "
        "invalid JWT signature, HS256/non-RSA signing, and MaxBodySize. Do not add unrelated command or file behavior in this AR."
    ),
    "AR-018": (
        "Scope split: implement only the agentd idle cleanup controller. Create pkg/agentd reconciler/tests "
        "and cmd/agentd manager wiring. The reconciler must use controller-runtime client Get/Delete, "
        "workloadmanager.LastActivityAnnotationKey, RFC3339 parsing, NotFound handling, and RequeueAfter for "
        "invalid/active sandboxes. Tests must use a real controller-runtime fake client and cover missing/empty "
        "annotation, invalid timestamp, expired deletion, active requeue, and NotFound. Do not create "
        "`pkg/apis/agents/...`; if an external sandbox dependency is unavailable in this Go environment, keep any "
        "minimal Sandbox type local to pkg/agentd only."
    ),
    "AR-019": (
        "Scope split: implement only the four Go service binary entrypoints that exist in the real project: "
        "`cmd/workload-manager/main.go`, `cmd/router/main.go`, `cmd/picod/main.go`, and `cmd/agentd/main.go`. "
        "Do not create a Go `kubectl-agentcube`, `cmd/agentcube-*` aliases, `pkg/cli`, `pkg/models`, or `pkg/services`; "
        "the user CLI is the Python Typer package under `cmd/cli` and belongs to later CLI ARs. Keep this AR focused "
        "on wiring flags/config, klog/signal handling, server startup, and controller-runtime manager startup for "
        "the existing Go packages."
    ),
    "AR-020": (
        "Scope split: implement only the Python CLI pack command under `cmd/cli`. It may create the package skeleton, "
        "`agentcube/cli/main.py`, `agentcube/runtime/pack_runtime.py`, `agentcube/models/pack_models.py`, pyproject metadata, "
        "README, and pack-focused tests. Do not implement build, publish, invoke, status runtimes or commands; those belong "
        "to AR-021, AR-022, and AR-023. Do not implement DockerService, MetadataService, K8sProvider, or AgentCubeProvider; "
        "those belong to AR-024 through AR-026. Pack may write minimal metadata/Dockerfile behavior locally in PackRuntime "
        "until those services exist."
    ),
    "AR-021": (
        "Scope split: implement only the Python CLI build command under `cmd/cli`, building on the pack skeleton. "
        "Update `agentcube/cli/main.py`, create `agentcube/runtime/build_runtime.py`, and add build-focused tests. "
        "Do not implement publish, invoke, or status commands/runtimes; those belong to AR-022 and AR-023. Do not "
        "create DockerService, MetadataService, K8sProvider, or AgentCubeProvider; those are AR-024 through AR-026. "
        "Build may use minimal local metadata/Docker helpers inside BuildRuntime until the service ARs exist. "
        "Do not use NotImplementedError in source or tests; unsupported cloud builds must use a real ValueError or "
        "RuntimeError path with tests asserting that behavior."
    ),
    "AR-022": (
        "Scope split: implement only the Python CLI publish command under `cmd/cli`, building on the pack/build skeleton. "
        "Update `agentcube/cli/main.py`, create `agentcube/runtime/publish_runtime.py`, and add publish-focused tests. "
        "Do not implement invoke or status commands/runtimes; those belong to AR-023. Do not create DockerService, "
        "MetadataService, K8sProvider, or AgentCubeProvider service modules; those are AR-024 through AR-026. Publish may "
        "use minimal inline metadata/provider helpers inside PublishRuntime until the service ARs exist. Do not use "
        "NotImplementedError in source or tests; unsupported providers must use real ValueError or RuntimeError paths. "
        "The full CLI test suite must pass with `PYTHONPATH=cmd/cli python -m pytest cmd/cli/agentcube/tests -q "
        "-W error -W error::pytest.PytestUnraisableExceptionWarning`; do not claim tests pass after running only a subset."
    ),
    "AR-023": (
        "Scope split: implement only the Python CLI invoke and status commands under `cmd/cli`, building on the existing "
        "pack/build/publish skeleton. Update `agentcube/cli/main.py`, create `agentcube/runtime/invoke_runtime.py` and "
        "`agentcube/runtime/status_runtime.py`, and add invoke/status-focused tests. Do not create DockerService, "
        "MetadataService, K8sProvider, AgentCubeProvider, or provider abstraction modules; those are AR-024 through AR-026. "
        "Invoke/status may use minimal inline metadata loading and HTTP/Kubernetes helpers inside their runtimes until the "
        "service ARs exist. Status output must include the metadata agent_name as well as agent_id, agent_endpoint, provider, "
        "deployment/status fields, and not_published/error states. If invoke uses httpx, update `cmd/cli/pyproject.toml` "
        "with a real httpx dependency. HTTP response mocks must match httpx behavior: `post`/client context can be async, "
        "but response methods such as `json()` and `raise_for_status()` are synchronous unless the implementation awaits them. "
        "Do not use NotImplementedError in source or tests. The full CLI test suite must pass with "
        "`PYTHONPATH=cmd/cli python -m pytest cmd/cli/agentcube/tests -q -W error "
        "-W error::pytest.PytestUnraisableExceptionWarning`."
    ),
    "AR-024": (
        "Scope split: implement only the Python CLI DockerService wrapper under `cmd/cli/agentcube/services`. "
        "Create the services package if missing, implement `agentcube/services/docker_service.py`, and add "
        "DockerService-focused tests. Do not implement MetadataService, KubernetesProvider, AgentCubeProvider, "
        "provider abstraction modules, or Kubernetes operations; those belong to AR-025 and AR-026. Do not rewrite "
        "pack/build/publish/invoke/status behavior except for minimal imports required by tests. Import Docker SDK "
        "exceptions from `docker.errors`; do not define local DockerException, BuildError, or APIError classes. Docker "
        "operation failures must raise real RuntimeError paths, matching the original project behavior. The Docker SDK "
        "must be mocked in tests, with no real Docker daemon dependency. Do not use NotImplementedError in source or tests. "
        "The full CLI test suite must pass with `PYTHONPATH=cmd/cli python -m pytest cmd/cli/agentcube/tests -q "
        "-W error -W error::pytest.PytestUnraisableExceptionWarning`."
    ),
    "AR-025": (
        "Scope split: implement only MetadataService and the AgentMetadata data model under `cmd/cli`. "
        "Create `agentcube/services/metadata_service.py`, update `agentcube/services/__init__.py` only as needed, "
        "and add metadata-focused tests. Do not implement KubernetesProvider, AgentCubeProvider, provider abstraction "
        "modules, or Kubernetes operations; those belong to AR-026. Do not rewrite DockerService or CLI runtimes except "
        "for minimal imports if tests require them. MetadataService must load/save/update `agent_metadata.yaml`, support "
        "the alternate metadata filenames used by the original project, validate Python and Java workspaces, and use "
        "real Pydantic/YAML/XML parsing rather than placeholder dictionaries. This is the AR that may migrate existing "
        "CLI runtimes from the temporary AR-020 pack_models AgentMetadata to `agentcube.services.metadata_service` and "
        "MetadataService, matching the original project. `metadata_service.py` itself must define "
        "`class AgentMetadata(BaseModel)` with its fields and validators; do not import AgentMetadata from "
        "`agentcube.models.pack_models` or leave runtime/test code using that temporary model. Use direct "
        "`agentcube.services.metadata_service` imports rather than package-level "
        "`from agentcube.services import AgentMetadata`. Python workspace validation must inspect "
        "`metadata.entrypoint` and `metadata.requirements_file`; Java validation must parse `pom.xml` and require "
        "`src/main/java`. Tests must cover valid and missing `requirements.txt`, missing entrypoint files, and Java "
        "source layout failures. Keep `MetadataOptions` in pack_models. Do not use NotImplementedError in source "
        "or tests. The full CLI test suite must pass with `PYTHONPATH=cmd/cli python -m pytest cmd/cli/agentcube/tests -q "
        "-W error -W error::pytest.PytestUnraisableExceptionWarning`."
    ),
    "AR-026": (
        "Scope split: implement only the Python CLI Kubernetes provider services under `cmd/cli`: "
        "`agentcube/services/k8s_provider.py`, `agentcube/services/agentcube_provider.py`, provider-focused tests, "
        "and the minimal publish/status runtime integration needed to call those providers. Do not implement SDK, "
        "integration, docs, or Go modules. Refactor the existing inline Kubernetes logic in publish/status runtimes "
        "to use `KubernetesProvider` and `AgentCubeProvider`; do not leave duplicate `CustomObjectsApi`, `AppsV1Api`, "
        "or `CoreV1Api` deployment/status logic inside runtime modules. `KubernetesProvider` must load kube config, "
        "ensure namespace, create-or-patch Deployment and NodePort Service, wait for readiness with `TimeoutError`, "
        "report pod/deployment status, delete deployment/service while ignoring 404, and sanitize DNS-1123 names. "
        "`AgentCubeProvider` must create-or-patch AgentRuntime CRs using group `runtime.agentcube.volcano.sh`, "
        "version `v1alpha1`, plural `agentruntimes`, include `targetPort`, `podTemplate`, `imagePullSecrets` "
        "`default-secret`, `sessionTimeout` `15m`, `maxSessionDuration` `8h`, and inject `WORKLOAD_MANAGER_URL`/"
        "`ROUTER_URL` from parameters or environment. Add the real `kubernetes` dependency to `cmd/cli/pyproject.toml`. "
        "Tests must mock Kubernetes clients and update existing publish/status runtime tests so they mock provider "
        "classes after the refactor; do not require a real cluster. Do not use NotImplementedError in source "
        "or tests. The full CLI test suite must pass with `PYTHONPATH=cmd/cli python -m pytest cmd/cli/agentcube/tests -q "
        "-W error -W error::pytest.PytestUnraisableExceptionWarning`."
    ),
    "AR-027": (
        "Scope split: implement only the Python SDK high-level `CodeInterpreterClient` under `sdk-python`. "
        "Create `sdk-python/agentcube/code_interpreter.py`, SDK package metadata, and code-interpreter-focused tests "
        "under `sdk-python/tests`. Python SDK package paths must stay under `sdk-python/`; never create a top-level "
        "`agentcube/` package. `CodeInterpreterClient` must resolve `router_url` from the argument or `ROUTER_URL`, "
        "create a session through `ControlPlaneClient.create_session` when `session_id` is absent, reuse an existing "
        "`session_id` without creating a new session, initialize `CodeInterpreterDataPlaneClient`, clean up created "
        "sessions if data-plane initialization fails, support context manager cleanup via `stop()`, and delegate "
        "`execute_command`, `run_code`, `write_file`, `upload_file`, `download_file`, and `list_files` to the data-plane "
        "client. Tests must mock `ControlPlaneClient` and `CodeInterpreterDataPlaneClient`; do not call real HTTP. "
        "Do not create low-level SDK tests such as `test_control_plane.py`, `test_code_interpreter_data_plane.py`, "
        "`test_http.py`, `test_log.py`, or `test_exceptions.py`; those are AR-029 scope. If importable collaborator "
        "modules are needed for mocking, keep them minimal and untested in this AR. "
        "Do not implement `AgentRuntimeClient` or full HTTP/data-plane client behavior; those belong to AR-028 and "
        "AR-029. Do not use NotImplementedError in source or tests. The SDK test suite must pass with "
        "`PYTHONPATH=sdk-python python -m pytest sdk-python/tests -q -W error "
        "-W error::pytest.PytestUnraisableExceptionWarning`."
    ),
    "AR-028": (
        "Scope split: implement only SDK `AgentRuntimeClient` and its AgentRuntime data-plane client under "
        "`sdk-python`. Create `sdk-python/agentcube/agent_runtime.py`, "
        "`sdk-python/agentcube/clients/agent_runtime_data_plane.py`, update `sdk-python/agentcube/__init__.py`, "
        "and add `sdk-python/tests/test_agent_runtime.py`. Python SDK package paths must stay under `sdk-python/`; "
        "never create a top-level `agentcube/` package. `AgentRuntimeClient` must resolve `router_url` from the "
        "argument or `ROUTER_URL`, bootstrap `session_id` via `AgentRuntimeDataPlaneClient.bootstrap_session_id()` "
        "when absent, reuse provided `session_id`, support context manager cleanup, invoke payloads through "
        "`AgentRuntimeDataPlaneClient.invoke`, call `raise_for_status`, return JSON or fallback text on JSON decode "
        "failure, and raise `ValueError(\"AgentRuntime session_id is not initialized\")` when invoked without a "
        "session. `AgentRuntimeDataPlaneClient` must build the router invocation URL, read/write the "
        "`x-agentcube-session-id` header, use the existing SDK `create_session` helper, and close its session. "
        "Do not create low-level tests for control plane, CodeInterpreter data plane, HTTP utils, logging, or "
        "exceptions; those are AR-029 scope. Do not use NotImplementedError in source or tests. The SDK test suite "
        "must pass with `PYTHONPATH=sdk-python python -m pytest sdk-python/tests -q -W error "
        "-W error::pytest.PytestUnraisableExceptionWarning`."
    ),
    "AR-029": (
        "Scope split: implement only Python SDK low-level HTTP clients/utilities under `sdk-python`: "
        "`agentcube/clients/control_plane.py`, `agentcube/clients/code_interpreter_data_plane.py`, "
        "`agentcube/utils/http.py`, `agentcube/utils/utils.py`, `agentcube/exceptions.py`, and focused SDK tests. "
        "Python SDK package paths must stay under `sdk-python/`; never create a top-level `agentcube/` package. "
        "`ControlPlaneClient` must use `requests.Session` from the shared `create_session` helper, resolve "
        "`WORKLOAD_MANAGER_URL`, read service-account tokens via `read_token_from_file`, set JSON/Auth headers, "
        "create sessions at `/v1/code-interpreter`, require `sessionId`, delete sessions at "
        "`/v1/code-interpreter/sessions/{session_id}`, treat 404 delete as success, and close the session. "
        "`CodeInterpreterDataPlaneClient` must construct the Router invocations base URL, set "
        "`x-agentcube-session-id`, implement `_request`, command execution with PicoD timeout strings and "
        "`CommandExecutionError` using PicoD's snake_case `exit_code` response field, Python/bash file-based "
        "`run_code` that writes the script into the remote session via `self.write_file` before calling "
        "`execute_command` (do not execute a local temp file path remotely), base64 file writes, multipart uploads, "
        "streamed downloads, file listing, and close. Tests must mock HTTP sessions; do not call real network. "
        "Do not use NotImplementedError in source or tests. The SDK test suite must pass with "
        "`PYTHONPATH=sdk-python python -m pytest sdk-python/tests -q -W error "
        "-W error::pytest.PytestUnraisableExceptionWarning`."
    ),
    "AR-030": (
        "Scope split: implement only the Helm chart scaffold and non-RBAC templates under "
        "`manifests/charts/base`. Required files are `Chart.yaml`, `values.yaml`, "
        "`templates/workloadmanager.yaml`, `templates/agentcube-router.yaml`, "
        "`crds/agentruntimes.runtime.agentcube.volcano.sh.yaml`, and "
        "`crds/codeinterpreters.runtime.agentcube.volcano.sh.yaml`. The CRD files are mandatory, not optional "
        "follow-up work. Do not create RBAC resources such as ServiceAccount, Role, ClusterRole, RoleBinding, "
        "or ClusterRoleBinding in this AR; those belong to AR-031. The chart must expose values for Redis, "
        "image repositories/tags, replicas, service ports, resources, router optional serviceAccountName/RBAC "
        "flag, and optional Volcano scheduler configuration. Workload Manager and Router templates must consume "
        "Redis env vars from values, set AGENTCUBE_NAMESPACE from the pod namespace, define health probes, "
        "resources, imagePullSecrets support, and set Router WORKLOAD_MANAGER_URL to the in-cluster "
        "workloadmanager service. Do not add Dockerfiles, Makefile targets, CI workflows, or generated rendered YAML."
    ),
    "AR-031": (
        "Scope split: implement only Helm RBAC and optional scheduler templates under `manifests/charts/base/templates`. "
        "Required files are `templates/rbac/workloadmanager.yaml`, `templates/rbac-router.yaml`, and "
        "`templates/volcano-agent-scheduler-development.yaml`. Do not modify the AR-030 chart scaffold, CRDs, "
        "Workload Manager Deployment/Service, Router Deployment/Service, Dockerfiles, Makefile, CI workflows, "
        "or rendered/generated YAML. Workload Manager RBAC must create ServiceAccount/workloadmanager, "
        "ClusterRole/workloadmanager, and ClusterRoleBinding/workloadmanager with rules for agent-sandbox resources, "
        "AgentCube runtime CRDs/status/finalizers, pods, tokenreviews, and secrets. Router RBAC must render only when "
        "`router.rbac.create` is true and create ServiceAccount/Role/RoleBinding for secret management, defaulting the "
        "name to `agentcube-router`. Volcano scheduler template must render only when `volcano.scheduler.enabled` is "
        "true and include ServiceAccount, ConfigMap with `agent-scheduler.conf`, ClusterRole, ClusterRoleBinding, "
        "metrics Service, and Deployment using volcano scheduler values."
    ),
    "AR-032": (
        "Scope split: implement only Dockerfiles under `docker/`. Required files are `docker/Dockerfile`, "
        "`docker/Dockerfile.router`, and `docker/Dockerfile.picod`. Do not modify Makefile, Helm manifests, "
        "CI workflows, Go source, Python source, or generated build artifacts. Workload Manager and Router "
        "Dockerfiles must be multi-stage builds using `golang:1.24.9-alpine` builder and `alpine:3.19` runtime, "
        "BuildKit cache mounts, `ARG TARGETOS=linux`, `ARG TARGETARCH`, `CGO_ENABLED=0 GOOS=${TARGETOS} "
        "GOARCH=${TARGETARCH}`, stripped Go binaries, non-root UID 1000 runtime users (`apiserver` and `router`), "
        "EXPOSE 8080, and the real entrypoints/CMDs. Router must copy `client-go/` and build `./cmd/router`. "
        "Picod must be a multi-stage build using `golang:1.24.4` builder and `ubuntu:24.04` runtime with Python3 "
        "installed, build `./cmd/picod`, copy `/app/picod`, and run `ENTRYPOINT [\"./picod\"]`."
    ),
    "AR-033": (
        "Scope split: implement only the project-root `Makefile`. Do not create `root/Makefile`; the file path "
        "must be exactly `Makefile` at the repository root. Do not modify Dockerfiles, Helm manifests, CI workflows, "
        "Go/Python source, hack scripts, generated binaries, or build output directories. The Makefile must define "
        "the real AgentCube build variables, code generation targets, Go build/run/test/fmt/vet/lint targets, "
        "Docker build/buildx/push/kind-load targets for workloadmanager, router, and picod, local tool download "
        "targets using the `go-install-tool` macro, E2E targets, and the Python SDK build target. Preserve the "
        "real target dependency shape such as `all: build`, `gen-crd: controller-gen`, "
        "`generate: controller-gen gen-crd`, `gen-all: generate gen-client`, `build: generate`, "
        "`build-agentd: generate`, `build-router: generate`, and `build-all: build build-agentd build-router`."
    ),
    "AR-034": (
        "Scope split: implement only GitHub Actions workflow YAML under `.github/workflows`. Required files are "
        "`main.yml`, `e2e.yml`, `lint.yml`, `python-sdk-tests.yml`, `python-lint.yml`, `test-coverage.yml`, "
        "`codegen-check.yml`, `copyright-check.yml`, `codespell.yml`, `build-push-release.yml`, "
        "`dify-plugin-publish.yml`, and `workflows-approve.yml`. Do not modify Makefile, Dockerfiles, Helm manifests, "
        "source code, tests, docs, or generated artifacts. Workflows must match the real AgentCube CI split: PR Docker "
        "build, Kind E2E, Go lint, SDK pytest, Python Ruff lint, Go coverage/Codecov, codegen drift check, copyright "
        "check, codespell, release image push to GHCR, Dify plugin publish, and first-time-contributor workflow approval."
    ),
    "AR-035": (
        "Scope split: implement only generated Kubernetes client code under `client-go/`. Required output is the real "
        "25-file generated tree for runtime.agentcube.volcano.sh/v1alpha1: versioned clientset, scheme, fake clientset, "
        "typed runtime/v1alpha1 clients for AgentRuntime and CodeInterpreter, typed fake clients, informer factory, "
        "generic informer routing, runtime/v1alpha1 informers, internal informer interfaces, and listers. Do not modify "
        "pkg/apis, hack scripts, Makefile, CI, Helm, Dockerfiles, source packages, tests, or generated "
        "applyconfiguration code. It may update `go.mod`/`go.sum` only to align Kubernetes dependencies with the real "
        "generated client (`k8s.io/api`, `k8s.io/apimachinery`, and `k8s.io/client-go` v0.34.1). For this AR, "
        "dependency metadata must match the original AgentCube baseline: `go 1.24.4`, `toolchain go1.24.9`, and "
        "Kubernetes modules v0.34.1; this AR-specific requirement overrides the generic Go 1.22 fallback guidance. "
        "All files must be real Go generated-code equivalents using the AgentCube module path "
        "`github.com/volcano-sh/agentcube`, client-go generics (`gentype.ClientWithList`, `gentype.FakeClientWithList`, "
        "`listers.ResourceIndexer`), watch-capable clients, fake clientset reactors, and informer/lister resource routing "
        "for both `agentruntimes` and `codeinterpreters`. Import external helpers from `k8s.io/client-go/...`; never "
        "create local replacement dependency packages such as `client-go/k8s.io/...` or `pkg/gentype`."
    ),
    "AR-036": (
        "Scope split: implement only the Dify plugin under `integrations/dify-plugin`. Required output is the real "
        "plugin package file set: `manifest.yaml`, `main.py`, `requirements.txt`, `.difyignore`, `README.md`, "
        "`GUIDE.md`, `PRIVACY.md`, `provider/agentcube.yaml`, `provider/agentcube.py`, "
        "`tools/agentcube-code-interpreter.yaml`, `tools/agentcube-code-interpreter.py`, and valid PNG assets "
        "`_assets/icon.png` and `_assets/icon-dark.png`. Do not implement the PCAP analyzer, FastAPI example, "
        "Dockerfile, Kubernetes deployment, or any `pcap_analyzer` files in this AR; those belong to AR-037 under "
        "`example/pcap-analyzer`."
    ),
    "AR-037": (
        "Scope split: implement only the PCAP analyzer example under `example/pcap-analyzer`. Required output is the "
        "real five-file example: `pcap_analyzer.py`, `requirements.txt`, `Dockerfile`, `deployment.yaml`, and "
        "`README.md`. The Python app must include the FastAPI `/analyze` service, LangChain/LangGraph planner and "
        "reporter agents, AgentCube-backed `SandboxRunner`, script planning/repair/retry helpers, OpenAI-compatible "
        "environment configuration, and uvicorn entrypoint. Do not modify `integrations/dify-plugin`; the Dify plugin "
        "belongs to AR-036."
    ),
    "AR-038": (
        "Test-only scope: create only the real workloadmanager Go unit test files under `pkg/workloadmanager`. "
        "Required files are `auth_test.go`, `client_cache_test.go`, `codeinterpreter_controller_test.go`, "
        "`handlers_test.go`, `k8s_client_test.go`, `runtimeclassname_test.go`, `sandbox_helper_test.go`, and "
        "`utils_test.go`. Do not modify production Go files, other packages, E2E tests, Python tests, docs, "
        "dependency metadata, or generated files."
    ),
    "AR-042": (
        "Scope limit: implement the Docusaurus documentation site framework only. Create concise, real "
        "starter pages for the home page, sidebar categories, i18n, MDX, and API-reference placeholders, "
        "but do not write comprehensive user/admin/developer/API manuals in this AR. Limit starter content "
        "to the minimum needed to prove navigation and rendering: one home page, two pages per guide category, "
        "and concise API placeholder pages. Keep each markdown/MDX page under 120 lines and avoid exhaustive "
        "command/API tables. Do not vendor dependencies or generated build artifacts such as node_modules, "
        ".docusaurus, build, dist, or coverage. Do not execute npm, npx, yarn, or pnpm commands in this "
        "model stage; the benchmark harness runs install/build checks separately and cleans their artifacts. "
        "Do not create package-lock.json, pnpm-lock.yaml, or yarn.lock. For Docusaurus prism config, import "
        "`themes as prismThemes` from `prism-react-renderer` and use `prism: { theme: prismThemes.github, "
        "darkTheme: prismThemes.dracula, additionalLanguages: [...] }`; do not use light/dark/plain string fields. "
        "Inside the Docusaurus site root, put guide and API markdown under the default `docs/` content folder "
        "(project paths like `docs/docs/guide/user/getting-started.md` and `docs/docs/api/go-api.md`), "
        "not directly under `docs/guide` or `docs/api`. Do not add a second content-docs plugin; keep guide "
        "and API sidebars in the single default `sidebars.ts`. Use `src/pages/index.tsx` for a React/TSX "
        "home page with no MDX front matter; do not put TypeScript annotations or React component exports "
        "in an `.mdx` page. Links to API docs must use `/docs/api/...`, not `/api/...`. For minimal i18n, "
        "configure locales only; do not create localized markdown copies, `i18n/en/...`, or `current.json` translation files. "
        "Static assets referenced as `img/...` must live under `docs/static/img/...`, not `docs/img/...`, "
        "and must be non-empty real assets. Prefer a small non-empty `docs/static/img/logo.svg` and set "
        "`favicon: 'img/logo.svg'`; do not create empty `.ico` or `.jpg` placeholder files. For links between docs, use Docusaurus "
        "routes such as `/docs/guide/admin/deployment`; avoid cross-folder `../*.md` markdown links. Exact file budget: "
        "write at most these 8 markdown pages under `docs/docs/`: "
        "`guide/user/getting-started.md`, `guide/user/workflows.md`, `guide/admin/installation.md`, "
        "`guide/admin/configuration.md`, `guide/developer/architecture.md`, `guide/developer/contributing.md`, "
        "`api/go-api.md`, and `api/python-sdk.md`. Do not create additional markdown or MDX pages. The React "
        "home page must have exactly one default export (`Home`); helper components must not be default exports. Use "
        "Docusaurus package versions `^3.10.1` or `3.10.1`; do not pin to older 3.5.x packages."
    ),
    "AR-043": (
        "Scope limit: extend the existing Docusaurus docs with concise architecture and API reference pages only. "
        "This is the ST-5 implementation scope; ST-0 through ST-4 must only describe the work in SDD artifacts "
        "under `changes/AR-043/` and must not create or update project docs pages early. "
        "Do not recreate or copy long design proposals or full manuals from the original project. Markdown/MDX "
        "content must live under `docs/docs/...`; never put documentation pages under `docs/src/...`. Create or "
        "update only these AR-043 content pages: `docs/docs/api/rest-api.md`, "
        "`docs/docs/api/kubernetes-crds.md`, `docs/docs/guide/developer/workload-manager-architecture.md`, "
        "`docs/docs/guide/developer/router-architecture.md`, and "
        "`docs/docs/guide/developer/agentd-architecture.md`. You may also update the existing AR-042 docs pages "
        "and `docs/sidebars.ts` only as needed to link these pages. Keep each markdown page under 180 lines, "
        "keep SDD artifacts concise, and target roughly 400-900 implementation LOC for this medium documentation AR. "
        "Use short endpoint/type tables, compact examples, and cross-links; do not generate exhaustive API dumps. "
        "Do not execute npm, npx, yarn, or pnpm commands in model stages, and do not leave generated artifacts or "
        "lockfiles."
    ),
}

AR_042_DOC_MARKDOWN = {
    "docs/docs/guide/user/getting-started.md",
    "docs/docs/guide/user/workflows.md",
    "docs/docs/guide/admin/installation.md",
    "docs/docs/guide/admin/configuration.md",
    "docs/docs/guide/developer/architecture.md",
    "docs/docs/guide/developer/contributing.md",
    "docs/docs/api/go-api.md",
    "docs/docs/api/python-sdk.md",
}

AR_043_DOC_MARKDOWN = {
    "docs/docs/api/rest-api.md",
    "docs/docs/api/kubernetes-crds.md",
    "docs/docs/guide/developer/workload-manager-architecture.md",
    "docs/docs/guide/developer/router-architecture.md",
    "docs/docs/guide/developer/agentd-architecture.md",
}

AR_RESERVED_IMPLEMENTATION_PATTERNS = {
    "AR-009": [
        "pkg/router/*_test.go",
        "pkg/router/jwt.go",
        "pkg/router/*jwt*.go",
        "pkg/router/session.go",
        "pkg/router/session_manager.go",
        "pkg/router/*session*.go",
        "cmd/router/*",
    ],
    "AR-010": [
        "pkg/router/*_test.go",
        "pkg/router/jwt.go",
        "pkg/router/*jwt*.go",
        "cmd/router/*",
    ],
    "AR-011": [
        "pkg/router/*_test.go",
        "cmd/router/*",
    ],
    "AR-012": [
        "pkg/store/store_redis.go",
        "pkg/store/store_redis_test.go",
        "pkg/store/*redis*.go",
        "pkg/store/store_valkey.go",
        "pkg/store/store_valkey_test.go",
        "pkg/store/*valkey*.go",
    ],
    "AR-013": [
        "pkg/store/store_valkey.go",
        "pkg/store/store_valkey_test.go",
        "pkg/store/*valkey*.go",
    ],
    "AR-014": [
        "pkg/store/store_redis.go",
        "pkg/store/store_redis_test.go",
        "pkg/store/*redis*.go",
    ],
    "AR-015": [
        "pkg/picod/files.go",
        "pkg/picod/files_test.go",
        "pkg/picod/*file*.go",
        "pkg/picod/auth.go",
        "pkg/picod/auth_test.go",
        "pkg/picod/*auth*.go",
    ],
    "AR-016": [
        "pkg/picod/auth.go",
        "pkg/picod/auth_test.go",
        "pkg/picod/*auth*.go",
    ],
    "AR-036": [
        "integrations/dify-plugin/examples/*",
        "integrations/dify-plugin/examples/pcap_analyzer/*",
        "integrations/dify-plugin/*pcap*",
        "integrations/dify-plugin/**/*pcap*",
        "example/pcap-analyzer/*",
    ],
    "AR-037": [
        "integrations/dify-plugin/*",
    ],
}


# ─── Adapter factory ─────────────────────────────────────────────────────

from adapters.base import BaseAdapter, StageRecord
from adapters.claude_code import ClaudeCodeAdapter
from adapters.gemini_cli import GeminiCliAdapter
from adapters.cursor_cli import CursorCliAdapter
from adapters.opencode_cli import OpenCodeCliAdapter


def create_adapter(tool: str, model: str, api_base: Optional[str] = None) -> BaseAdapter:
    """Factory: create the right adapter for the given CLI tool."""
    factories = {
        "claude-code": lambda: ClaudeCodeAdapter(model, api_base),
        "gemini-cli": lambda: GeminiCliAdapter(model),
        "cursor-cli": lambda: CursorCliAdapter(model, api_base),
        "opencode-cli": lambda: OpenCodeCliAdapter(model),
    }
    if tool not in factories:
        raise ValueError(f"Unknown tool: {tool}. Supported: {', '.join(factories.keys())}")
    return factories[tool]()


def reconcile_stage_records(adapter, log_dir: str, stage_records: dict, ar_id: str) -> dict:
    """Re-parse all log files to get authoritative api_calls/iterations counts.

    This corrects any parser-induced inflation of call counts from the live run.
    Token values (input/output/cache) are preserved as-is since they were already
    correctly extracted — the bug only affected api_calls counting.
    """
    log_path = Path(log_dir)
    if not log_path.exists():
        return stage_records

    for stage_id, record in stage_records.items():
        if getattr(record, "data_source", "") == "litellm_proxy" or getattr(record, "attempts", 1) > 1:
            continue
        log_file = log_path / f"{ar_id}_{stage_id}.log"
        if not log_file.exists():
            continue

        log_text = log_file.read_text(encoding="utf-8")
        verified = adapter.parse_native_output(log_text)
        if verified.api_calls > 0:
            # Only update api_calls/iterations, preserve token values
            record.api_calls = verified.api_calls
            record.iterations = verified.api_calls

    return stage_records


def _repair_partial_timeout_telemetry(ar_results: list[dict], adapter, log_dir: Path) -> None:
    """Repair prior checkpoint data for timed-out opencode stages.

    Older checkpoints may have a timed-out stage with only `step_start` in the
    log. We count that attempted API call but keep token and cost fields at
    zero because opencode never emitted completed usage.
    """
    for ar in ar_results:
        stages = ar.get("stages", {})
        for stage_id, stage in stages.items():
            if stage_id == "ST-6.5" or stage.get("api_calls", 0) > 0:
                continue
            if "Timeout after" not in (stage.get("error") or ""):
                continue
            log_file = log_dir / f"{ar.get('ar_id')}_{stage_id}.log"
            if not log_file.exists():
                continue
            log_text = log_file.read_text(encoding="utf-8", errors="replace")
            parsed = adapter.parse_native_output(log_text)
            if parsed.api_calls <= 0:
                attempt_logs = [log_file] + sorted(log_dir.glob(f"{ar.get('ar_id')}_{stage_id}.attempt*.log"))
                timeout_attempts = 0
                for attempt_log in attempt_logs:
                    try:
                        attempt_text = attempt_log.read_text(encoding="utf-8", errors="replace")
                    except OSError:
                        continue
                    if "EXIT_CODE: TIMEOUT" in attempt_text:
                        timeout_attempts += 1
                if timeout_attempts <= 0:
                    continue
                stage["api_calls"] = timeout_attempts
                stage["iterations"] = timeout_attempts
                stage["data_source"] = "process_timeout_no_usage"
            else:
                stage["api_calls"] = parsed.api_calls
                stage["iterations"] = parsed.iterations
                stage["data_source"] = parsed.data_source

        totals = ar.get("totals", {})
        totals["api_calls"] = sum(s.get("api_calls", 0) for s in stages.values())
        totals["iterations"] = sum(s.get("iterations", 0) for s in stages.values())


def _workspace_root() -> Path:
    raw = os.environ.get("SDD_WORKSPACE_ROOT")
    return Path(raw).expanduser().resolve() if raw else DEFAULT_WORKSPACE_ROOT


def _ensure_workspace_git_root(workspace: Path) -> None:
    """Keep CLI tools from climbing to the benchmark repo's Git root."""
    git_dir = workspace / ".git"
    if git_dir.exists():
        return
    try:
        subprocess.run(
            ["git", "init"],
            cwd=workspace,
            check=True,
            timeout=30,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception as exc:
        print(f"[WARN] Could not initialize isolated workspace git root: {exc}")


def _workspace_checkpoint_root() -> Path:
    return BASE / "results" / "runs" / "v5.1" / "workspace_checkpoints"


def _workspace_checkpoint_path(run_id: str, ar_id: str) -> Path:
    safe_run_id = re.sub(r"[^A-Za-z0-9_.-]", "-", run_id)
    safe_ar_id = re.sub(r"[^A-Za-z0-9_.-]", "-", ar_id)
    return _workspace_checkpoint_root() / f"{safe_run_id}_{safe_ar_id}"


def _workspace_snapshot_ignore(dirpath: str, names: list[str]) -> set[str]:
    ignored = set()
    base = Path(dirpath)
    for name in names:
        path = base / name
        if name == ".git" or name in GENERATED_ARTIFACT_DIRS:
            ignored.add(name)
        elif name in GENERATED_ARTIFACT_FILES and path.is_file():
            ignored.add(name)
    return ignored


def _save_workspace_checkpoint(workspace: Path, run_id: str, ar_id: str) -> Optional[Path]:
    """Save a clean filesystem checkpoint for reliable AR reruns."""
    if os.environ.get("SDD_DISABLE_WORKSPACE_CHECKPOINTS") == "1":
        return None
    checkpoint = _workspace_checkpoint_path(run_id, ar_id)
    tmp = checkpoint.with_name(checkpoint.name + ".tmp")
    if tmp.exists():
        shutil.rmtree(tmp)
    if checkpoint.exists():
        shutil.rmtree(checkpoint)
    checkpoint.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(workspace, tmp, ignore=_workspace_snapshot_ignore)
    tmp.rename(checkpoint)
    return checkpoint


def _restore_workspace_checkpoint(workspace: Path, run_id: str, ar_id: str) -> bool:
    """Restore the workspace to the filesystem checkpoint matching resume JSON."""
    if os.environ.get("SDD_DISABLE_WORKSPACE_CHECKPOINTS") == "1":
        return False
    checkpoint = _workspace_checkpoint_path(run_id, ar_id)
    if not checkpoint.exists():
        return False
    workspace.mkdir(parents=True, exist_ok=True)
    for item in workspace.iterdir():
        if item.name == ".git":
            continue
        if item.is_dir():
            shutil.rmtree(item)
        else:
            item.unlink()
    for item in checkpoint.iterdir():
        dst = workspace / item.name
        if item.is_dir():
            shutil.copytree(item, dst, ignore=_workspace_snapshot_ignore)
        else:
            shutil.copy2(item, dst)
    return True


# ─── Prompt builder ──────────────────────────────────────────────────────

def load_specs(specs_dir: str) -> dict:
    """Load all .md files from specs directory."""
    specs = Path(specs_dir)
    content = {}
    for sf in sorted(specs.rglob("*.md")):
        rel = str(sf.relative_to(specs))
        content[rel] = sf.read_text(encoding="utf-8", errors="replace")
    return content


def _spec_keywords_for_ar(ar: dict) -> list[str]:
    module = ar["module"].strip("/")
    matches = []
    for prefix, keywords in SPEC_KEYWORDS_BY_MODULE.items():
        if module == prefix or module.startswith(prefix + "/"):
            matches.extend(keywords)
            break
    if not matches:
        matches.append("project")
        leaf = module.split("/")[-1]
        if leaf:
            matches.append(leaf)
    if ar["type"] == "测试":
        matches.append("testing")
    return list(dict.fromkeys(matches))


def _filter_spec_text_for_ar(ar: dict, name: str, text: str) -> str:
    """Keep shared integration specs aligned with the current AR split."""
    if ar["id"] in {"AR-009", "AR-010"} and name == "session-routing/spec.md":
        text = text.replace(
            "resolve or create sessions via the workload manager, track activity in the store, "
            "reverse-proxy to pod endpoints, and sign outbound requests with JWT when targeting sandboxes.",
            "resolve or create sessions via the workload manager, track activity in the store, "
            "and reverse-proxy to pod endpoints. JWT key management is deferred to AR-011.",
        )
        jwt_start = "### Requirement: JWT injection for sandbox kinds"
        jwt_end = "### Requirement: Forwarding headers and response header"
        if jwt_start in text and jwt_end in text:
            before, rest = text.split(jwt_start, 1)
            _, after = rest.split(jwt_end, 1)
            text = before.rstrip() + "\n\n<!-- Signing requirements are omitted for this AR; they belong to AR-011. -->\n\n" + jwt_end + after
        secret_start = "### Requirement: Identity secret bootstrap for JWT"
        if secret_start in text:
            text = text.split(secret_start, 1)[0].rstrip() + "\n\n<!-- Identity bootstrap is omitted for this AR; it belongs to AR-011. -->\n"
    if ar["id"] in {"AR-009", "AR-010"} and name == "session-routing/design.md":
        jwt_start = "### JWT (`jwt.go`)"
        jwt_end = "### Reverse proxy"
        if jwt_start in text and jwt_end in text:
            before, rest = text.split(jwt_start, 1)
            _, after = rest.split(jwt_end, 1)
            text = before.rstrip() + "\n\n<!-- Signing design is omitted for this AR; it belongs to AR-011. -->\n\n" + jwt_end + after
        text = text.replace("    jwtManager     *JWTManager\n", "")
    if ar["id"] == "AR-036" and name in {"integrations/spec.md", "integrations/design.md"}:
        for marker in (
            "### Requirement: PCAP analyzer FastAPI service",
            "## PCAP analyzer — application structure",
        ):
            if marker in text:
                return (
                    text.split(marker, 1)[0].rstrip()
                    + "\n\n<!-- PCAP analyzer requirements are omitted for AR-036; "
                    + "they belong to AR-037. -->\n"
                )
    if ar["id"] == "AR-037" and name == "integrations/spec.md":
        marker = "### Requirement: PCAP analyzer FastAPI service"
        if marker in text:
            preamble = text.split("## Requirements", 1)[0].rstrip()
            tail = marker + text.split(marker, 1)[1]
            return f"{preamble}\n\n## Requirements\n\n{tail}"
    if ar["id"] == "AR-037" and name == "integrations/design.md":
        marker = "## PCAP analyzer — application structure"
        if marker in text:
            tail = marker + text.split(marker, 1)[1]
            return "# AgentCube PCAP Analyzer Example — Design\n\n" + tail
    return text


def _allowed_implementation_prefixes(ar: dict) -> list[str]:
    if ar.get("id") == "AR-009":
        return ["pkg/router"]
    if ar.get("id") == "AR-010":
        return ["pkg/router", "pkg/api"]
    if ar.get("id") == "AR-011":
        return ["pkg/router"]
    module = ar["module"].strip("/")
    prefixes = [module] if module else []
    prefixes.extend(EXTRA_IMPLEMENTATION_PREFIXES_BY_MODULE.get(module, []))
    prefixes.extend(EXTRA_IMPLEMENTATION_PREFIXES_BY_AR.get(ar["id"], []))
    return list(dict.fromkeys(p for p in prefixes if p))


def _sdd_artifact_line_limits(ar: dict) -> dict[str, int]:
    """Concise SDD artifacts keep later prompts and token/cost data realistic."""
    size = ar.get("size", "M")
    if size == "S":
        limits = {
            "ST-1": 160,
            "ST-2": 220,
            "ST-3": 260,
            "ST-4": 180,
            "ST-5": 160,
            "ST-6": 140,
            "ST-7": 100,
        }
    elif size == "L":
        limits = {
            "ST-1": 280,
            "ST-2": 420,
            "ST-3": 520,
            "ST-4": 320,
            "ST-5": 260,
            "ST-6": 180,
            "ST-7": 140,
        }
    else:
        limits = {
            "ST-1": 220,
            "ST-2": 300,
            "ST-3": 360,
            "ST-4": 240,
            "ST-5": 220,
            "ST-6": 160,
            "ST-7": 120,
        }
    if ar.get("id") == "AR-043":
        limits.update({
            "ST-1": 140,
            "ST-2": 220,
            "ST-3": 220,
            "ST-4": 180,
            "ST-5": 140,
            "ST-6": 140,
            "ST-7": 100,
        })
    if ar.get("id") == "AR-017":
        limits.update({
            "ST-3": 320,
        })
    return limits


def build_stage_prompt(ar: dict, stage_id: str, specs_content: dict, prev_outputs: dict,
                       original_snippets: str = "") -> str:
    """Build prompt for a specific AR × stage.

    Prompts reference the actual agentcube specs.
    """
    ar_desc = (
        f"AR: {ar['id']} — {ar['name']}\n"
        f"Module: {ar['module']}\n"
        f"Language: {ar['lang']}\n"
        f"Size: {ar['size']}"
    )

    # Find relevant specs. Do not match on generic language names such as
    # "Go"; that pulls unrelated specs like deployment/client-go into every
    # Go AR and corrupts the benchmark prompts.
    relevant = []
    keywords = _spec_keywords_for_ar(ar)
    for name, text in specs_content.items():
        name_lower = name.lower()
        if any(kw.lower() in name_lower for kw in keywords):
            relevant.append(f"--- {name} ---\n{_filter_spec_text_for_ar(ar, name, text)}")

    spec_ctx = "\n\n".join(relevant[:5]) if relevant else "(No directly matching specs)"
    change_dir = f"changes/{ar['id']}"
    previous_ctx = "\n\n".join(
        f"--- {name} ---\n{text[:6000]}" for name, text in prev_outputs.items() if text
    ) or "(No previous stage artifacts yet)"
    scope_notes: list[str] = []
    if AR_IMPLEMENTATION_NOTES.get(ar["id"]):
        scope_notes.append(AR_IMPLEMENTATION_NOTES[ar["id"]])
    if ar["type"] == "测试" and ar["lang"] == "Go":
        module_path = ar["module"].strip("/")
        if module_path.startswith("test/") or module_path == "test":
            scope_notes.append(
                "Test-only scope: create or modify Go E2E tests and test helper .go files only under "
                f"`{module_path}/...`. Do not modify production Go packages such as `pkg/...` in this AR. "
                f"The generated tests must compile and pass with `go test ./{module_path}/...`."
            )
        else:
            scope_notes.append(
                "Test-only scope: create or modify Go test files ending in _test.go. "
                "Do not modify production .go implementation files in this AR; those are reserved for feature ARs. "
                f"The generated tests must compile and pass with `go test ./{module_path}/...`; "
                "if a fake client or external dependency makes a success-path test impractical, test the pure builder, "
                "store, validation, and error paths instead of relying on panic recovery or production-code changes."
            )
    ar_scope_note = " ".join(scope_notes)
    line_limits = _sdd_artifact_line_limits(ar)
    sdd_budget_text = (
        "SDD artifact length budget: "
        f"proposal <= {line_limits['ST-1']} lines, "
        f"delta-spec <= {line_limits['ST-2']} lines, "
        f"design <= {line_limits['ST-3']} lines, "
        f"tasks <= {line_limits['ST-4']} lines, "
        f"implementation notes <= {line_limits['ST-5']} lines, "
        f"verification <= {line_limits['ST-6']} lines, "
        f"archive notes <= {line_limits['ST-7']} lines. "
        "Keep artifacts concise: summarize decisions and scenarios; do not paste source files, exhaustive API dumps, "
        "or repeated tables into SDD documents.\n"
    )
    if stage_id == "ST-5":
        stage_write_policy = (
            "Stage write boundary: this is the implementation stage. Project source changes are allowed "
            "only under the allowed implementation paths listed below. You must also create or update the "
            f"single stage artifact `{change_dir}/implementation.md`; files such as `implementation-notes.md`, "
            "`summary.md`, or `verification.md` do not satisfy the ST-5 artifact requirement.\n"
        )
    else:
        stage_write_policy = (
            f"Stage write boundary: for {stage_id}, write only the explicitly requested SDD artifact(s) "
            f"under {change_dir}/. Do not create, modify, or delete project implementation/source files "
            "outside the change directory; implementation source is allowed only in ST-5.\n"
        )
    if ar["id"] in WORKLOADMANAGER_PRODUCTION_AR_IDS:
        go_dependency_guidance = (
            "The real AgentCube WorkloadManager dependency baseline is `go 1.24.4` with "
            "`toolchain go1.24.9`. Preserve that baseline for these WorkloadManager production ARs; "
            "the benchmark runner has a compatible Go toolchain and this AR-specific requirement overrides "
            "generic older-toolchain fallback guidance.\n"
        )
        local_import_guidance = (
            "For Go imports, local module import paths must match real directories in this workspace. "
            "Shared sandbox request/response types must live under `pkg/common/types/{types.go,sandbox.go}` "
            "and be imported as `github.com/volcano-sh/agentcube/pkg/common/types`; do not create or reference "
            "`pkg/common/types.go` for WorkloadManager.\n"
        )
    else:
        go_dependency_guidance = (
            "The benchmark environment runs Go 1.22.x. Keep the `go` directive at 1.22.x and choose "
            "dependency versions that compile on Go 1.22; do not introduce packages that require Go 1.23+.\n"
        )
        local_import_guidance = (
            "For Go imports, local module import paths must match real directories in this workspace. "
            "If you create `pkg/common/types.go`, import it as `github.com/volcano-sh/agentcube/pkg/common` "
            "or create a real `pkg/common/types/` directory; never import non-existent local subpackages.\n"
        )

    common = (
        "You are reconstructing the real open-source project agentcube from an empty workspace "
        "through a Specification-Driven Development benchmark.\n"
        "The Go module path MUST be `github.com/volcano-sh/agentcube`.\n"
        f"{go_dependency_guidance}"
        f"{local_import_guidance}"
        "The project root is the current working directory for this CLI session. "
        "Do not inspect, create, modify, delete, or run commands against parent directories "
        "or the benchmark harness repository outside the current working directory.\n"
        "This is an execution task, not a discussion. Use filesystem tools to write the requested files.\n"
        "Do not invent benchmark metrics, token counts, costs, or test results.\n"
        "Do not leave placeholders, TODOs, stubs, or empty implementations.\n"
        f"All SDD change artifacts for this AR must live under {change_dir}/.\n"
        f"The {change_dir}/ directory is for SDD documents only. Never write source code, packages, "
        f"tests, generated clients, or implementation trees under {change_dir}/. "
        f"Any source file under {change_dir}/ will be deleted and counted as a benchmark failure.\n"
        f"{stage_write_policy}"
        f"{sdd_budget_text}"
        f"{('AR-specific scope: ' + ar_scope_note + chr(10)) if ar_scope_note else ''}"
    )
    allowed_paths = _allowed_implementation_prefixes(ar)
    if allowed_paths == ["root"]:
        allowed_paths_text = "project root files (for this AR, `Makefile`)"
    else:
        allowed_paths_text = ", ".join(f"`{p}/...`" for p in allowed_paths) or "project root target paths"
    if ar["id"] in FORBIDDEN_DEPENDENCY_METADATA_BY_AR:
        dependency_metadata_policy = (
            "Do NOT modify dependency metadata such as go.mod, go.sum, package.json, lockfiles, "
            "pyproject.toml, requirements.txt, or poetry.lock for this AR.\n"
        )
    elif ar["id"] == "AR-035":
        dependency_metadata_policy = (
            "For AR-035, update go.mod/go.sum as needed to match the original AgentCube dependency baseline: "
            "`go 1.24.4`, `toolchain go1.24.9`, and `k8s.io/api`, `k8s.io/apimachinery`, "
            "`k8s.io/client-go` at v0.34.1.\n"
        )
    else:
        dependency_metadata_policy = (
            "Only dependency metadata such as go.mod/go.sum may be adjusted outside the target module.\n"
        )
    st5_intro = "Implement ALL code for the agentcube project. Write COMPLETE, working code."
    previous_ctx_limit = 12000
    original_snippets_limit = 12000
    original_reference_note = "ORIGINAL CODE REFERENCE (ground truth — match these interfaces and behaviors):"
    if ar["id"] in {"AR-004", "AR-005", "AR-006", "AR-007", "AR-008"}:
        st5_intro = (
            "Implement the WorkloadManager production Go code for this AR using the real AgentCube production "
            "interfaces from the original reference below. Keep the output compatible with the cumulative real "
            "`pkg/workloadmanager` package; do not invent alternate session models, request/response types, "
            "test-only controller shims, or non-original production files. Use the original shared package "
            "`pkg/common/types/{types.go,sandbox.go}` and import it as `github.com/volcano-sh/agentcube/pkg/common/types`; "
            "do not create `pkg/common/types.go` or alias these types from `pkg/store`. Align `go.mod` to the "
            "original baseline (`go 1.24.4`, `toolchain go1.24.9`, Kubernetes modules v0.34.1, "
            "`sigs.k8s.io/agent-sandbox v0.1.1`, controller-runtime v0.22.2) so `go mod tidy` does not pull a "
            "newer incompatible agent-sandbox release. Do not create concrete `pkg/store` backend implementations "
            "in these production ARs; store backends belong to the later store ARs. Do not create workloadmanager "
            "or common/types `_test.go` files in these production ARs; workloadmanager tests belong to AR-038."
        )
        previous_ctx_limit = 5000
        original_snippets_limit = 95000
        original_reference_note = (
            "FULL ORIGINAL WORKLOADMANAGER PRODUCTION REFERENCE (ground truth for production APIs and file set):"
        )
    if ar["id"] == "AR-008":
        st5_intro = (
            "Implement the AR-008 garbage collection work and close the WorkloadManager production module. After this "
            "AR, `pkg/workloadmanager` must contain exactly the real production Go file set from the reference below "
            "and no non-original shim files. Remove any earlier simplified Session/Store/defaults/memory/token-cache "
            "files that are not in the reference."
        )
    if ar["id"] == "AR-009":
        st5_intro = (
            "Implement ONLY the Router HTTP reverse-proxy core for this AR. Write exactly "
            "`pkg/router/config.go`, `pkg/router/server.go`, and `pkg/router/handlers.go` using the original "
            "router core reference below. Do not create router tests, JWT implementation files, session manager "
            "implementation files, `cmd/router`, or shared package rewrites. AR-010 will implement the concrete "
            "session manager and AR-011 will implement JWT key management; for AR-009, keep those collaborators as "
            "narrow package-local interfaces or optional fields inside the three allowed files so `go test "
            "./pkg/router/...` can compile without fake future implementations. The session interface must return "
            "`*types.SandboxInfo` from `github.com/volcano-sh/agentcube/pkg/common/types`; do not define local "
            "`SandboxInfo` or `SandboxEntryPoint` structs or conversion shims in `pkg/router`. Use an unexported "
            "JWT signer interface such as `tokenSigner`; do not define `type JWTManager interface` because AR-011 "
            "owns the concrete `JWTManager` type."
        )
        previous_ctx_limit = 5000
        original_snippets_limit = 50000
        original_reference_note = (
            "FULL ORIGINAL ROUTER CORE REFERENCE (ground truth for AR-009; deferred files are intentionally omitted):"
        )
    if ar["id"] == "AR-010":
        st5_intro = (
            "Implement ONLY the Router concrete session manager for this AR. Add `pkg/router/session_manager.go` "
            "from the original reference and wire the existing Router server to call "
            "`NewSessionManager(store.Storage())`. Preserve the AR-009 Router core files "
            "`pkg/router/config.go`, `pkg/router/server.go`, and `pkg/router/handlers.go`; do not replace or "
            "delete them. Do not implement JWT key management, `pkg/router/jwt.go`, router tests, `cmd/router`, "
            "or dependency metadata in AR-010. You may update only `pkg/api/errors.go` outside `pkg/router` if "
            "needed to add the original API error helpers used by the session manager. Keep the JWT collaborator "
            "as the existing narrow `tokenSigner` interface until AR-011."
        )
        previous_ctx_limit = 6500
        original_snippets_limit = 35000
        original_reference_note = (
            "FULL ORIGINAL ROUTER SESSION MANAGER REFERENCE (ground truth for AR-010; JWT is intentionally omitted):"
        )
    if ar["id"] == "AR-011":
        st5_intro = (
            "Implement ONLY Router JWT key management for this AR. Add `pkg/router/jwt.go` from the original "
            "reference and wire the existing Router server and forwarding handler to use `*JWTManager`. Preserve "
            "`pkg/router/config.go`, `pkg/router/server.go`, `pkg/router/handlers.go`, and "
            "`pkg/router/session_manager.go`; do not replace the router core or session manager. Do not create "
            "router tests, `cmd/router`, store/common rewrites, or alternate JWT interfaces. Update `go.mod` and "
            "`go.sum` only as needed to add the original `github.com/golang-jwt/jwt/v5 v5.2.2` dependency."
        )
        previous_ctx_limit = 6500
        original_snippets_limit = 55000
        original_reference_note = (
            "FULL ORIGINAL ROUTER JWT REFERENCE (ground truth for AR-011; tests and cmd/router are intentionally omitted):"
        )
    if ar["id"] == "AR-012":
        st5_intro = (
            "Implement ONLY the Store contract split for this AR. Replace the earlier temporary `pkg/store/store.go` "
            "empty implementation with real contract files: `pkg/store/interface.go`, `pkg/store/error.go`, and a "
            "compileable `pkg/store/singleton.go` surface. Do not create Redis or Valkey backend files, tests, "
            "mock stores, no-op Store method implementations, `initRedisStore`/`initValkeyStore` placeholders, or "
            "dependency metadata changes. The singleton may return explicit deferred-provider errors until AR-013 "
            "and AR-014 implement the concrete backends, but it must not return an empty Store implementation."
        )
        previous_ctx_limit = 6000
        original_snippets_limit = 30000
        original_reference_note = (
            "LIMITED ORIGINAL STORE CONTRACT REFERENCE (ground truth for AR-012; Redis/Valkey backends are intentionally omitted):"
        )
    if ar["id"] == "AR-042":
        st5_intro = (
            "Implement ONLY the fixed Docusaurus scaffold for this AR. This is not a full documentation "
            "writing task: do not copy or recreate the original project's complete docs. Write the fixed "
            "file manifest described in the AR-specific scope, keep markdown concise, then stop."
        )
        previous_ctx_limit = 5000
        original_snippets_limit = 2500
        original_reference_note = (
            "LIMITED ORIGINAL REFERENCE (use only for Docusaurus layout/config patterns; do not copy full docs):"
        )
    if ar["id"] == "AR-043":
        st5_intro = (
            "Extend ONLY the fixed Docusaurus docs content for this AR. This is a concise architecture and API "
            "documentation pass, not a full manual rewrite. Write the fixed AR-043 markdown page manifest under "
            "docs/docs, update sidebars as needed, keep pages compact, then stop."
        )
        previous_ctx_limit = 6000
        original_snippets_limit = 4000
        original_reference_note = (
            "LIMITED ORIGINAL DOC REFERENCE (extract structure and facts; do not copy long design proposals):"
        )
    if ar["id"] == "AR-035":
        st5_intro = (
            "Implement ONLY the generated `client-go/` tree for this AR. Recreate the real Kubernetes "
            "code-generator v0.34.1 output file-by-file from the full original client-go reference below. "
            "Do not hand-roll simplified clients or older pre-generics client-go code."
        )
        previous_ctx_limit = 5000
        original_snippets_limit = 90000
        original_reference_note = (
            "FULL ORIGINAL CLIENT-GO REFERENCE (ground truth — recreate these 25 generated Go files under client-go/):"
        )
    if ar["id"] == "AR-036":
        st5_intro = (
            "Implement ONLY the Dify plugin package under `integrations/dify-plugin/` for this AR. "
            "Recreate the real plugin package file set from the original reference below, including manifest, "
            "provider/tool descriptors, Python provider/tool code, requirements, docs, .difyignore, and valid PNG assets. "
            "Do not create PCAP analyzer, FastAPI, Dockerfile, Kubernetes deployment, or example files."
        )
        previous_ctx_limit = 5000
        original_snippets_limit = 30000
        original_reference_note = (
            "FULL ORIGINAL DIFY PLUGIN REFERENCE (ground truth — recreate this plugin package under integrations/dify-plugin/):"
        )
    if ar["id"] == "AR-037":
        st5_intro = (
            "Implement ONLY the PCAP analyzer example under `example/pcap-analyzer/` for this AR. "
            "Recreate the real five-file example from the original reference below: FastAPI analyzer app, pinned "
            "requirements, uv Dockerfile, Kubernetes Deployment, and README. Do not modify the Dify plugin."
        )
        previous_ctx_limit = 5000
        original_snippets_limit = 45000
        original_reference_note = (
            "FULL ORIGINAL PCAP ANALYZER REFERENCE (ground truth — recreate this example under example/pcap-analyzer/):"
        )
    if ar["id"] == "AR-038":
        st5_intro = (
            "Implement ONLY the workloadmanager Go unit test files for this AR. Recreate the real eight `_test.go` "
            "files under `pkg/workloadmanager/` from the original reference below. Do not modify production Go code, "
            "dependency metadata, or tests outside `pkg/workloadmanager/`."
        )
        previous_ctx_limit = 5000
        original_snippets_limit = 90000
        original_reference_note = (
            "FULL ORIGINAL WORKLOADMANAGER TEST REFERENCE (ground truth — recreate these eight Go test files):"
        )
    critical_text = (
        "CRITICAL:\n"
        "1. Write COMPLETE, working code — no placeholders, no TODOs, no stubs\n"
        "2. Write unit tests for every component\n"
        "3. Follow Go/Python best practices\n"
        "4. Handle errors properly\n"
        "5. You MUST use tool calls to WRITE files to disk\n"
        "6. Match the original code's API contracts, function signatures, and behavior\n"
        f"7. Record the source changes in `{change_dir}/implementation.md` before completion\n"
        "8. Do not report completion unless files were actually created or modified"
    )
    if ar["id"] in WORKLOADMANAGER_PRODUCTION_AR_IDS:
        critical_text = (
            "CRITICAL:\n"
            "1. Write COMPLETE production code matching the original WorkloadManager APIs — no placeholders, TODOs, or stubs\n"
            "2. Do not create workloadmanager or common/types `_test.go` files in AR-004..AR-008; "
            "WorkloadManager tests are intentionally deferred to AR-038\n"
            "3. Follow Go best practices and preserve the original Go 1.24.4/toolchain go1.24.9 dependency baseline\n"
            "4. Handle errors properly and keep local imports aligned with real directories\n"
            "5. You MUST use tool calls to WRITE files to disk\n"
            "6. Match the original code's API contracts, function signatures, file names, and route wiring\n"
            f"7. Record the source changes in `{change_dir}/implementation.md` before completion\n"
            "8. Do not report completion unless files were actually created or modified"
        )
    if ar["id"] == "AR-009":
        critical_text = (
            "CRITICAL:\n"
            "1. Write COMPLETE Router core code matching the original config/server/handlers contracts — no placeholders, TODOs, or stubs\n"
            "2. Create or modify only `pkg/router/config.go`, `pkg/router/server.go`, and `pkg/router/handlers.go`\n"
            "3. Do not create `pkg/router/*_test.go`, `pkg/router/jwt*.go`, `pkg/router/session*.go`, `cmd/router`, or shared package files\n"
            "4. Preserve existing `go.mod` and `go.sum`; the dependency baseline already exists from earlier ARs\n"
            "5. Use `*types.SandboxInfo` and the existing shared `types.SandboxEntryPoint`; do not create local sandbox structs, conversion shims, or `type JWTManager interface`\n"
            "6. Match the real health routes, invocation routes, concurrency limit, reverse proxy behavior, and session header handling\n"
            "7. Do not report completion unless files were actually created or modified"
        )
    if ar["id"] == "AR-042":
        critical_text = (
            "CRITICAL:\n"
            "1. Write only the fixed docs scaffold files listed in the AR-specific scope; no extra markdown pages\n"
            "2. Keep every markdown page under 80 lines where possible and always under 120 lines\n"
            "3. Use real Docusaurus 3 config that builds with `npm run build`\n"
            "4. Do not run npm/yarn/pnpm/npx and do not leave generated artifacts or lockfiles\n"
            "5. You MUST use tool calls to WRITE files to disk\n"
            "6. Record what you changed in changes/{ar_id}/implementation.md\n"
            "7. Stop after writing the scaffold; do not expand into full manuals"
        ).format(ar_id=ar["id"])
    if ar["id"] == "AR-043":
        critical_text = (
            "CRITICAL:\n"
            "1. Write only the AR-043 docs pages listed in the AR-specific scope; no docs/src markdown pages\n"
            "2. Keep every markdown page under 180 lines and avoid copying full original design documents\n"
            "3. Update docs/sidebars.ts so the new architecture and API pages are navigable\n"
            "4. Do not run npm/yarn/pnpm/npx and do not leave generated artifacts or lockfiles\n"
            "5. You MUST use tool calls to WRITE files to disk\n"
            "6. Record what you changed in changes/{ar_id}/implementation.md\n"
            "7. Stop after the concise architecture/API documentation is linked and buildable"
        ).format(ar_id=ar["id"])
    generated_artifact_policy = (
        "Do NOT vendor dependency directories or generated build outputs such as `node_modules/`, "
        "`.docusaurus/`, `build/`, `dist/`, or `coverage/`; source/config/docs and lockfiles are enough.\n"
    )
    if ar["id"] in {"AR-042", "AR-043"}:
        generated_artifact_policy = (
            "Do NOT execute npm, npx, yarn, or pnpm commands in this model stage. "
            "The benchmark harness runs install/build checks separately after you return. "
            "Do NOT vendor dependency directories, lockfiles, or generated build outputs such as "
            "`node_modules/`, `package-lock.json`, `pnpm-lock.yaml`, `yarn.lock`, `.docusaurus/`, "
            "`build/`, `dist/`, or `coverage/`; source/config/docs are enough.\n"
        )

    verification_scope_note = ""
    if ar["id"] in WORKLOADMANAGER_PRODUCTION_AR_IDS:
        verification_scope_note = (
            "For this WorkloadManager production AR, do not mark missing `pkg/workloadmanager/*_test.go` files "
            "as a failure; those tests are intentionally scheduled for AR-038. Treat `go 1.24.4` and "
            "`toolchain go1.24.9` as the required original AgentCube baseline, not as a compatibility issue. "
            "Shared types must be documented as `pkg/common/types/{types.go,sandbox.go}`, not `pkg/common/types.go`. "
        )

    prompts = {
        "ST-0": (
            f"{common}\n"
            f"Initialize a new OpenSpec change for the agentcube project:\n\n"
            f"{ar_desc}\n\n"
            f"Create this exact scaffold:\n"
            f"- {change_dir}/.openspec.yaml\n"
            f"- {change_dir}/README.md\n"
            f"- {change_dir}/changelog/entries.md\n\n"
            f"Do NOT write implementation code yet."
        ),
        "ST-1": (
            f"{common}\n"
            f"Write proposal.md for the agentcube project:\n\n"
            f"{ar_desc}\n\n"
            f"Relevant specs:\n{spec_ctx}\n\n"
            f"Write exactly: {change_dir}/proposal.md\n"
            f"Include: purpose, scope, impact analysis, alternatives considered, acceptance criteria."
        ),
        "ST-2": (
            f"{common}\n"
            f"Write delta-spec.md (GIVEN/WHEN/THEN scenarios) for the agentcube project:\n\n"
            f"{ar_desc}\n\n"
            f"Base specs:\n{spec_ctx}\n\n"
            f"Previous artifacts:\n{previous_ctx[:8000]}\n\n"
            f"Write exactly: {change_dir}/delta-spec.md\n"
            f"Use OpenSpec format. Each requirement must have acceptance scenarios."
        ),
        "ST-3": (
            f"{common}\n"
            f"Write design.md with technical implementation details for the agentcube project:\n\n"
            f"{ar_desc}\n\n"
            f"Specs:\n{spec_ctx}\n\n"
            f"Previous artifacts:\n{previous_ctx[:8000]}\n\n"
            f"Write exactly: {change_dir}/design.md\n"
            f"Include: architecture, data structures, API contracts, error handling, testing strategy."
        ),
        "ST-4": (
            f"{common}\n"
            f"Write tasks.md checklist for the agentcube project:\n\n"
            f"{ar_desc}\n\n"
            f"Previous artifacts:\n{previous_ctx[:8000]}\n\n"
            f"Write exactly: {change_dir}/tasks.md\n"
            f"Break into atomic, independently verifiable implementation and test tasks."
        ),
        "ST-5": (
            f"{common}\n"
            f"{st5_intro}\n\n"
            f"{ar_desc}\n\n"
            f"{('AR-specific scope: ' + ar_scope_note + chr(10) + chr(10)) if ar_scope_note else ''}"
            f"Previous SDD artifacts:\n{previous_ctx[:previous_ctx_limit]}\n\n"
            f"{original_reference_note}\n"
            f"{original_snippets[:original_snippets_limit] if original_snippets else '(No original code available — follow specs strictly)'}\n\n"
            f"Target implementation area: {ar['module']}/ or the closest matching project path.\n"
            f"Implementation code MUST be written under project root target paths, not under `{change_dir}/`.\n"
            f"Allowed implementation paths for this AR: {allowed_paths_text}.\n"
            f"Do NOT create or modify source files outside these allowed implementation paths for this AR. "
            f"{dependency_metadata_policy}"
            f"{generated_artifact_policy}"
            f"The `{change_dir}/` directory is only for SDD documents and notes.\n"
            f"Mandatory ST-5 artifact: write exactly `{change_dir}/implementation.md` with a concise summary "
            "of changed source files, validation performed, and known deferrals. Do not use alternate names "
            "such as `implementation-notes.md`, `summary.md`, or `verification.md` for this stage.\n\n"
            f"{critical_text}"
        ),
        "ST-6": (
            f"{common}\n"
            f"Verify implementation against spec for the agentcube project:\n\n"
            f"{ar_desc}\n\n"
            f"Spec:\n{spec_ctx[:3000]}\n\n"
            f"Write exactly: {change_dir}/verification.md\n"
            f"Check: Are all requirements met? Are tests passing?\n"
            f"{verification_scope_note}"
            f"Do NOT run shell commands. The benchmark harness runs local checks separately. "
            f"Inspect the files already in the workspace and write a concise verification report with explicit unknowns. "
            f"Do not fabricate passing tests. Keep the report under 120 lines and do not copy specs or source files."
        ),
        "ST-6.5": (
            f"Compare your generated code against the original agentcube source code.\n\n"
            f"{ar_desc}\n\n"
            f"Report:\n"
            f"1. Which original files have corresponding generated files?\n"
            f"2. Are all function signatures and API endpoints preserved?\n"
            f"3. Are there any behavioral differences?\n"
            f"4. What is missing or different?\n\n"
            f"Output a brief equivalence report."
        ),
        "ST-7": (
            f"{common}\n"
            f"Archive change for the agentcube project:\n\n"
            f"{ar_desc}\n\n"
            f"Append archive notes to {change_dir}/changelog/entries.md and update {change_dir}/README.md.\n"
            f"Do NOT modify project source code during archive.\n"
            f"Summarize: What was completed, what was deferred, and validation status. "
            f"Keep the archive notes under 80 lines and do not copy specs, tests, or implementation code."
        ),
    }
    return prompts.get(stage_id, f"Process {stage_id} for {ar_desc}")


def _is_source_like(path: Path, lang: str) -> bool:
    name = path.name
    suffix = path.suffix.lower()
    if name in {"Dockerfile", "Makefile", "requirements.txt", "pyproject.toml"}:
        return True
    if name.startswith("Dockerfile.") or suffix == ".dockerfile":
        return True
    return suffix in SOURCE_EXTS_BY_LANG.get(lang, {".go", ".py", ".yaml", ".yml", ".md"})


def _is_implementation_support_file(path: Path) -> bool:
    suffix = path.suffix.lower()
    name = path.name
    return (
        name in IMPLEMENTATION_SUPPORT_NAMES
        or name.startswith("Dockerfile.")
        or suffix in IMPLEMENTATION_SUPPORT_EXTS
    )


def _is_project_implementation_file(rel: str, path: Path, lang: str) -> bool:
    if rel.startswith("changes/"):
        return False
    if rel in {"go.mod", "go.sum", "requirements.txt", "pyproject.toml"}:
        return False
    if path.name in LOCKFILE_NAMES:
        return False
    if not _is_source_like(path, lang):
        return False
    suffix = path.suffix.lower()
    name = path.name
    if lang == "Go":
        return suffix == ".go" or name in {"go.mod", "go.sum"}
    if lang == "Python":
        return suffix == ".py" or _is_implementation_support_file(path)
    if lang == "YAML":
        return suffix in {".yaml", ".yml"}
    if lang == "Dockerfile":
        return name == "Dockerfile" or name.startswith("Dockerfile.") or suffix == ".dockerfile"
    if lang == "Makefile":
        return name == "Makefile" or suffix == ".mk"
    if lang == "TypeScript":
        return suffix in {".ts", ".tsx", ".js", ".jsx", ".json", ".md", ".mdx", ".css"}
    if lang == "Markdown":
        return suffix in {".md", ".mdx"}
    return True


def _snapshot_workspace(workspace: Path, lang: str) -> dict[str, dict]:
    """Return hash/LOC snapshot for generated files in the workspace."""
    snap: dict[str, dict] = {}
    for dirpath, dirnames, filenames in os.walk(workspace):
        dirnames[:] = [d for d in dirnames if d not in SKIP_SCAN_DIRS]
        for fn in filenames:
            path = Path(dirpath) / fn
            rel = str(path.relative_to(workspace))
            if rel == ".sdd_prompt.md" or rel.startswith("specs/"):
                continue
            if not _is_source_like(path, lang) and not rel.startswith("changes/"):
                continue
            try:
                data = path.read_bytes()
            except OSError:
                continue
            text = data.decode("utf-8", errors="replace")
            snap[rel] = {
                "hash": hashlib.sha256(data).hexdigest(),
                "loc": len(text.splitlines()),
                "source": _is_source_like(path, lang),
                "implementation": _is_project_implementation_file(rel, path, lang),
                "data": data,
            }
    return snap


def _find_generated_artifact_dirs(workspace: Path) -> list[str]:
    """Find generated dependency/build directories that should not persist in benchmark samples."""
    found: list[str] = []
    for dirpath, dirnames, _ in os.walk(workspace):
        dirnames[:] = [d for d in dirnames if d not in {".git", ".opencode"}]
        for dirname in list(dirnames):
            if dirname in GENERATED_ARTIFACT_DIRS:
                rel = str((Path(dirpath) / dirname).relative_to(workspace))
                found.append(rel)
                dirnames.remove(dirname)
    return sorted(found)


def _remove_generated_artifact_dirs(workspace: Path, rel_dirs: list[str]) -> int:
    removed = 0
    for rel in rel_dirs:
        target = workspace / rel
        if target.exists() and target.is_dir():
            shutil.rmtree(target, ignore_errors=True)
            removed += 1
    return removed


def _is_generated_artifact_file(path: Path, workspace: Path) -> bool:
    if path.name in LOCKFILE_NAMES:
        return True
    if path.name in GENERATED_CACHE_FILE_NAMES:
        return True
    if path.parent != workspace:
        return False
    if path.name in GENERATED_BINARY_NAMES or path.name.endswith(".test"):
        return True
    try:
        return path.read_bytes()[:4] == b"\x7fELF"
    except OSError:
        return False


def _find_generated_artifact_files(workspace: Path, before: dict[str, dict]) -> list[str]:
    """Find generated package-manager files and root build binaries."""
    found: list[str] = []
    for dirpath, dirnames, filenames in os.walk(workspace):
        dirnames[:] = [
            d for d in dirnames
            if d not in {".git", ".opencode"} | GENERATED_ARTIFACT_DIRS
        ]
        for filename in filenames:
            path = Path(dirpath) / filename
            if not _is_generated_artifact_file(path, workspace):
                continue
            rel = str(path.relative_to(workspace))
            is_root_binary = path.parent == workspace and (
                filename in GENERATED_BINARY_NAMES
                or filename.endswith(".test")
            )
            if rel not in before or is_root_binary:
                found.append(rel)
    return sorted(found)


def _remove_generated_artifact_files(workspace: Path, rel_files: list[str]) -> int:
    removed = 0
    for rel in rel_files:
        target = workspace / rel
        if target.exists() and target.is_file():
            try:
                target.unlink()
                removed += 1
            except OSError:
                pass
    return removed


def _cleanup_generated_artifacts(workspace: Path, before: dict[str, dict]) -> tuple[list[str], list[str]]:
    generated_dirs = _find_generated_artifact_dirs(workspace)
    generated_files = _find_generated_artifact_files(workspace, before)
    if generated_dirs:
        _remove_generated_artifact_dirs(workspace, generated_dirs)
    if generated_files:
        _remove_generated_artifact_files(workspace, generated_files)
    return generated_dirs, generated_files


def _blocking_generated_artifacts(generated_dirs: list[str], generated_files: list[str]) -> list[str]:
    blocking = [
        rel for rel in generated_dirs
        if Path(rel).name not in NON_BLOCKING_GENERATED_ARTIFACT_DIRS
    ]
    blocking.extend(
        rel for rel in generated_files
        if Path(rel).name not in NON_BLOCKING_GENERATED_ARTIFACT_FILES
    )
    return blocking


def _snapshot_delta(before: dict[str, dict], after: dict[str, dict]) -> dict:
    added = [p for p in after if p not in before]
    modified = [p for p in after if p in before and after[p]["hash"] != before[p]["hash"]]
    changed = sorted(added + modified)
    source_changed = [p for p in changed if after[p].get("source")]
    implementation_changed = [p for p in changed if after[p].get("implementation")]
    loc_delta = 0
    for p in implementation_changed:
        old_loc = before.get(p, {}).get("loc", 0)
        loc_delta += max(0, after[p]["loc"] - old_loc)
    return {
        "added": sorted(added),
        "modified": sorted(modified),
        "changed": changed,
        "source_changed": sorted(source_changed),
        "implementation_changed": sorted(implementation_changed),
        "loc_delta": loc_delta,
    }


def _restore_workspace_files(workspace: Path, before: dict[str, dict], rel_files: list[str]) -> int:
    restored = 0
    for rel in rel_files:
        path = workspace / rel
        if rel in before:
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(before[rel]["data"])
                restored += 1
            except OSError:
                pass
        else:
            try:
                path.unlink()
                restored += 1
            except FileNotFoundError:
                restored += 1
            except OSError:
                pass
    return restored


def _forbidden_change_source_files(ar: dict, rel_files: list[str]) -> list[str]:
    prefix = f"changes/{ar['id']}/"
    forbidden: list[str] = []
    for rel in rel_files:
        if not rel.startswith(prefix):
            continue
        name = Path(rel).name
        suffix = Path(rel).suffix.lower()
        if name in CHANGE_DOC_NAMES or suffix in CHANGE_DOC_EXTS:
            continue
        forbidden.append(rel)
    return sorted(forbidden)


def _forbidden_dependency_metadata_files(ar: dict, rel_files: list[str]) -> list[str]:
    forbidden = FORBIDDEN_DEPENDENCY_METADATA_BY_AR.get(ar["id"], set())
    if not forbidden:
        return []
    return sorted(rel for rel in rel_files if rel in forbidden)


def _in_scope_implementation_files(ar: dict, rel_files: list[str]) -> tuple[list[str], list[str]]:
    allowed_prefixes = _allowed_implementation_prefixes(ar)
    in_scope: list[str] = []
    out_scope: list[str] = []
    for rel in rel_files:
        if rel in DEPENDENCY_METADATA_FILES:
            continue
        if not allowed_prefixes or allowed_prefixes == ["root"]:
            ok = "/" not in rel
        else:
            ok = any(
                rel == prefix or rel.startswith(prefix + "/")
                for prefix in allowed_prefixes
            )
        if ok:
            in_scope.append(rel)
        else:
            out_scope.append(rel)
    return sorted(in_scope), sorted(out_scope)


def _reserved_implementation_files(ar: dict, rel_files: list[str]) -> list[str]:
    patterns = AR_RESERVED_IMPLEMENTATION_PATTERNS.get(ar["id"], [])
    reserved: list[str] = []
    for rel in rel_files:
        if ar.get("type") == "测试" and ar.get("lang") == "Go":
            if rel.endswith(".go") and not rel.endswith("_test.go"):
                module_path = ar.get("module", "").strip("/")
                if (module_path == "test" or module_path.startswith("test/")) and (
                    rel == module_path or rel.startswith(module_path + "/")
                ):
                    continue
                reserved.append(rel)
                continue
        if any(fnmatch.fnmatch(rel, pattern) for pattern in patterns):
            reserved.append(rel)
    return sorted(set(reserved))


def _loc_delta_for_files(before: dict[str, dict], after: dict[str, dict], rel_files: list[str]) -> int:
    total = 0
    for rel in rel_files:
        if rel not in after:
            continue
        old_loc = before.get(rel, {}).get("loc", 0)
        total += max(0, after[rel]["loc"] - old_loc)
    return total


def _read_stage_artifacts(workspace: Path, ar_id: str) -> dict[str, str]:
    change_dir = workspace / "changes" / ar_id
    files = {
        "proposal.md": change_dir / "proposal.md",
        "delta-spec.md": change_dir / "delta-spec.md",
        "design.md": change_dir / "design.md",
        "tasks.md": change_dir / "tasks.md",
        "implementation.md": change_dir / "implementation.md",
        "verification.md": change_dir / "verification.md",
    }
    out = {}
    for name, path in files.items():
        if path.exists():
            out[name] = path.read_text(encoding="utf-8", errors="replace")
    return out


def _validate_stage_output(
    workspace: Path,
    ar: dict,
    stage_id: str,
    delta: dict,
    in_scope_impl: list[str] | None = None,
    out_scope_impl: list[str] | None = None,
    scoped_loc_delta: int | None = None,
) -> list[str]:
    """Detect empty stages, missing artifacts, and hollow implementations."""
    errors: list[str] = []
    change_dir = workspace / "changes" / ar["id"]
    required = {
        "ST-0": [change_dir / ".openspec.yaml", change_dir / "README.md"],
        "ST-1": [change_dir / "proposal.md"],
        "ST-2": [change_dir / "delta-spec.md"],
        "ST-3": [change_dir / "design.md"],
        "ST-4": [change_dir / "tasks.md"],
        "ST-5": [change_dir / "implementation.md"],
        "ST-6": [change_dir / "verification.md"],
        "ST-7": [change_dir / "changelog" / "entries.md"],
    }
    for path in required.get(stage_id, []):
        if not path.exists():
            errors.append(f"missing required artifact: {path.relative_to(workspace)}")
        elif path.stat().st_size < 80:
            errors.append(f"artifact too small: {path.relative_to(workspace)}")

    allowed_stage_docs = {
        "ST-0": {
            f"changes/{ar['id']}/.openspec.yaml",
            f"changes/{ar['id']}/README.md",
            f"changes/{ar['id']}/changelog/entries.md",
        },
        "ST-1": {f"changes/{ar['id']}/proposal.md"},
        "ST-2": {f"changes/{ar['id']}/delta-spec.md"},
        "ST-3": {f"changes/{ar['id']}/design.md"},
        "ST-4": {f"changes/{ar['id']}/tasks.md"},
        "ST-5": {f"changes/{ar['id']}/implementation.md"},
        "ST-6": {f"changes/{ar['id']}/verification.md"},
        "ST-7": {
            f"changes/{ar['id']}/README.md",
            f"changes/{ar['id']}/changelog/entries.md",
        },
    }.get(stage_id, set())
    change_prefix = f"changes/{ar['id']}/"
    early_or_extra_docs: list[str] = []
    for rel in delta["changed"]:
        if not rel.startswith(change_prefix) or rel in allowed_stage_docs:
            continue
        rel_path = Path(rel)
        if rel_path.name in CHANGE_DOC_NAMES or rel_path.suffix.lower() in CHANGE_DOC_EXTS:
            early_or_extra_docs.append(rel)
    if early_or_extra_docs:
        errors.append(
            f"{stage_id} modified SDD artifacts outside its stage boundary: "
            + ", ".join(early_or_extra_docs[:10])
        )

    artifact_line_limits = _sdd_artifact_line_limits(ar)
    limit = artifact_line_limits.get(stage_id)
    if limit:
        for path in required.get(stage_id, []):
            if not path.exists():
                continue
            try:
                line_count = len(path.read_text(encoding="utf-8", errors="replace").splitlines())
            except OSError:
                continue
            if line_count > limit:
                errors.append(
                    f"{ar['id']} {path.relative_to(workspace)} exceeds concise artifact limit: "
                    f"{line_count} > {limit} lines"
                )

    if stage_id in {"ST-0", "ST-1", "ST-2", "ST-3", "ST-4", "ST-6", "ST-7"} and not delta["changed"]:
        errors.append("no files were created or modified")

    if stage_id == "ST-5":
        source_changed = in_scope_impl if in_scope_impl is not None else delta["implementation_changed"]
        out_scope = out_scope_impl if out_scope_impl is not None else []
        loc_delta = scoped_loc_delta if scoped_loc_delta is not None else delta["loc_delta"]
        if out_scope:
            allowed = ", ".join(_allowed_implementation_prefixes(ar))
            errors.append(
                "implementation modified files outside allowed paths "
                f"({allowed}): " + ", ".join(out_scope[:10])
            )
        reserved_impl = _reserved_implementation_files(ar, source_changed + out_scope)
        if reserved_impl:
            errors.append(
                "implementation modified files reserved for another AR: "
                + ", ".join(reserved_impl[:10])
            )
        if not source_changed:
            errors.append("implementation stage did not create or modify project source files outside changes/")
        default_min_loc = 10 if ar["type"] in {"测试"} else min(30, max(10, ar.get("est_loc", 50) // 6))
        min_loc = MIN_IMPLEMENTATION_LOC_BY_AR.get(ar["id"], default_min_loc)
        if loc_delta < min_loc:
            errors.append(f"implementation LOC delta below minimum: {loc_delta} < {min_loc}")

        placeholder_hits = _scan_placeholder_hits(workspace, source_changed + out_scope)
        if placeholder_hits:
            preview = ", ".join(placeholder_hits[:5])
            errors.append(f"placeholder/stub markers found: {preview}")
        if ar.get("lang") == "Go":
            bad_imports = _scan_missing_local_go_imports(workspace, source_changed + out_scope)
            if bad_imports:
                errors.append(
                    "Go files import local module paths that do not exist: "
                    + ", ".join(bad_imports[:8])
                )
        errors.extend(_validate_ar_specific_implementation(workspace, ar))

    if stage_id == "ST-6" and ar.get("id") in WORKLOADMANAGER_PRODUCTION_AR_IDS:
        errors.extend(_validate_workloadmanager_verification_artifact(workspace, ar))

    return errors


def _validate_workloadmanager_verification_artifact(workspace: Path, ar: dict) -> list[str]:
    """Keep WorkloadManager verification reports aligned with the AR split."""
    path = workspace / "changes" / ar["id"] / "verification.md"
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8", errors="replace")
    lower = text.lower()
    errors: list[str] = []

    forbidden_phrases = [
        ("go 1.22", "Go 1.22 compatibility is not the WorkloadManager production baseline", False),
        ("go1.22", "Go 1.22 compatibility is not the WorkloadManager production baseline", False),
        ("missing test files", "WorkloadManager tests are intentionally deferred to AR-038", True),
        ("no test files found", "WorkloadManager tests are intentionally deferred to AR-038", True),
        ("required test files", "WorkloadManager tests are intentionally deferred to AR-038", True),
        ("all required test files are absent", "WorkloadManager tests are intentionally deferred to AR-038", True),
    ]
    deferred_test_markers = [
        "ar-038",
        "defer",
        "scheduled",
        "intentionally",
        "expected",
        "later testing ar",
        "not a failure",
    ]
    for phrase, reason, allow_deferred_context in forbidden_phrases:
        for line in lower.splitlines():
            if phrase not in line:
                continue
            if allow_deferred_context and any(marker in line for marker in deferred_test_markers):
                continue
            errors.append(f"{ar['id']} verification.md contains misleading report text: {reason}")
            break

    for line in text.splitlines():
        line_lower = line.lower()
        if "pkg/common/types.go" not in line_lower:
            continue
        if any(marker in line_lower for marker in ["not `pkg/common/types.go`", "not pkg/common/types.go", "do not", "must not", "avoid"]):
            continue
        errors.append(
            f"{ar['id']} verification.md references obsolete shared-types path pkg/common/types.go"
        )
        break

    source_errors = _validate_ar_specific_implementation(workspace, ar)
    if not source_errors:
        for phrase in [
            "critical issue",
            "critical issues",
            "non-functional",
            "prevents compilation",
            "will not compile",
            "cannot compile",
        ]:
            if phrase in lower:
                errors.append(
                    f"{ar['id']} verification.md reports a blocking source issue after local validators passed: {phrase}"
                )
                break

    return errors


def _validate_ar_specific_implementation(workspace: Path, ar: dict) -> list[str]:
    errors: list[str] = []
    if ar.get("id") == "AR-004":
        return _validate_ar004_workloadmanager_framework(workspace)
    if ar.get("id") == "AR-005":
        return _validate_ar005_workloadmanager_creation(workspace)
    if ar.get("id") == "AR-006":
        return _validate_ar006_workloadmanager_lifecycle(workspace)
    if ar.get("id") == "AR-007":
        return _validate_ar007_workloadmanager_controllers(workspace)
    if ar.get("id") == "AR-008":
        return _validate_ar008_workloadmanager_gc_complete(workspace)
    if ar.get("id") == "AR-009":
        return _validate_ar009_router_core(workspace)
    if ar.get("id") == "AR-010":
        return _validate_ar010_router_session_manager(workspace)
    if ar.get("id") == "AR-011":
        return _validate_ar011_router_jwt(workspace)
    if ar.get("id") == "AR-012":
        return _validate_ar012_store_contract(workspace)
    if ar.get("id") == "AR-013":
        return _validate_ar013_redis_backend(workspace)
    if ar.get("id") == "AR-014":
        return _validate_ar014_valkey_backend(workspace)
    if ar.get("id") == "AR-015":
        return _validate_ar015_picod_execute_api(workspace)
    if ar.get("id") == "AR-016":
        return _validate_ar016_picod_file_api(workspace)
    if ar.get("id") == "AR-017":
        return _validate_ar017_picod_auth_middleware(workspace)
    if ar.get("id") == "AR-018":
        return _validate_ar018_agentd_idle_cleanup(workspace)
    if ar.get("id") == "AR-019":
        return _validate_ar019_go_service_binaries(workspace)
    if ar.get("id") == "AR-020":
        return _validate_ar020_cli_pack_command(workspace)
    if ar.get("id") == "AR-021":
        return _validate_ar021_cli_build_command(workspace)
    if ar.get("id") == "AR-022":
        return _validate_ar022_cli_publish_command(workspace)
    if ar.get("id") == "AR-023":
        return _validate_ar023_cli_invoke_status_command(workspace)
    if ar.get("id") == "AR-024":
        return _validate_ar024_cli_docker_service(workspace)
    if ar.get("id") == "AR-025":
        return _validate_ar025_cli_metadata_service(workspace)
    if ar.get("id") == "AR-026":
        return _validate_ar026_cli_providers(workspace)
    if ar.get("id") == "AR-027":
        return _validate_ar027_sdk_code_interpreter(workspace)
    if ar.get("id") == "AR-028":
        return _validate_ar028_sdk_agent_runtime(workspace)
    if ar.get("id") == "AR-029":
        return _validate_ar029_sdk_http_clients(workspace)
    if ar.get("id") == "AR-030":
        return _validate_ar030_helm_chart(workspace)
    if ar.get("id") == "AR-031":
        return _validate_ar031_helm_rbac(workspace)
    if ar.get("id") == "AR-032":
        return _validate_ar032_dockerfiles(workspace)
    if ar.get("id") == "AR-033":
        return _validate_ar033_makefile(workspace)
    if ar.get("id") == "AR-034":
        return _validate_ar034_github_workflows(workspace)
    if ar.get("id") == "AR-035":
        return _validate_ar035_client_go(workspace)
    if ar.get("id") == "AR-036":
        return _validate_ar036_dify_plugin(workspace)
    if ar.get("id") == "AR-037":
        return _validate_ar037_pcap_analyzer(workspace)
    if ar.get("id") == "AR-038":
        return _validate_ar038_workloadmanager_tests(workspace)
    if ar.get("id") not in {"AR-042", "AR-043"}:
        return errors

    docs_root = workspace / "docs"
    if not docs_root.exists():
        return errors
    if ar.get("id") == "AR-043":
        return _validate_ar043_docs(workspace, docs_root)

    overlong: list[str] = []
    misplaced: list[str] = []
    content_markdown: list[str] = []
    localized_markdown: list[str] = []
    for dirpath, dirnames, filenames in os.walk(docs_root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_SCAN_DIRS]
        for filename in filenames:
            path = Path(dirpath) / filename
            rel = str(path.relative_to(workspace))
            if path.suffix.lower() in {".md", ".mdx"}:
                if rel.startswith("docs/docs/"):
                    content_markdown.append(rel)
                if rel.startswith("docs/i18n/"):
                    localized_markdown.append(rel)
                try:
                    line_count = len(path.read_text(encoding="utf-8", errors="replace").splitlines())
                except OSError:
                    continue
                if line_count > 120:
                    overlong.append(f"{rel}:{line_count}")
                if rel.startswith("docs/guide/") or rel.startswith("docs/api/"):
                    misplaced.append(rel)
                try:
                    text = path.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    text = ""
                if re.search(r"\]\(\.\./[^)]*\.md(?:#[^)]*)?\)", text):
                    errors.append(f"AR-042 docs must not use cross-folder ../*.md links: {rel}")

    if overlong:
        errors.append(
            "AR-042 docs pages exceed 120-line scope limit: "
            + ", ".join(overlong[:8])
        )
    if misplaced:
        errors.append(
            "AR-042 markdown must live under Docusaurus default content folder docs/docs/: "
            + ", ".join(sorted(misplaced)[:8])
        )
    if len(content_markdown) > 8:
        errors.append(
            f"AR-042 must create at most 8 docs markdown pages, found {len(content_markdown)}: "
            + ", ".join(sorted(content_markdown)[:10])
        )
    expected_markdown = AR_042_DOC_MARKDOWN
    unexpected_markdown = sorted(set(content_markdown) - expected_markdown)
    missing_markdown = sorted(expected_markdown - set(content_markdown))
    if unexpected_markdown:
        errors.append(
            "AR-042 markdown pages must match the fixed docs manifest; unexpected: "
            + ", ".join(unexpected_markdown[:8])
        )
    if missing_markdown:
        errors.append(
            "AR-042 missing required docs markdown pages: "
            + ", ".join(missing_markdown[:8])
        )
    if localized_markdown:
        errors.append(
            "AR-042 must not create localized markdown copies under docs/i18n/: "
            + ", ".join(sorted(localized_markdown)[:8])
        )

    config = docs_root / "docusaurus.config.ts"
    if config.exists():
        text = config.read_text(encoding="utf-8", errors="replace")
        if "@docusaurus/plugin-content-docs" in text:
            errors.append("AR-042 must not add a second @docusaurus/plugin-content-docs plugin")
        if "prismThemes" not in text or "darkTheme: prismThemes.dracula" not in text:
            errors.append("AR-042 Docusaurus prism config must use prismThemes.github and prismThemes.dracula")
        if "img/" in text and not (docs_root / "static" / "img").exists():
            errors.append("AR-042 config references img/... but docs/static/img/ is missing")
        for img_ref in sorted(set(re.findall(r"['\"](img/[^'\"]+)['\"]", text))):
            asset = docs_root / "static" / img_ref
            if not asset.exists():
                errors.append(f"AR-042 config references missing static asset: docs/static/{img_ref}")
            elif asset.stat().st_size < 20:
                errors.append(f"AR-042 static asset is empty or too small: docs/static/{img_ref}")

    mdx_home = docs_root / "src" / "pages" / "index.mdx"
    if mdx_home.exists():
        errors.append("AR-042 React home page must be src/pages/index.tsx, not index.mdx")
    tsx_home = docs_root / "src" / "pages" / "index.tsx"
    if tsx_home.exists():
        home_text = tsx_home.read_text(encoding="utf-8", errors="replace").lstrip()
        if home_text.startswith("---"):
            errors.append("AR-042 src/pages/index.tsx must not contain MDX front matter")
        if len(re.findall(r"\bexport\s+default\b", home_text)) != 1:
            errors.append("AR-042 src/pages/index.tsx must contain exactly one default export")
    if (docs_root / "i18n" / "en").exists():
        errors.append("AR-042 must not create i18n/en files for the default locale")
    invalid_translation_files = sorted(
        str(path.relative_to(workspace))
        for path in docs_root.glob("i18n/*/docusaurus-plugin-content-docs/current.json")
    )
    if invalid_translation_files:
        errors.append(
            "AR-042 must not create Docusaurus docs current.json translation files: "
            + ", ".join(invalid_translation_files[:8])
        )
    if (docs_root / "img").exists():
        errors.append("AR-042 static assets referenced as img/... must live under docs/static/img/, not docs/img/")
    static_root = docs_root / "static"
    if static_root.exists():
        small_assets = [
            str(path.relative_to(workspace))
            for path in static_root.rglob("*")
            if path.is_file() and path.stat().st_size < 20
        ]
        if small_assets:
            errors.append(
                "AR-042 static assets must be non-empty real files: "
                + ", ".join(sorted(small_assets)[:8])
            )
    package_json = docs_root / "package.json"
    if package_json.exists():
        try:
            package_data = json.loads(package_json.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            package_data = {}
        deps = {}
        for section in ("dependencies", "devDependencies"):
            values = package_data.get(section, {})
            if isinstance(values, dict):
                deps.update(values)
        docusaurus_packages = [
            "@docusaurus/core",
            "@docusaurus/preset-classic",
            "@docusaurus/module-type-aliases",
            "@docusaurus/tsconfig",
            "@docusaurus/types",
        ]
        stale_versions = [
            f"{pkg}@{deps[pkg]}"
            for pkg in docusaurus_packages
            if pkg in deps and str(deps[pkg]) not in {"3.10.1", "^3.10.1"}
        ]
        if stale_versions:
            errors.append(
                "AR-042 Docusaurus package versions must be 3.10.1 or ^3.10.1: "
                + ", ".join(stale_versions)
            )
    return errors


def _validate_ar013_redis_backend(workspace: Path) -> list[str]:
    errors: list[str] = []
    redis_impl = workspace / "pkg/store/store_redis.go"
    redis_test = workspace / "pkg/store/store_redis_test.go"
    singleton = workspace / "pkg/store/singleton.go"

    if not redis_impl.exists():
        errors.append("AR-013 must create pkg/store/store_redis.go")
        return errors
    impl_text = redis_impl.read_text(encoding="utf-8", errors="replace")
    for token in [
        "github.com/redis/go-redis/v9",
        "makeRedisOptions",
        "REDIS_ADDR",
        "REDIS_PASSWORD_REQUIRED",
        "SetNX",
        "ZAdd",
        "ZRangeByScore",
        "UpdateSessionLastActivity",
        "redisv9.Nil",
    ]:
        if token not in impl_text:
            errors.append(f"AR-013 Redis implementation missing required behavior token: {token}")

    if not redis_test.exists():
        errors.append("AR-013 must create pkg/store/store_redis_test.go with Redis backend behavior tests")
        return errors
    test_text = redis_test.read_text(encoding="utf-8", errors="replace")
    if "miniredis" not in test_text and "redismock" not in test_text:
        errors.append("AR-013 Redis tests must use miniredis or redismock, not only Store interface mocks")
    required_test_terms = [
        "makeRedisOptions",
        "StoreSandbox",
        "GetSandboxBySessionID",
        "ListExpiredSandboxes",
        "ListInactiveSandboxes",
        "UpdateSessionLastActivity",
        "ErrNotFound",
    ]
    missing_terms = [term for term in required_test_terms if term not in test_text]
    if missing_terms:
        errors.append(
            "AR-013 Redis tests do not cover required behaviors: "
            + ", ".join(missing_terms)
        )

    if not singleton.exists():
        errors.append("AR-013 must update pkg/store/singleton.go")
    else:
        singleton_text = singleton.read_text(encoding="utf-8", errors="replace")
        for token in [
            "case redisStoreType:",
            "initRedisStore()",
            "provider = redisProvider",
            "init redis store successfully",
        ]:
            if token not in singleton_text:
                errors.append(f"AR-013 singleton wiring missing Redis token: {token}")
        lowered = singleton_text.lower()
        for forbidden in [
            "redis provider initialization failed",
            "redis backend is deferred",
            "redis backend deferred",
            "redis not implemented",
            "initValkeyStore(",
        ]:
            if forbidden.lower() in lowered:
                errors.append(f"AR-013 singleton wiring must not keep invalid provider branch: {forbidden}")

    go_mod = workspace / "go.mod"
    if go_mod.exists():
        go_mod_text = go_mod.read_text(encoding="utf-8", errors="replace")
        if "github.com/redis/go-redis/v9 v9.17.1" not in go_mod_text:
            errors.append("AR-013 go.mod missing original Redis dependency: github.com/redis/go-redis/v9 v9.17.1")
        if "miniredis" in test_text and "github.com/alicebob/miniredis/v2 v2.35.0" not in go_mod_text:
            errors.append("AR-013 go.mod missing original miniredis dependency: github.com/alicebob/miniredis/v2 v2.35.0")
    errors.extend(_validate_workloadmanager_go_mod_baseline(workspace, "AR-013"))
    return errors


def _validate_ar014_valkey_backend(workspace: Path) -> list[str]:
    errors: list[str] = []
    valkey_impl = workspace / "pkg/store/store_valkey.go"
    valkey_test = workspace / "pkg/store/store_valkey_test.go"
    singleton = workspace / "pkg/store/singleton.go"

    if not valkey_impl.exists():
        errors.append("AR-014 must create pkg/store/store_valkey.go")
        return errors
    impl_text = valkey_impl.read_text(encoding="utf-8", errors="replace")
    for token in [
        "github.com/valkey-io/valkey-go",
        "makeValkeyOptions",
        "VALKEY_ADDR",
        "VALKEY_PASSWORD_REQUIRED",
        "VALKEY_DISABLE_CACHE",
        "VALKEY_FORCE_SINGLE",
        "DisableCache",
        "ForceSingleClient",
        "valkey.IsValkeyNil",
        "DoMulti",
        "Mget",
        "UpdateSessionLastActivity",
    ]:
        if token not in impl_text:
            errors.append(f"AR-014 Valkey implementation missing required behavior token: {token}")

    if not singleton.exists():
        errors.append("AR-014 must update pkg/store/singleton.go")
    else:
        singleton_text = singleton.read_text(encoding="utf-8", errors="replace")
        for token in [
            "case valkeyStoreType:",
            "initValkeyStore()",
            "provider = valkeyProvider",
            "init valkey store successfully",
        ]:
            if token not in singleton_text:
                errors.append(f"AR-014 singleton wiring missing Valkey token: {token}")
        lowered = singleton_text.lower()
        if "valkey provider not implemented" in lowered or "valkey not implemented" in lowered:
            errors.append("AR-014 singleton wiring still contains not-implemented Valkey branch")

    if not valkey_test.exists():
        errors.append("AR-014 must create pkg/store/store_valkey_test.go with Valkey backend behavior tests")
        return errors
    test_text = valkey_test.read_text(encoding="utf-8", errors="replace")
    if "miniredis" not in test_text:
        errors.append("AR-014 Valkey tests must use miniredis as a Valkey-compatible server")
    required_test_terms = [
        "makeValkeyOptions",
        "StoreSandbox",
        "GetSandboxBySessionID",
        "ListExpiredSandboxes",
        "ListInactiveSandboxes",
        "UpdateSessionLastActivity",
        "ErrNotFound",
        "VALKEY_DISABLE_CACHE",
        "VALKEY_FORCE_SINGLE",
    ]
    missing_terms = [term for term in required_test_terms if term not in test_text]
    if missing_terms:
        errors.append(
            "AR-014 Valkey tests do not cover required behaviors: "
            + ", ".join(missing_terms)
        )
    go_mod = workspace / "go.mod"
    if go_mod.exists():
        go_mod_text = go_mod.read_text(encoding="utf-8", errors="replace")
        if "github.com/valkey-io/valkey-go v1.0.69" not in go_mod_text:
            errors.append("AR-014 go.mod missing original Valkey dependency: github.com/valkey-io/valkey-go v1.0.69")
        if "github.com/alicebob/miniredis/v2 v2.35.0" not in go_mod_text:
            errors.append("AR-014 go.mod missing original miniredis dependency: github.com/alicebob/miniredis/v2 v2.35.0")
        if "replace github.com/valkey-io/valkey-go" in go_mod_text or "github.com/valkey-io/valkey-go v0.0.0" in go_mod_text:
            errors.append("AR-014 go.mod must use direct original Valkey v1.0.69, not v0.0.0 or replace")
    errors.extend(_validate_workloadmanager_go_mod_baseline(workspace, "AR-014"))
    return errors


def _validate_ar015_picod_execute_api(workspace: Path) -> list[str]:
    errors: list[str] = []
    picod_dir = workspace / "pkg/picod"
    server = picod_dir / "server.go"
    execute = picod_dir / "execute.go"
    execute_test = picod_dir / "execute_test.go"

    if not server.exists():
        errors.append("AR-015 must create pkg/picod/server.go")
    if not execute.exists():
        errors.append("AR-015 must create pkg/picod/execute.go")
    if not execute_test.exists():
        errors.append("AR-015 must create pkg/picod/execute_test.go with command execution behavior tests")
    if errors:
        return errors

    server_text = server.read_text(encoding="utf-8", errors="replace")
    execute_text = execute.read_text(encoding="utf-8", errors="replace")
    test_text = execute_test.read_text(encoding="utf-8", errors="replace")
    impl_text = server_text + "\n" + execute_text
    picod_go_text = "\n".join(
        path.read_text(encoding="utf-8", errors="replace")
        for path in sorted(picod_dir.glob("*.go"))
    )

    for token in [
        "type Config struct",
        "type Server struct",
        "NewServer",
        "gin.New",
        "gin.Recovery",
        "HealthCheckHandler",
        'GET("/health"',
        "ReadHeaderTimeout",
        "ListenAndServe",
        "workspaceDir",
        "setWorkspace",
    ]:
        if token not in server_text:
            errors.append(f"AR-015 PicoD server missing required behavior token: {token}")
    if 'POST("/execute"' not in server_text and 'POST("/api/execute"' not in server_text:
        errors.append("AR-015 PicoD server missing execute route registration")
    if "sanitizePath" not in picod_go_text:
        errors.append("AR-015 implementation missing working-directory sanitizePath behavior")

    for token in [
        "type ExecuteRequest struct",
        "type ExecuteResponse struct",
        "TimeoutExitCode",
    ]:
        if token not in picod_go_text:
            errors.append(f"AR-015 PicoD package missing required behavior token: {token}")

    for token in [
        "ExecuteHandler",
        "ShouldBindJSON",
        "command cannot be empty",
        "time.ParseDuration",
        "context.WithTimeout",
        "exec.CommandContext",
        "cmd.Stdout",
        "cmd.Stderr",
        "ProcessState.ExitCode",
        "DeadlineExceeded",
        "req.WorkingDir",
        "req.Env",
        "cmd.Env",
    ]:
        if token not in execute_text:
            errors.append(f"AR-015 execute implementation missing required behavior token: {token}")

    forbidden_scope_tokens = [
        "AuthMiddleware",
        "LoadPublicKeyFromEnv",
        "PublicKeyEnvVar",
        "MaxBodySize",
        "jwt.",
        "UploadFileHandler",
        "DownloadFileHandler",
        "ListFilesHandler",
    ]
    forbidden_found = [token for token in forbidden_scope_tokens if token in picod_go_text]
    if forbidden_found:
        errors.append(
            "AR-015 source/tests include auth/file-management behavior reserved for later ARs: "
            + ", ".join(forbidden_found)
        )

    required_test_terms = [
        "httptest",
        "ExecuteHandler",
        "command cannot be empty",
        "Invalid timeout",
        "TimeoutExitCode",
        "WorkingDir",
        "TEST_VAR",
        "ExitCode",
        "Stderr",
        "Stdout",
    ]
    missing_terms = [term for term in required_test_terms if term not in test_text]
    if not any(term in test_text for term in ["invalid JSON", "malformed JSON", "not json"]):
        missing_terms.append("invalid/malformed JSON request")
    if missing_terms:
        errors.append(
            "AR-015 execute tests do not cover required behaviors: "
            + ", ".join(missing_terms)
        )
    return errors


def _validate_ar016_picod_file_api(workspace: Path) -> list[str]:
    errors: list[str] = []
    picod_dir = workspace / "pkg/picod"
    server = picod_dir / "server.go"
    files = picod_dir / "files.go"
    files_test = picod_dir / "files_test.go"

    if not files.exists():
        errors.append("AR-016 must create pkg/picod/files.go")
    if not files_test.exists():
        errors.append("AR-016 must create pkg/picod/files_test.go with file API behavior tests")
    if not server.exists():
        errors.append("AR-016 must update pkg/picod/server.go route wiring")
    if errors:
        return errors

    server_text = server.read_text(encoding="utf-8", errors="replace")
    files_text = files.read_text(encoding="utf-8", errors="replace")
    test_text = files_test.read_text(encoding="utf-8", errors="replace")
    picod_go_text = "\n".join(
        path.read_text(encoding="utf-8", errors="replace")
        for path in sorted(picod_dir.glob("*.go"))
    )

    route_groups = [
        ('POST("/files"', 'POST("/api/files"'),
        ('GET("/files"', 'GET("/api/files"'),
        ('GET("/files/*path"', 'GET("/api/files/*path"'),
    ]
    for group in route_groups:
        if not any(token in server_text for token in group):
            errors.append("AR-016 PicoD server missing file route registration: " + " or ".join(group))

    for token in [
        "type UploadFileRequest struct",
        "type FileEntry struct",
        "type ListFilesResponse struct",
        "UploadFileHandler",
        "DownloadFileHandler",
        "ListFilesHandler",
        "ShouldBindJSON",
        "sanitizePath",
        "os.MkdirAll",
        "os.WriteFile",
        "os.ReadFile",
        "os.ReadDir",
        "strconv.ParseUint",
        "filepath.Dir",
        "http.StatusBadRequest",
        "http.StatusNotFound",
    ]:
        if token not in files_text:
            errors.append(f"AR-016 file implementation missing required behavior token: {token}")

    forbidden_scope_tokens = [
        "AuthMiddleware",
        "LoadPublicKeyFromEnv",
        "PublicKeyEnvVar",
        "MaxBodySize",
        "jwt.",
    ]
    forbidden_found = [token for token in forbidden_scope_tokens if token in picod_go_text]
    if forbidden_found:
        errors.append(
            "AR-016 source/tests include auth behavior reserved for AR-017: "
            + ", ".join(forbidden_found)
        )

    required_test_terms = [
        "httptest",
        "UploadFileHandler",
        "DownloadFileHandler",
        "ListFilesHandler",
        "path traversal",
        "UploadFileRequest",
        "ListFilesResponse",
        "not found",
        "mode",
        "content",
    ]
    missing_terms = [term for term in required_test_terms if term not in test_text]
    if missing_terms:
        errors.append(
            "AR-016 file tests do not cover required behaviors: "
            + ", ".join(missing_terms)
        )
    return errors


def _validate_ar017_picod_auth_middleware(workspace: Path) -> list[str]:
    errors: list[str] = []
    picod_dir = workspace / "pkg/picod"
    auth = picod_dir / "auth.go"
    auth_test = picod_dir / "auth_test.go"
    server = picod_dir / "server.go"

    if not auth.exists():
        errors.append("AR-017 must create pkg/picod/auth.go")
    if not auth_test.exists():
        errors.append("AR-017 must create pkg/picod/auth_test.go")
    if not server.exists():
        errors.append("AR-017 must update pkg/picod/server.go auth wiring")
    if errors:
        return errors

    auth_text = auth.read_text(encoding="utf-8", errors="replace")
    test_text = auth_test.read_text(encoding="utf-8", errors="replace")
    server_text = server.read_text(encoding="utf-8", errors="replace")

    for token in [
        "type AuthManager struct",
        "NewAuthManager",
        "LoadPublicKeyFromEnv",
        "PublicKeyEnvVar",
        "MaxBodySize",
        "PICOD_AUTH_PUBLIC_KEY",
        "pem.Decode",
        "x509.ParsePKIXPublicKey",
        "rsa.PublicKey",
        "sync.RWMutex",
        "AuthMiddleware",
        "Authorization",
        "Bearer",
        "jwt.Parse",
        "jwt.SigningMethodRSA",
        "jwt.WithExpirationRequired",
        "jwt.WithIssuedAt",
        "http.MaxBytesReader",
        "c.Abort",
    ]:
        if token not in auth_text:
            errors.append(f"AR-017 auth implementation missing required behavior token: {token}")

    for token in [
        "authManager",
        "NewAuthManager",
        "LoadPublicKeyFromEnv",
        "Group(\"/api\")",
        "AuthMiddleware",
        ".Use(",
        "GET(\"/health\"",
        "POST(\"/execute\"",
        "POST(\"/files\"",
        "GET(\"/files\"",
        "GET(\"/files/*path\"",
    ]:
        if token not in server_text:
            errors.append(f"AR-017 server auth wiring missing required token: {token}")

    required_test_terms = [
        "generateTestRSAKeyPair",
        "LoadPublicKeyFromEnv",
        "Bearer",
        "HS256",
        "MaxBodySize",
        "jwt.NewWithClaims",
    ]
    missing_terms = [term for term in required_test_terms if term not in test_text]
    if not any(term in test_text for term in [
        "missing Authorization",
        "Missing Authorization",
        "MissingHeader",
        "MissingAuthorization",
    ]):
        missing_terms.append("missing Authorization")
    if not any(term in test_text for term in ["expired token", "ExpiredToken", "expired"]):
        missing_terms.append("expired token")
    if not any(term in test_text for term in [
        "invalid signature",
        "invalid token signature",
        "invalid JWT signature",
        "InvalidSignature",
        "InvalidJWTSignature",
    ]):
        missing_terms.append("invalid signature")
    if missing_terms:
        errors.append(
            "AR-017 auth tests do not cover required behaviors: "
            + ", ".join(missing_terms)
        )
    return errors


def _validate_ar018_agentd_idle_cleanup(workspace: Path) -> list[str]:
    errors: list[str] = []
    agentd_dir = workspace / "pkg/agentd"
    agentd = agentd_dir / "agentd.go"
    tests = agentd_dir / "agentd_test.go"
    main = workspace / "cmd/agentd/main.go"
    defaults = workspace / "pkg/workloadmanager/defaults.go"
    types = agentd_dir / "types.go"
    out_of_scope_agents = workspace / "pkg/apis/agents"

    if not agentd.exists():
        errors.append("AR-018 must create pkg/agentd/agentd.go")
    if not tests.exists():
        errors.append("AR-018 must create pkg/agentd/agentd_test.go")
    if not main.exists():
        errors.append("AR-018 must create cmd/agentd/main.go")
    if out_of_scope_agents.exists() and any(p.is_file() for p in out_of_scope_agents.rglob("*")):
        errors.append("AR-018 must not create pkg/apis/agents; sandbox support must be external or local to pkg/agentd")
    if errors:
        return errors

    agentd_text = agentd.read_text(encoding="utf-8", errors="replace")
    test_text = tests.read_text(encoding="utf-8", errors="replace")
    main_text = main.read_text(encoding="utf-8", errors="replace")
    defaults_text = defaults.read_text(encoding="utf-8", errors="replace") if defaults.exists() else ""
    types_text = types.read_text(encoding="utf-8", errors="replace") if types.exists() else ""

    for token in [
        "type Reconciler struct",
        "client.Client",
        "Scheme *runtime.Scheme",
        "func (r *Reconciler) Reconcile",
        "r.Get",
        "r.Delete",
        "errors.IsNotFound",
        "time.Parse",
        "time.RFC3339",
        "SessionExpirationTimeout",
        "LastActivityAnnotationKey",
        "RequeueAfter",
        "SetupWithManager",
        "ctrl.NewControllerManagedBy",
        "For(",
        "Complete(r)",
    ]:
        if token not in agentd_text:
            errors.append(f"AR-018 agentd implementation missing required behavior token: {token}")

    if "controller-runtime/pkg/client/fake" in agentd_text or "NewClientBuilder" in agentd_text:
        errors.append("AR-018 production code must not use controller-runtime fake client")

    has_external_sandbox = "sigs.k8s.io/agent-sandbox/api/v1alpha1" in agentd_text + main_text + test_text
    has_local_sandbox = "type Sandbox struct" in types_text and "DeepCopyObject" in types_text and "AddToScheme" in types_text
    if not (has_external_sandbox or has_local_sandbox):
        errors.append("AR-018 must use an external sandbox API or define a local pkg/agentd Sandbox runtime.Object")

    if "LastActivityAnnotationKey" not in defaults_text + agentd_text + test_text:
        errors.append("AR-018 must define or use LastActivityAnnotationKey for idle activity annotations")

    for token in [
        "ctrl.NewManager",
        "AddToScheme",
        "metricsserver.Options",
        "BindAddress",
        "SetupSignalHandler",
        "agentd.Reconciler",
        "Complete(",
    ]:
        if token not in main_text:
            errors.append(f"AR-018 cmd/agentd manager wiring missing required token: {token}")

    required_test_terms = [
        "fake.NewClientBuilder",
        "WithObjects",
        "Reconcile",
        "LastActivityAnnotationKey",
        "time.Now().Add",
        "time.RFC3339",
        "k8serrors.IsNotFound",
        "AddToScheme",
    ]
    missing_terms = [term for term in required_test_terms if term not in test_text]
    if not any(term in test_text for term in ["invalid-timestamp", "InvalidTimestamp", "invalid timestamp"]):
        missing_terms.append("invalid timestamp")
    if not any(term in test_text for term in ["expired", "Expired", "-20 * time.Minute", "-30 * time.Minute"]):
        missing_terms.append("expired sandbox")
    if not any(term in test_text for term in ["active", "Active", "-5 * time.Minute"]):
        missing_terms.append("active sandbox")
    if not any(term in test_text for term in ["NotFound", "nonexistent", "IsNotFound"]):
        missing_terms.append("NotFound")
    if not any(term in test_text for term in ["empty", "missing", "without last"]):
        missing_terms.append("missing/empty annotation")
    if missing_terms:
        errors.append(
            "AR-018 agentd tests do not cover required behaviors: "
            + ", ".join(missing_terms)
        )

    return errors


WORKLOADMANAGER_FINAL_PRODUCTION_TOKENS: dict[str, list[str]] = {
    "auth.go": [
        "func (s *Server) authMiddleware(c *gin.Context)",
        "func (s *Server) validateServiceAccountToken(ctx context.Context, token string) (bool, string, error)",
        "func extractUserInfo(c *gin.Context) (userToken, userNamespace, serviceAccount, serviceAccountName string)",
        "authv1.TokenReview",
        "system:serviceaccount:",
        "s.tokenCache.Get(token)",
        "s.tokenCache.Set(token, result.Status.Authenticated, username)",
    ],
    "client_cache.go": [
        "type ClientCache struct",
        "func parseJWTExpiry(token string) time.Time",
        "func NewClientCache(maxSize int) *ClientCache",
        "func (c *ClientCache) Get(key string) *UserK8sClient",
        "func (c *ClientCache) Set(key, token string, client *UserK8sClient)",
        "type TokenCache struct",
        "func NewTokenCache(maxSize int, ttl time.Duration) *TokenCache",
        "func (c *TokenCache) Get(token string) (found bool, authenticated bool, username string)",
        "func (c *TokenCache) Set(token string, authenticated bool, username string)",
    ],
    "codeinterpreter_controller.go": [
        "type CodeInterpreterReconciler struct",
        "func (r *CodeInterpreterReconciler) Reconcile(ctx context.Context, req ctrl.Request) (ctrl.Result, error)",
        "func (r *CodeInterpreterReconciler) ensureSandboxTemplate(ctx context.Context, ci *runtimev1alpha1.CodeInterpreter) (ctrl.Result, error)",
        "func (r *CodeInterpreterReconciler) ensureSandboxWarmPool(ctx context.Context, ci *runtimev1alpha1.CodeInterpreter) error",
        "func (r *CodeInterpreterReconciler) deleteSandboxWarmPool(ctx context.Context, ci *runtimev1alpha1.CodeInterpreter) error",
        "func (r *CodeInterpreterReconciler) convertToPodTemplate(template *runtimev1alpha1.CodeInterpreterSandboxTemplate, ci *runtimev1alpha1.CodeInterpreter) sandboxv1alpha1.PodTemplate",
        "PICOD_AUTH_PUBLIC_KEY",
        "RuntimeClassName",
        "SetupWithManager",
    ],
    "garbage_collection.go": [
        "github.com/volcano-sh/agentcube/pkg/common/types",
        "type garbageCollector struct",
        "func newGarbageCollector(k8sClient *K8sClient, storeClient store.Store, interval time.Duration) *garbageCollector",
        "func (gc *garbageCollector) run(stopCh <-chan struct{})",
        "func (gc *garbageCollector) once()",
        "DefaultSandboxIdleTimeout",
        "DeleteSandboxBySessionID",
        "deleteSandboxClaim",
        "deleteSandbox",
    ],
    "handlers.go": [
        "github.com/volcano-sh/agentcube/pkg/common/types",
        "func (s *Server) handleAgentRuntimeCreate(c *gin.Context)",
        "func (s *Server) handleCodeInterpreterCreate(c *gin.Context)",
        "func (s *Server) extractUserK8sClient(c *gin.Context) (dynamic.Interface, error)",
        "func (s *Server) handleSandboxCreate(c *gin.Context, kind string)",
        "buildSandboxByAgentRuntime",
        "buildSandboxByCodeInterpreter",
        "s.sandboxController.WatchSandboxOnce",
        "func (s *Server) createSandbox(ctx context.Context, dynamicClient dynamic.Interface",
        "buildSandboxPlaceHolder",
        "createSandboxClaim",
        "createSandbox(ctx, dynamicClient, sandbox)",
        "deleteSandboxClaim",
        "deleteSandbox",
        "buildSandboxInfo",
        "func (s *Server) handleDeleteSandbox(c *gin.Context)",
        "GetSandboxBySessionID",
        "DeleteSandboxBySessionID",
    ],
    "informers.go": [
        "type Informers struct",
        "func NewInformers(k8sClient *K8sClient) *Informers",
        "func (ifm *Informers) RunAndWaitForCacheSync(ctx context.Context) error",
        "AgentRuntimeGVR",
        "CodeInterpreterGVR",
    ],
    "k8s_client.go": [
        "DefaultSandboxTTL",
        "DefaultSandboxIdleTimeout",
        "SessionIdLabelKey",
        "LastActivityAnnotationKey",
        "type K8sClient struct",
        "type sandboxEntry struct",
        "func NewK8sClient() (*K8sClient, error)",
        "func (c *K8sClient) NewUserK8sClient(userToken, namespace string) (*UserK8sClient, error)",
        "func (c *K8sClient) GetOrCreateUserK8sClient(userToken, namespace, serviceAccountName string) (*UserK8sClient, error)",
        "func createSandbox(ctx context.Context, client dynamic.Interface, sandbox *sandboxv1alpha1.Sandbox) (*SandboxInfo, error)",
        "func createSandboxClaim(ctx context.Context, client dynamic.Interface, sandboxClaim *extensionsv1alpha1.SandboxClaim) error",
        "func deleteSandbox(ctx context.Context, client dynamic.Interface, namespace, sandboxName string) error",
        "func deleteSandboxClaim(ctx context.Context, client dynamic.Interface, namespace, sandboxClaimName string) error",
        "func (c *K8sClient) GetSandboxPodIP(_ context.Context, namespace, sandboxName, podName string) (string, error)",
        "func validateAndGetPodIP(pod *corev1.Pod) (string, error)",
    ],
    "sandbox_controller.go": [
        "type SandboxReconciler struct",
        "type SandboxStatusUpdate struct",
        "func (r *SandboxReconciler) Reconcile(ctx context.Context, req ctrl.Request) (ctrl.Result, error)",
        "func (r *SandboxReconciler) WatchSandboxOnce(_ context.Context, namespace, name string) <-chan SandboxStatusUpdate",
        "func (r *SandboxReconciler) UnWatchSandbox(namespace, name string)",
    ],
    "sandbox_helper.go": [
        "github.com/volcano-sh/agentcube/pkg/common/types",
        "func buildSandboxPlaceHolder(sandboxCR *sandboxv1alpha1.Sandbox, entry *sandboxEntry) *types.SandboxInfo",
        "func buildSandboxInfo(sandbox *sandboxv1alpha1.Sandbox, podIP string, entry *sandboxEntry) *types.SandboxInfo",
        "func getSandboxStatus(sandbox *sandboxv1alpha1.Sandbox) string",
        "sandboxv1alpha1.SandboxConditionReady",
    ],
    "server.go": [
        "type Server struct",
        "storeClient       store.Store",
        "sandboxController *SandboxReconciler",
        "func NewServer(config *Config, sandboxController *SandboxReconciler) (*Server, error)",
        "InitPublicKeyCache(k8sClient.clientset)",
        "NewTokenCache(1000, 5*time.Minute)",
        "func (s *Server) setupRoutes()",
        "v1Group.POST(\"/agent-runtime\", s.handleAgentRuntimeCreate)",
        "v1Group.POST(\"/code-interpreter\", s.handleCodeInterpreterCreate)",
        "v1Group.DELETE(\"/agent-runtime/sessions/:sessionId\", s.handleDeleteSandbox)",
        "func (s *Server) Start(ctx context.Context) error",
        "newGarbageCollector",
        "h2c.NewHandler",
    ],
    "utils.go": [
        "type ErrorResponse struct",
        "func respondJSON(c *gin.Context, statusCode int, data interface{})",
        "func respondError(c *gin.Context, statusCode int, message string)",
        "func RandString(n int) string",
    ],
    "workload_builder.go": [
        "github.com/volcano-sh/agentcube/pkg/common/types",
        "func GetCachedPublicKey() string",
        "func IsPublicKeyCached() bool",
        "func InitPublicKeyCache(clientset kubernetes.Interface)",
        "func buildSandboxObject(params *buildSandboxParams) *sandboxv1alpha1.Sandbox",
        "func buildSandboxClaimObject(params *buildSandboxClaimParams) *extensionsv1alpha1.SandboxClaim",
        "func buildSandboxByAgentRuntime(namespace string, name string, ifm *Informers) (*sandboxv1alpha1.Sandbox, *sandboxEntry, error)",
        "func buildSandboxByCodeInterpreter(namespace string, codeInterpreterName string, informer *Informers) (*sandboxv1alpha1.Sandbox, *extensionsv1alpha1.SandboxClaim, *sandboxEntry, error)",
        "PICOD_AUTH_PUBLIC_KEY",
        "RuntimeClassName",
        "RandString(8)",
    ],
}


def _validate_workloadmanager_tokens(
    workspace: Path,
    file_tokens: dict[str, list[str]],
    label: str,
    *,
    exact_production_files: bool = False,
    min_total_loc: int = 0,
    forbid_tests: bool = False,
) -> list[str]:
    errors: list[str] = []
    root = workspace / "pkg" / "workloadmanager"
    if not root.exists():
        return [f"{label} must create pkg/workloadmanager"]

    expected = set(file_tokens)
    production_files = {
        p.name for p in root.glob("*.go")
        if p.is_file() and not p.name.endswith("_test.go")
    }
    non_original_production = sorted(production_files - set(WORKLOADMANAGER_FINAL_PRODUCTION_TOKENS))
    if non_original_production:
        errors.append(
            f"{label} must not create non-original workloadmanager production files: "
            + ", ".join(non_original_production[:12])
        )
    early_tests = sorted(p.name for p in root.glob("*_test.go") if p.is_file())
    if forbid_tests and early_tests:
        errors.append(
            f"{label} must not create workloadmanager Go tests before AR-038: "
            + ", ".join(early_tests[:12])
        )
    if exact_production_files:
        missing = sorted(expected - production_files)
        unexpected = sorted(production_files - expected)
        for rel in missing:
            errors.append(f"{label} must create pkg/workloadmanager/{rel}")
        if unexpected:
            errors.append(
                f"{label} must not create non-original workloadmanager production files: "
                + ", ".join(unexpected[:12])
            )

    total_loc = 0
    for rel, tokens in file_tokens.items():
        path = root / rel
        if not path.exists():
            errors.append(f"{label} must create pkg/workloadmanager/{rel}")
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        total_loc += len(text.splitlines())
        lower = text.lower()
        for marker in ["notimplementederror", "stub implementation", "stubbed implementation"]:
            if marker in lower:
                errors.append(f"{label} pkg/workloadmanager/{rel} must not contain placeholder marker: {marker}")
        for token in tokens:
            if token not in text:
                errors.append(f"{label} pkg/workloadmanager/{rel} missing production token: {token}")

    if min_total_loc and total_loc < min_total_loc:
        errors.append(f"{label} workloadmanager production LOC is too small: {total_loc} < {min_total_loc}")

    return errors


def _validate_common_types_package(workspace: Path, label: str, *, forbid_tests: bool = False) -> list[str]:
    errors: list[str] = []
    misplaced = workspace / "pkg" / "common" / "types.go"
    if misplaced.exists():
        errors.append(f"{label} must not create pkg/common/types.go; use pkg/common/types/{{types.go,sandbox.go}}")
    early_common_tests = sorted((workspace / "pkg" / "common" / "types").glob("*_test.go"))
    if forbid_tests and early_common_tests:
        errors.append(
            f"{label} must not create pkg/common/types tests in WorkloadManager production ARs: "
            + ", ".join(str(p.relative_to(workspace)) for p in early_common_tests[:8])
        )

    required = {
        "pkg/common/types/types.go": [
            "package types",
            "AgentRuntimeKind    = \"AgentRuntime\"",
            "CodeInterpreterKind = \"CodeInterpreter\"",
            "SandboxKind       = \"Sandbox\"",
            "SandboxClaimsKind = \"SandboxClaim\"",
        ],
        "pkg/common/types/sandbox.go": [
            "package types",
            "type SandboxInfo struct",
            "type SandboxEntryPoint struct",
            "type CreateSandboxRequest struct",
            "type CreateSandboxResponse struct",
            "func (car *CreateSandboxRequest) Validate() error",
            "namespace is required",
            "name is required",
            "invalid kind",
        ],
    }
    for rel, tokens in required.items():
        path = workspace / rel
        if not path.exists():
            errors.append(f"{label} must create {rel}")
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for forbidden in [
            "github.com/volcano-sh/agentcube/pkg/store",
            "type SandboxInfo =",
            "type SandboxEntryPoint =",
        ]:
            if forbidden in text:
                errors.append(f"{label} {rel} must not alias store types or import store: {forbidden}")
        for token in tokens:
            if token not in text:
                errors.append(f"{label} {rel} missing token: {token}")

    sandbox_path = workspace / "pkg" / "common" / "types" / "sandbox.go"
    types_path = workspace / "pkg" / "common" / "types" / "types.go"
    sandbox_text = sandbox_path.read_text(encoding="utf-8", errors="replace") if sandbox_path.exists() else ""
    types_text = types_path.read_text(encoding="utf-8", errors="replace") if types_path.exists() else ""
    if re.search(r"type\s+EntryPoint\s+struct", sandbox_text + "\n" + types_text):
        errors.append(f"{label} shared types must not define non-original type EntryPoint; use SandboxEntryPoint")
    if not re.search(r"type\s+SandboxInfo\s+struct\s*\{[^}]*EntryPoints\s+\[\]SandboxEntryPoint", sandbox_text, re.S):
        errors.append(f"{label} SandboxInfo.EntryPoints must use []SandboxEntryPoint")
    if not re.search(r"type\s+CreateSandboxResponse\s+struct\s*\{[^}]*EntryPoints\s+\[\]SandboxEntryPoint", sandbox_text, re.S):
        errors.append(f"{label} CreateSandboxResponse.EntryPoints must use []SandboxEntryPoint")
    entrypoint_tokens = [
        ("Path", r"Path\s+string\s+`json:\"path\"`"),
        ("Protocol", r"Protocol\s+string\s+`json:\"protocol\"`"),
        ("Endpoint", r"Endpoint\s+string\s+`json:\"endpoint\"`"),
    ]
    for field, pattern in entrypoint_tokens:
        if not re.search(pattern, sandbox_text):
            errors.append(f"{label} SandboxEntryPoint missing original field {field}")

    return errors


def _validate_workloadmanager_go_mod_baseline(workspace: Path, label: str) -> list[str]:
    go_mod = workspace / "go.mod"
    if not go_mod.exists():
        return [f"{label} must create go.mod with the original AgentCube Go dependency baseline"]
    text = go_mod.read_text(encoding="utf-8", errors="replace")
    required = [
        "go 1.24.4",
        "toolchain go1.24.9",
        "k8s.io/api v0.34.1",
        "k8s.io/apimachinery v0.34.1",
        "k8s.io/client-go v0.34.1",
        "golang.org/x/net v0.47.0",
        "golang.org/x/sys v0.39.0",
        "sigs.k8s.io/agent-sandbox v0.1.1",
        "sigs.k8s.io/controller-runtime v0.22.2",
    ]
    return [f"{label} go.mod missing original dependency baseline token: {token}" for token in required if token not in text]


def _validate_workloadmanager_store_contract(workspace: Path, label: str) -> list[str]:
    store_root = workspace / "pkg" / "store"
    if not store_root.exists():
        return []
    errors: list[str] = []
    concrete = sorted(
        p.name for p in store_root.glob("*.go")
        if p.is_file() and p.name != "store.go" and not p.name.endswith("_test.go")
    )
    if concrete:
        errors.append(
            f"{label} must not create concrete store backends before store ARs: "
            + ", ".join(concrete[:12])
        )
    store_go = store_root / "store.go"
    if store_go.exists():
        text = store_go.read_text(encoding="utf-8", errors="replace")
        required = [
            "type Store interface",
            "GetSandboxBySessionID(ctx context.Context, sessionID string) (*types.SandboxInfo, error)",
            "StoreSandbox(ctx context.Context",
            "UpdateSandbox(ctx context.Context",
            "DeleteSandboxBySessionID(ctx context.Context, sessionID string) error",
            "ListExpiredSandboxes(ctx context.Context, before time.Time, limit int64)",
            "ListInactiveSandboxes(ctx context.Context, before time.Time, limit int64)",
            "UpdateSessionLastActivity(ctx context.Context, sessionID string, at time.Time) error",
            "Close() error",
        ]
        for token in required:
            if token not in text:
                errors.append(f"{label} pkg/store/store.go missing original store contract token: {token}")
    return errors


def _validate_workloadmanager_shared_contracts(workspace: Path, label: str, *, forbid_tests: bool = False) -> list[str]:
    return (
        _validate_common_types_package(workspace, label, forbid_tests=forbid_tests)
        + _validate_workloadmanager_go_mod_baseline(workspace, label)
        + _validate_workloadmanager_store_contract(workspace, label)
    )


def _validate_ar004_workloadmanager_framework(workspace: Path) -> list[str]:
    return _validate_workloadmanager_tokens(
        workspace,
        {
            "server.go": [
                "type Server struct",
                "type Config struct",
                "func NewServer(config *Config, sandboxController *SandboxReconciler) (*Server, error)",
                "func (s *Server) setupRoutes()",
                "v1Group.POST(\"/agent-runtime\", s.handleAgentRuntimeCreate)",
                "v1Group.POST(\"/code-interpreter\", s.handleCodeInterpreterCreate)",
                "func (s *Server) Start(ctx context.Context) error",
                "h2c.NewHandler",
            ],
            "utils.go": [
                "type ErrorResponse struct",
                "func respondJSON(c *gin.Context, statusCode int, data interface{})",
                "func respondError(c *gin.Context, statusCode int, message string)",
            ],
            "client_cache.go": [
                "type TokenCache struct",
                "func NewTokenCache(maxSize int, ttl time.Duration) *TokenCache",
            ],
            "k8s_client.go": [
                "type K8sClient struct",
                "func NewK8sClient() (*K8sClient, error)",
            ],
        },
        "AR-004",
        exact_production_files=True,
        forbid_tests=True,
    ) + _validate_workloadmanager_shared_contracts(workspace, "AR-004", forbid_tests=True)


def _validate_ar005_workloadmanager_creation(workspace: Path) -> list[str]:
    return _validate_workloadmanager_tokens(
        workspace,
        {
            "handlers.go": [
                "github.com/volcano-sh/agentcube/pkg/common/types",
                "func (s *Server) handleSandboxCreate(c *gin.Context, kind string)",
                "func (s *Server) extractUserK8sClient(c *gin.Context) (dynamic.Interface, error)",
                "buildSandboxByAgentRuntime",
                "buildSandboxByCodeInterpreter",
                "s.sandboxController.WatchSandboxOnce",
                "func (s *Server) createSandbox(ctx context.Context, dynamicClient dynamic.Interface",
            ],
            "workload_builder.go": [
                "github.com/volcano-sh/agentcube/pkg/common/types",
                "func buildSandboxObject(params *buildSandboxParams) *sandboxv1alpha1.Sandbox",
                "func buildSandboxClaimObject(params *buildSandboxClaimParams) *extensionsv1alpha1.SandboxClaim",
                "func buildSandboxByAgentRuntime(namespace string, name string, ifm *Informers) (*sandboxv1alpha1.Sandbox, *sandboxEntry, error)",
                "func buildSandboxByCodeInterpreter(namespace string, codeInterpreterName string, informer *Informers) (*sandboxv1alpha1.Sandbox, *extensionsv1alpha1.SandboxClaim, *sandboxEntry, error)",
                "PICOD_AUTH_PUBLIC_KEY",
                "RuntimeClassName",
            ],
            "sandbox_helper.go": [
                "github.com/volcano-sh/agentcube/pkg/common/types",
                "func buildSandboxPlaceHolder(sandboxCR *sandboxv1alpha1.Sandbox, entry *sandboxEntry) *types.SandboxInfo",
                "func buildSandboxInfo(sandbox *sandboxv1alpha1.Sandbox, podIP string, entry *sandboxEntry) *types.SandboxInfo",
            ],
            "k8s_client.go": [
                "func (c *K8sClient) GetOrCreateUserK8sClient(userToken, namespace, serviceAccountName string) (*UserK8sClient, error)",
                "func createSandbox(ctx context.Context, client dynamic.Interface, sandbox *sandboxv1alpha1.Sandbox) (*SandboxInfo, error)",
                "func createSandboxClaim(ctx context.Context, client dynamic.Interface, sandboxClaim *extensionsv1alpha1.SandboxClaim) error",
            ],
        },
        "AR-005",
        forbid_tests=True,
    ) + _validate_workloadmanager_shared_contracts(workspace, "AR-005", forbid_tests=True)


def _validate_ar006_workloadmanager_lifecycle(workspace: Path) -> list[str]:
    return _validate_workloadmanager_tokens(
        workspace,
        {
            "handlers.go": [
                "github.com/volcano-sh/agentcube/pkg/common/types",
                "func (s *Server) handleDeleteSandbox(c *gin.Context)",
                "GetSandboxBySessionID",
                "DeleteSandboxBySessionID",
                "deleteSandboxClaim",
                "deleteSandbox",
            ],
            "k8s_client.go": [
                "func deleteSandbox(ctx context.Context, client dynamic.Interface, namespace, sandboxName string) error",
                "func deleteSandboxClaim(ctx context.Context, client dynamic.Interface, namespace, sandboxClaimName string) error",
            ],
        },
        "AR-006",
        forbid_tests=True,
    ) + _validate_workloadmanager_shared_contracts(workspace, "AR-006", forbid_tests=True)


def _validate_ar007_workloadmanager_controllers(workspace: Path) -> list[str]:
    return _validate_workloadmanager_tokens(
        workspace,
        {
            "sandbox_controller.go": WORKLOADMANAGER_FINAL_PRODUCTION_TOKENS["sandbox_controller.go"],
            "codeinterpreter_controller.go": [
                "type CodeInterpreterReconciler struct",
                "func (r *CodeInterpreterReconciler) Reconcile(ctx context.Context, req ctrl.Request) (ctrl.Result, error)",
                "func (r *CodeInterpreterReconciler) ensureSandboxTemplate(ctx context.Context, ci *runtimev1alpha1.CodeInterpreter) (ctrl.Result, error)",
                "func (r *CodeInterpreterReconciler) ensureSandboxWarmPool(ctx context.Context, ci *runtimev1alpha1.CodeInterpreter) error",
                "func (r *CodeInterpreterReconciler) convertToPodTemplate(template *runtimev1alpha1.CodeInterpreterSandboxTemplate, ci *runtimev1alpha1.CodeInterpreter) sandboxv1alpha1.PodTemplate",
                "PICOD_AUTH_PUBLIC_KEY",
                "RuntimeClassName",
            ],
            "informers.go": WORKLOADMANAGER_FINAL_PRODUCTION_TOKENS["informers.go"],
        },
        "AR-007",
        forbid_tests=True,
    ) + _validate_workloadmanager_shared_contracts(workspace, "AR-007", forbid_tests=True)


def _validate_workloadmanager_production_complete(workspace: Path, label: str, *, forbid_tests: bool = False) -> list[str]:
    return _validate_workloadmanager_tokens(
        workspace,
        WORKLOADMANAGER_FINAL_PRODUCTION_TOKENS,
        label,
        exact_production_files=True,
        min_total_loc=2300,
        forbid_tests=forbid_tests,
    ) + _validate_workloadmanager_shared_contracts(workspace, label, forbid_tests=forbid_tests)


def _validate_ar008_workloadmanager_gc_complete(workspace: Path) -> list[str]:
    return _validate_workloadmanager_production_complete(workspace, "AR-008", forbid_tests=True)


def _validate_router_tokens(
    workspace: Path,
    file_tokens: dict[str, list[str]],
    label: str,
    *,
    min_total_loc: int = 0,
    forbid_tests: bool = False,
) -> list[str]:
    errors: list[str] = []
    root = workspace / "pkg" / "router"
    if not root.exists():
        return [f"{label} must create pkg/router"]

    if forbid_tests:
        early_tests = sorted(p.name for p in root.glob("*_test.go") if p.is_file())
        if early_tests:
            errors.append(
                f"{label} must not create router Go tests before the router testing AR: "
                + ", ".join(early_tests[:12])
            )

    total_loc = 0
    for rel, tokens in file_tokens.items():
        path = root / rel
        if not path.exists():
            errors.append(f"{label} must create pkg/router/{rel}")
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        total_loc += len(text.splitlines())
        lower = text.lower()
        for marker in ["notimplementederror", "stub implementation", "stubbed implementation"]:
            if marker in lower:
                errors.append(f"{label} pkg/router/{rel} must not contain placeholder marker: {marker}")
        for token in tokens:
            if token not in text:
                errors.append(f"{label} pkg/router/{rel} missing production token: {token}")

    if min_total_loc and total_loc < min_total_loc:
        errors.append(f"{label} router production LOC is too small: {total_loc} < {min_total_loc}")

    return errors


def _validate_ar009_router_core(workspace: Path) -> list[str]:
    errors = _validate_router_tokens(
        workspace,
        {
            "config.go": [
                "LastActivityAnnotationKey",
                "type Config struct",
                "MaxConcurrentRequests",
            ],
            "server.go": [
                "type Server struct",
                "github.com/volcano-sh/agentcube/pkg/common/types",
                "GetSandboxBySession(ctx context.Context, sessionID string, namespace string, name string, kind string) (*types.SandboxInfo, error)",
                "type tokenSigner interface",
                "func NewServer(config *Config) (*Server, error)",
                "func (s *Server) concurrencyLimitMiddleware() gin.HandlerFunc",
                "func (s *Server) setupRoutes()",
                "\"/health/live\"",
                "\"/health/ready\"",
                "\"/namespaces/:namespace/agent-runtimes/:name/invocations/*path\"",
                "\"/namespaces/:namespace/code-interpreters/:name/invocations/*path\"",
                "func (s *Server) Start(ctx context.Context) error",
                "h2c.NewHandler",
            ],
            "handlers.go": [
                "github.com/volcano-sh/agentcube/pkg/common/types",
                "func (s *Server) handleHealthLive(c *gin.Context)",
                "func (s *Server) handleHealthReady(c *gin.Context)",
                "func (s *Server) handleInvoke(c *gin.Context, namespace, name, path, kind string)",
                "\"x-agentcube-session-id\"",
                "GetSandboxBySession",
                "s.storeClient.UpdateSessionLastActivity",
                "func determineUpstreamURL(sandbox *types.SandboxInfo, path string) (*url.URL, error)",
                "strings.HasPrefix(path, ep.Path)",
                "buildURL(ep.Protocol, ep.Endpoint)",
                "func buildURL(protocol, endpoint string) *url.URL",
                "func (s *Server) handleAgentInvoke(c *gin.Context)",
                "func (s *Server) handleCodeInterpreterInvoke(c *gin.Context)",
                "func (s *Server) forwardToSandbox(c *gin.Context, sandbox *types.SandboxInfo, path string)",
                "httputil.NewSingleHostReverseProxy",
            ],
        },
        "AR-009",
        min_total_loc=220,
        forbid_tests=True,
    )
    root = workspace / "pkg" / "router"
    if root.exists():
        allowed_production = {"config.go", "server.go", "handlers.go"}
        production_files = {
            p.name for p in root.glob("*.go")
            if p.is_file() and not p.name.endswith("_test.go")
        }
        unexpected = sorted(production_files - allowed_production)
        if unexpected:
            errors.append(
                "AR-009 must not create router production files reserved for later ARs: "
                + ", ".join(unexpected[:12])
            )
        combined = "\n".join(
            p.read_text(encoding="utf-8", errors="replace")
            for p in root.glob("*.go")
            if p.is_file()
        )
        for forbidden in [
            "type SandboxInfo struct",
            "type SandboxEntryPoint struct",
            "func convertToTypesEntryPoints",
            "type JWTManager interface",
            "*JWTManager",
            "UpdateSessionLastActivity(ctx context.Context, storeClient store.Store",
        ]:
            if forbidden in combined:
                errors.append(f"AR-009 router core must not define local/future shim: {forbidden}")
    errors.extend(_validate_workloadmanager_shared_contracts(workspace, "AR-009", forbid_tests=True))
    return errors


def _validate_ar010_router_session_manager(workspace: Path) -> list[str]:
    errors = _validate_router_tokens(
        workspace,
        {
            "config.go": [
                "LastActivityAnnotationKey",
                "type Config struct",
                "MaxConcurrentRequests",
            ],
            "server.go": [
                "type Server struct",
                "sessionManager SessionManager",
                "storeClient    store.Store",
                "httpTransport  *http.Transport",
                "type tokenSigner interface",
                "tokenSigner    tokenSigner",
                "func NewServer(config *Config) (*Server, error)",
                "func (s *Server) setupRoutes()",
                "\"/health/live\"",
                "\"/health/ready\"",
                "\"/namespaces/:namespace/agent-runtimes/:name/invocations/*path\"",
                "\"/namespaces/:namespace/code-interpreters/:name/invocations/*path\"",
                "func (s *Server) Start(ctx context.Context) error",
                "h2c.NewHandler",
            ],
            "handlers.go": [
                "github.com/volcano-sh/agentcube/pkg/common/types",
                "func (s *Server) handleInvoke(c *gin.Context, namespace, name, path, kind string)",
                "\"x-agentcube-session-id\"",
                "GetSandboxBySession",
                "s.storeClient.UpdateSessionLastActivity",
                "func determineUpstreamURL(sandbox *types.SandboxInfo, path string) (*url.URL, error)",
                "strings.HasPrefix(path, ep.Path)",
                "buildURL(ep.Protocol, ep.Endpoint)",
                "func (s *Server) forwardToSandbox(c *gin.Context, sandbox *types.SandboxInfo, path string)",
                "httputil.NewSingleHostReverseProxy",
            ],
            "session_manager.go": [
                "github.com/volcano-sh/agentcube/pkg/api",
                "github.com/volcano-sh/agentcube/pkg/common/types",
                "github.com/volcano-sh/agentcube/pkg/store",
                "var serviceAccountTokenPath = \"/var/run/secrets/kubernetes.io/serviceaccount/token\"",
                "type SessionManager interface",
                "GetSandboxBySession(ctx context.Context, sessionID string, namespace string, name string, kind string) (*types.SandboxInfo, error)",
                "type manager struct",
                "storeClient     store.Store",
                "workloadMgrAddr string",
                "httpClient      *http.Client",
                "func NewSessionManager(storeClient store.Store) (SessionManager, error)",
                "os.Getenv(\"WORKLOAD_MANAGER_URL\")",
                "http2.ConfigureTransports",
                "ReadIdleTimeout = 30 * time.Second",
                "PingTimeout = 15 * time.Second",
                "func (m *manager) GetSandboxBySession(ctx context.Context, sessionID string, namespace string, name string, kind string) (*types.SandboxInfo, error)",
                "if sessionID == \"\"",
                "return m.createSandbox(ctx, namespace, name, kind)",
                "m.storeClient.GetSandboxBySessionID(ctx, sessionID)",
                "errors.Is(err, store.ErrNotFound)",
                "api.NewSessionNotFoundError(sessionID)",
                "func (m *manager) createSandbox(ctx context.Context, namespace string, name string, kind string) (*types.SandboxInfo, error)",
                "types.AgentRuntimeKind",
                "\"/v1/agent-runtime\"",
                "types.CodeInterpreterKind",
                "\"/v1/code-interpreter\"",
                "types.CreateSandboxRequest",
                "json.Marshal",
                "http.NewRequestWithContext",
                "req.Header.Set(\"Content-Type\", \"application/json\")",
                "loadWorkloadManagerAuthToken()",
                "req.Header.Set(\"Authorization\", \"Bearer \"+token)",
                "m.httpClient.Do(req)",
                "io.ReadAll",
                "resp.StatusCode != http.StatusOK",
                "api.NewSandboxTemplateNotFoundError(namespace, name, kind)",
                "var res types.CreateSandboxResponse",
                "json.Unmarshal",
                "res.SessionID == \"\"",
                "&types.SandboxInfo{",
                "EntryPoints: res.EntryPoints",
                "func loadWorkloadManagerAuthToken() string",
                "os.ReadFile(serviceAccountTokenPath)",
                "strings.TrimSpace",
            ],
        },
        "AR-010",
        min_total_loc=420,
        forbid_tests=True,
    )
    root = workspace / "pkg" / "router"
    if root.exists():
        allowed_production = {"config.go", "server.go", "handlers.go", "session_manager.go"}
        production_files = {
            p.name for p in root.glob("*.go")
            if p.is_file() and not p.name.endswith("_test.go")
        }
        unexpected = sorted(production_files - allowed_production)
        if unexpected:
            errors.append(
                "AR-010 must not create router production files reserved for later ARs: "
                + ", ".join(unexpected[:12])
            )
        combined = "\n".join(
            p.read_text(encoding="utf-8", errors="replace")
            for p in root.glob("*.go")
            if p.is_file()
        )
        server_text = (root / "server.go").read_text(encoding="utf-8", errors="replace") if (root / "server.go").is_file() else ""
        if "NewSessionManager(" not in server_text:
            errors.append("AR-010 server.go must wire NewServer to NewSessionManager")
        if not any(token in server_text for token in [
            "sessionManager: sessionManager",
            "SetSessionManager(sessionManager)",
            "sessionManager = sessionManager",
        ]):
            errors.append("AR-010 server.go must store the NewSessionManager result on Server.sessionManager")
        for forbidden in [
            "type SandboxInfo struct",
            "type SandboxEntryPoint struct",
            "func convertToTypesEntryPoints",
            "type JWTManager",
            "*JWTManager",
            "NewJWTManager",
            "TryStoreOrLoadJWTKeySecret",
            "GenerateJWT",
            "github.com/golang-jwt/jwt",
            "rsa.GenerateKey",
            "PrivateKeyDataKey",
            "PublicKeyDataKey",
            "IdentitySecretName",
            "UpdateSessionLastActivity(ctx context.Context, storeClient store.Store",
        ]:
            if forbidden in combined:
                errors.append(f"AR-010 router session manager must not define local/future shim: {forbidden}")
    api_root = workspace / "pkg" / "api"
    if api_root.exists():
        api_files = {
            p.name for p in api_root.glob("*.go")
            if p.is_file() and not p.name.endswith("_test.go")
        }
        unexpected_api = sorted(api_files - {"errors.go"})
        if unexpected_api:
            errors.append(
                "AR-010 may only update pkg/api/errors.go outside pkg/router, found: "
                + ", ".join(unexpected_api[:12])
            )
    api_errors_path = workspace / "pkg" / "api" / "errors.go"
    if not api_errors_path.exists():
        errors.append("AR-010 must keep pkg/api/errors.go for session manager API errors")
    else:
        api_errors_text = api_errors_path.read_text(encoding="utf-8", errors="replace")
        for token in [
            "apierrors \"k8s.io/apimachinery/pkg/api/errors\"",
            "\"k8s.io/apimachinery/pkg/runtime/schema\"",
            "github.com/volcano-sh/agentcube/pkg/common/types",
            "resourceGroup               = \"agentcube.volcano.sh\"",
            "sessionResourceName         = \"sessions\"",
            "agentRuntimeResourceName    = \"agentruntimes\"",
            "codeInterpreterResourceName = \"codeinterpreters\"",
            "sessionResource         = schema.GroupResource{Group: resourceGroup, Resource: sessionResourceName}",
            "func NewSessionNotFoundError(sessionID string) error",
            "return apierrors.NewNotFound(sessionResource, sessionID)",
            "func workloadResource(kind string) schema.GroupResource",
            "case types.CodeInterpreterKind:",
            "func NewSandboxTemplateNotFoundError(namespace, name, kind string) error",
            "return apierrors.NewNotFound(gr, fmt.Sprintf(\"%s/%s\", namespace, name))",
            "func NewUpstreamUnavailableError(err error) error",
            "func NewInternalError(err error) error",
        ]:
            if token not in api_errors_text:
                errors.append(f"AR-010 pkg/api/errors.go missing production token: {token}")
    errors.extend(_validate_workloadmanager_shared_contracts(workspace, "AR-010", forbid_tests=True))
    return errors


def _validate_ar011_router_jwt(workspace: Path) -> list[str]:
    errors = _validate_router_tokens(
        workspace,
        {
            "config.go": [
                "LastActivityAnnotationKey",
                "type Config struct",
                "MaxConcurrentRequests",
            ],
            "server.go": [
                "type Server struct",
                "sessionManager SessionManager",
                "storeClient    store.Store",
                "httpTransport  *http.Transport",
                "jwtManager     *JWTManager",
                "func NewServer(config *Config) (*Server, error)",
                "NewSessionManager(",
                "NewJWTManager()",
                "TryStoreOrLoadJWTKeySecret(context.Background())",
                "server.jwtManager = jwtManager",
                "JWT manager initialized successfully",
                "func (s *Server) setupRoutes()",
                "func (s *Server) Start(ctx context.Context) error",
                "h2c.NewHandler",
            ],
            "handlers.go": [
                "github.com/volcano-sh/agentcube/pkg/common/types",
                "func (s *Server) forwardToSandbox(c *gin.Context, sandbox *types.SandboxInfo, path string)",
                "if sandbox.Kind == types.SandboxClaimsKind || sandbox.Kind == types.SandboxKind",
                "if s.jwtManager != nil",
                "claims := map[string]interface{}",
                "\"session_id\": sandbox.SessionID",
                "s.jwtManager.GenerateToken(claims)",
                "\"error\": \"failed to sign request\"",
                "\"code\":  \"JWT_SIGNING_FAILED\"",
                "req.Header.Set(\"Authorization\", \"Bearer \"+jwtToken)",
            ],
            "session_manager.go": [
                "type SessionManager interface",
                "func NewSessionManager(storeClient store.Store) (SessionManager, error)",
                "func (m *manager) GetSandboxBySession(ctx context.Context, sessionID string, namespace string, name string, kind string) (*types.SandboxInfo, error)",
                "api.NewSessionNotFoundError(sessionID)",
                "api.NewSandboxTemplateNotFoundError(namespace, name, kind)",
            ],
            "jwt.go": [
                "github.com/golang-jwt/jwt/v5",
                "crypto/rand",
                "IdentitySecretName = \"picod-router-identity\"",
                "var IdentityNamespace = \"default\"",
                "os.Getenv(\"AGENTCUBE_NAMESPACE\")",
                "type JWTManager struct",
                "clientset  kubernetes.Interface",
                "func NewJWTManager() (*JWTManager, error)",
                "rsa.GenerateKey(rand.Reader, rsaKeySize)",
                "func (jm *JWTManager) GenerateToken(claims map[string]interface{}) (string, error)",
                "jwt.MapClaims",
                "\"iss\": \"agentcube-router\"",
                "jwt.SigningMethodRS256",
                "func (jm *JWTManager) GetPublicKeyPEM() ([]byte, error)",
                "x509.MarshalPKIXPublicKey",
                "func (jm *JWTManager) GetPrivateKeyPEM() []byte",
                "x509.MarshalPKCS1PrivateKey",
                "func (jm *JWTManager) TryStoreOrLoadJWTKeySecret(ctx context.Context) error",
                "rest.InClusterConfig",
                "kubernetes.NewForConfig",
                "corev1.Secret",
                "apierrors.IsAlreadyExists",
                "loadPrivateKeyPEM",
                "func (jm *JWTManager) loadPrivateKeyPEM(privateKeyPEM []byte) error",
            ],
        },
        "AR-011",
        min_total_loc=620,
        forbid_tests=True,
    )
    root = workspace / "pkg" / "router"
    if root.exists():
        allowed_production = {"config.go", "server.go", "handlers.go", "session_manager.go", "jwt.go"}
        production_files = {
            p.name for p in root.glob("*.go")
            if p.is_file() and not p.name.endswith("_test.go")
        }
        unexpected = sorted(production_files - allowed_production)
        if unexpected:
            errors.append(
                "AR-011 must not create router production files outside the JWT split: "
                + ", ".join(unexpected[:12])
            )
        combined = "\n".join(
            p.read_text(encoding="utf-8", errors="replace")
            for p in root.glob("*.go")
            if p.is_file()
        )
        jwt_text = (root / "jwt.go").read_text(encoding="utf-8", errors="replace") if (root / "jwt.go").is_file() else ""
        for label, pattern in {
            "rsaKeySize": r"rsaKeySize\s*=\s*2048",
            "jwtExpiration": r"jwtExpiration\s*=\s*5\s*\*\s*time\.Minute",
            "PrivateKeyDataKey": r"PrivateKeyDataKey\s*=\s*\"private\.pem\"",
            "PublicKeyDataKey": r"PublicKeyDataKey\s*=\s*\"public\.pem\"",
        }.items():
            if not re.search(pattern, jwt_text):
                errors.append(f"AR-011 pkg/router/jwt.go missing original constant: {label}")
        for forbidden in [
            "type JWTManager interface",
            "tokenSigner    tokenSigner",
            "type tokenSigner interface",
            "rsa.GenerateKey(nil",
            "RSA PUBLIC KEY",
            "privateKey not initialized",
        ]:
            if forbidden in combined:
                errors.append(f"AR-011 router JWT must not keep shim/incorrect JWT token: {forbidden}")
    go_mod = workspace / "go.mod"
    if not go_mod.exists():
        errors.append("AR-011 must keep go.mod")
    else:
        go_mod_text = go_mod.read_text(encoding="utf-8", errors="replace")
        if "github.com/golang-jwt/jwt/v5 v5.2.2" not in go_mod_text:
            errors.append("AR-011 go.mod missing original dependency: github.com/golang-jwt/jwt/v5 v5.2.2")
    errors.extend(_validate_workloadmanager_shared_contracts(workspace, "AR-011", forbid_tests=True))
    return errors


def _validate_ar012_store_contract(workspace: Path) -> list[str]:
    errors: list[str] = []
    root = workspace / "pkg" / "store"
    if not root.exists():
        return ["AR-012 must create pkg/store"]

    early_tests = sorted(p.name for p in root.glob("*_test.go") if p.is_file())
    if early_tests:
        errors.append(
            "AR-012 must not create store tests before backend/testing ARs: "
            + ", ".join(early_tests[:12])
        )

    allowed_production = {"interface.go", "error.go", "singleton.go"}
    production_files = {
        p.name for p in root.glob("*.go")
        if p.is_file() and not p.name.endswith("_test.go")
    }
    unexpected = sorted(production_files - allowed_production)
    if unexpected:
        errors.append(
            "AR-012 store contract must not keep temporary or backend production files: "
            + ", ".join(unexpected[:12])
        )

    required = {
        "interface.go": [
            "package store",
            "github.com/volcano-sh/agentcube/pkg/common/types",
            "type Store interface",
            "Ping(ctx context.Context) error",
            "GetSandboxBySessionID(ctx context.Context, sessionID string) (*types.SandboxInfo, error)",
            "StoreSandbox(ctx context.Context, sandboxStore *types.SandboxInfo) error",
            "UpdateSandbox(ctx context.Context, sandboxStore *types.SandboxInfo) error",
            "DeleteSandboxBySessionID(ctx context.Context, sessionID string) error",
            "ListExpiredSandboxes(ctx context.Context, before time.Time, limit int64) ([]*types.SandboxInfo, error)",
            "ListInactiveSandboxes(ctx context.Context, before time.Time, limit int64) ([]*types.SandboxInfo, error)",
            "UpdateSessionLastActivity(ctx context.Context, sessionID string, at time.Time) error",
            "Close() error",
        ],
        "error.go": [
            "package store",
            "\"errors\"",
            "ErrNotFound = errors.New(\"store: not found\")",
        ],
        "singleton.go": [
            "package store",
            "\"fmt\"",
            "\"os\"",
            "\"strings\"",
            "\"sync\"",
            "k8s.io/klog/v2",
            "redisStoreType  string = \"redis\"",
            "valkeyStoreType string = \"valkey\"",
            "initStoreOnce = &sync.Once{}",
            "provider      Store",
            "func Storage() Store",
            "initStoreOnce.Do",
            "klog.Fatalf(\"init store failed: %v\", err)",
            "return provider",
            "func initStore() error",
            "os.LookupEnv(\"STORE_TYPE\")",
            "providerType = redisStoreType",
            "strings.ToLower(providerType)",
            "case redisStoreType:",
            "case valkeyStoreType:",
            "unsupported provider type",
        ],
    }
    combined = ""
    for rel, tokens in required.items():
        path = root / rel
        if not path.exists():
            errors.append(f"AR-012 must create pkg/store/{rel}")
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        combined += "\n" + text
        for token in tokens:
            if token not in text:
                errors.append(f"AR-012 pkg/store/{rel} missing production token: {token}")

    for forbidden in [
        "type storage struct",
        "func (s *storage)",
        "return &storage",
        "initRedisStore(",
        "initValkeyStore(",
        "store_redis",
        "store_valkey",
        "github.com/redis/go-redis",
        "github.com/valkey-io/valkey-go",
        "not implemented",
        "TODO",
    ]:
        if forbidden in combined:
            errors.append(f"AR-012 store contract must not keep placeholder/backend token: {forbidden}")

    errors.extend(_validate_common_types_package(workspace, "AR-012", forbid_tests=True))
    errors.extend(_validate_workloadmanager_go_mod_baseline(workspace, "AR-012"))
    return errors


def _validate_ar019_go_service_binaries(workspace: Path) -> list[str]:
    errors: list[str] = []
    required = {
        "cmd/workload-manager/main.go": [
            "package main",
            "flag.Parse",
            "workloadmanager",
            "NewServer",
            "Start(",
            "signal",
        ],
        "cmd/router/main.go": [
            "package main",
            "flag.Parse",
            "router",
            "NewServer",
            "Start(",
            "signal",
        ],
        "cmd/picod/main.go": [
            "package main",
            "flag.Parse",
            "picod",
            "NewServer",
            "Run()",
        ],
        "cmd/agentd/main.go": [
            "package main",
            "ctrl.NewManager",
            "agentd.Reconciler",
            "SetupSignalHandler",
            "Complete(",
        ],
    }

    for rel, tokens in required.items():
        path = workspace / rel
        if not path.exists():
            errors.append(f"AR-019 must create or update {rel}")
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for token in tokens:
            if token not in text:
                errors.append(f"AR-019 {rel} missing required wiring token: {token}")

    forbidden_paths = [
        "cmd/kubectl-agentcube",
        "cmd/agentcube-router",
        "cmd/agentcube-workload-manager",
        "cmd/agentcube-agentd",
        "cmd/agentcube-picod",
        "pkg/cli",
        "pkg/models",
        "pkg/services",
    ]
    created_forbidden: list[str] = []
    for rel in forbidden_paths:
        path = workspace / rel
        if path.is_file():
            created_forbidden.append(rel)
        elif path.is_dir() and any(p.is_file() for p in path.rglob("*")):
            created_forbidden.append(rel)
    if created_forbidden:
        errors.append(
            "AR-019 implemented CLI/alias binaries outside the real Go service entrypoint scope: "
            + ", ".join(created_forbidden)
        )

    cmd_cli = workspace / "cmd/cli"
    if cmd_cli.exists() and any(p.is_file() for p in cmd_cli.rglob("*")):
        errors.append("AR-019 must not implement the Python cmd/cli user CLI; it belongs to later CLI ARs")

    return errors


def _validate_ar020_cli_pack_command(workspace: Path) -> list[str]:
    errors: list[str] = []
    cli_root = workspace / "cmd/cli"
    main = cli_root / "agentcube/cli/main.py"
    pack_runtime = cli_root / "agentcube/runtime/pack_runtime.py"
    pack_models = cli_root / "agentcube/models/pack_models.py"
    pyproject = cli_root / "pyproject.toml"

    for rel, path in {
        "cmd/cli/pyproject.toml": pyproject,
        "cmd/cli/agentcube/cli/main.py": main,
        "cmd/cli/agentcube/runtime/pack_runtime.py": pack_runtime,
        "cmd/cli/agentcube/models/pack_models.py": pack_models,
    }.items():
        if not path.exists():
            errors.append(f"AR-020 must create {rel}")
    if errors:
        return errors

    main_text = main.read_text(encoding="utf-8", errors="replace")
    runtime_text = pack_runtime.read_text(encoding="utf-8", errors="replace")
    model_text = pack_models.read_text(encoding="utf-8", errors="replace")
    pyproject_text = pyproject.read_text(encoding="utf-8", errors="replace")

    forbidden_files = [
        "agentcube/runtime/build_runtime.py",
        "agentcube/runtime/publish_runtime.py",
        "agentcube/runtime/invoke_runtime.py",
        "agentcube/runtime/status_runtime.py",
        "agentcube/runtime/metadata_service.py",
        "agentcube/services/docker_service.py",
        "agentcube/services/metadata_service.py",
        "agentcube/services/k8s_provider.py",
        "agentcube/services/agentcube_provider.py",
        "agentcube/tests/test_metadata_service.py",
        "agentcube/tests/test_docker_service.py",
    ]
    existing_forbidden = [rel for rel in forbidden_files if (cli_root / rel).exists()]
    if existing_forbidden:
        errors.append(
            "AR-020 implemented CLI modules reserved for later ARs: "
            + ", ".join(existing_forbidden)
        )

    forbidden_command_defs = ["def build(", "def publish(", "def invoke(", "def status("]
    present_commands = [token for token in forbidden_command_defs if token in main_text]
    if present_commands:
        errors.append(
            "AR-020 main.py must expose only the pack command; found reserved command definitions: "
            + ", ".join(present_commands)
        )

    for token in [
        "typer.Typer",
        "@app.command",
        "def pack(",
        "PackRuntime",
        "MetadataOptions",
        "workspace",
        "agent_name",
        "entrypoint",
        "language",
        "build_mode",
        "output",
    ]:
        if token not in main_text:
            errors.append(f"AR-020 CLI pack command missing token in main.py: {token}")

    for token in [
        "class PackRuntime",
        "def pack(",
        "Dockerfile",
        "agent_metadata.yaml",
        "requirements.txt",
        "entrypoint",
        "language",
    ]:
        if token not in runtime_text:
            errors.append(f"AR-020 PackRuntime missing pack behavior token: {token}")

    for token in ["MetadataOptions", "agent_name", "entrypoint", "language", "build_mode"]:
        if token not in model_text:
            errors.append(f"AR-020 pack models missing token: {token}")

    if "agentcube" not in pyproject_text or "typer" not in pyproject_text:
        errors.append("AR-020 pyproject.toml must define the agentcube CLI package and typer dependency")

    tests_root = cli_root / "agentcube/tests"
    pack_tests = []
    if tests_root.exists():
        pack_tests = [p for p in tests_root.rglob("test_*.py") if "pack" in p.name]
    if not pack_tests:
        errors.append("AR-020 must include pack-focused tests under cmd/cli/agentcube/tests")
    else:
        combined_tests = "\n".join(p.read_text(encoding="utf-8", errors="replace") for p in pack_tests)
        for token in ["PackRuntime", "Dockerfile", "requirements"]:
            if token not in combined_tests:
                errors.append(f"AR-020 pack tests missing token: {token}")
        if "agent_metadata" not in combined_tests and "metadata_path" not in combined_tests:
            errors.append("AR-020 pack tests missing token: agent_metadata or metadata_path")

    return errors


def _validate_ar021_cli_build_command(workspace: Path) -> list[str]:
    errors: list[str] = []
    cli_root = workspace / "cmd/cli"
    main = cli_root / "agentcube/cli/main.py"
    build_runtime = cli_root / "agentcube/runtime/build_runtime.py"
    build_tests = cli_root / "agentcube/tests/test_build.py"

    for rel, path in {
        "cmd/cli/agentcube/cli/main.py": main,
        "cmd/cli/agentcube/runtime/build_runtime.py": build_runtime,
        "cmd/cli/agentcube/tests/test_build.py": build_tests,
    }.items():
        if not path.exists():
            errors.append(f"AR-021 must create or update {rel}")
    if errors:
        return errors

    main_text = main.read_text(encoding="utf-8", errors="replace")
    runtime_text = build_runtime.read_text(encoding="utf-8", errors="replace")
    test_text = build_tests.read_text(encoding="utf-8", errors="replace")

    forbidden_files = [
        "agentcube/runtime/publish_runtime.py",
        "agentcube/runtime/invoke_runtime.py",
        "agentcube/runtime/status_runtime.py",
        "agentcube/services/docker_service.py",
        "agentcube/services/metadata_service.py",
        "agentcube/services/k8s_provider.py",
        "agentcube/services/agentcube_provider.py",
        "agentcube/tests/test_publish.py",
        "agentcube/tests/test_invoke.py",
        "agentcube/tests/test_status.py",
        "agentcube/tests/test_docker_service.py",
        "agentcube/tests/test_metadata_service.py",
    ]
    existing_forbidden = [rel for rel in forbidden_files if (cli_root / rel).exists()]
    if existing_forbidden:
        errors.append(
            "AR-021 implemented CLI modules reserved for later ARs: "
            + ", ".join(existing_forbidden)
        )

    for token in ["def publish(", "def invoke(", "def status("]:
        if token in main_text:
            errors.append(f"AR-021 main.py must not expose later command: {token}")

    for token in ["def build(", "BuildRuntime", "workspace", "build_mode", "proxy", "output"]:
        if token not in main_text:
            errors.append(f"AR-021 CLI build command missing token in main.py: {token}")

    for token in [
        "class BuildRuntime",
        "def build(",
        "agent_metadata.yaml",
        "Dockerfile",
        "build_mode",
        "local",
        "cloud",
        "version",
        "image",
        "docker",
    ]:
        if token not in runtime_text:
            errors.append(f"AR-021 BuildRuntime missing build behavior token: {token}")

    for token in ["BuildRuntime", "Dockerfile", "agent_metadata", "build_mode", "version"]:
        if token not in test_text:
            errors.append(f"AR-021 build tests missing token: {token}")

    return errors


def _validate_ar022_cli_publish_command(workspace: Path) -> list[str]:
    errors: list[str] = []
    cli_root = workspace / "cmd/cli"
    main = cli_root / "agentcube/cli/main.py"
    publish_runtime = cli_root / "agentcube/runtime/publish_runtime.py"
    tests_root = cli_root / "agentcube/tests"

    for rel, path in {
        "cmd/cli/agentcube/cli/main.py": main,
        "cmd/cli/agentcube/runtime/publish_runtime.py": publish_runtime,
        "cmd/cli/agentcube/tests": tests_root,
    }.items():
        if not path.exists():
            errors.append(f"AR-022 must create or update {rel}")
    if errors:
        return errors

    main_text = main.read_text(encoding="utf-8", errors="replace")
    runtime_text = publish_runtime.read_text(encoding="utf-8", errors="replace")
    publish_tests = [
        p for p in tests_root.rglob("test_*.py")
        if "publish" in p.name
    ]
    test_text = "\n".join(
        p.read_text(encoding="utf-8", errors="replace")
        for p in publish_tests
    )

    forbidden_files = [
        "agentcube/runtime/invoke_runtime.py",
        "agentcube/runtime/status_runtime.py",
        "agentcube/services/docker_service.py",
        "agentcube/services/metadata_service.py",
        "agentcube/services/k8s_provider.py",
        "agentcube/services/agentcube_provider.py",
        "agentcube/tests/test_invoke.py",
        "agentcube/tests/test_status.py",
        "agentcube/tests/test_docker_service.py",
        "agentcube/tests/test_metadata_service.py",
        "agentcube/tests/test_k8s_provider.py",
        "agentcube/tests/test_agentcube_provider.py",
    ]
    existing_forbidden = [rel for rel in forbidden_files if (cli_root / rel).exists()]
    if existing_forbidden:
        errors.append(
            "AR-022 implemented CLI modules reserved for later ARs: "
            + ", ".join(existing_forbidden)
        )

    for token in ["def invoke(", "def status("]:
        if token in main_text:
            errors.append(f"AR-022 main.py must not expose later command: {token}")

    for token in [
        "def publish(",
        "PublishRuntime",
        "workspace",
        "version",
        "image_url",
        "provider",
        "node_port",
        "replicas",
        "namespace",
    ]:
        if token not in main_text:
            errors.append(f"AR-022 CLI publish command missing token in main.py: {token}")

    for token in [
        "class PublishRuntime",
        "def publish(",
        "agent_metadata.yaml",
        "provider",
        "agentcube",
        "k8s",
        "router_url",
        "workload_manager_url",
        "Deployment",
        "NodePort",
        "image_url",
        "ValueError",
        "RuntimeError",
    ]:
        if token not in runtime_text:
            errors.append(f"AR-022 PublishRuntime missing publish behavior token: {token}")

    publish_body_end = runtime_text.find("\n    def _", runtime_text.find("def publish("))
    publish_body = (
        runtime_text[runtime_text.find("def publish("):publish_body_end]
        if publish_body_end != -1
        else runtime_text
    )
    prepare_idx = publish_body.find("_prepare_image")
    provider_validation_idx = min(
        [idx for idx in [
            publish_body.find("router_url"),
            publish_body.find("workload_manager_url"),
            publish_body.find("_validate"),
        ] if idx >= 0] or [-1]
    )
    if prepare_idx >= 0 and (provider_validation_idx < 0 or provider_validation_idx > prepare_idx):
        errors.append(
            "AR-022 publish must validate provider-specific fields before image preparation "
            "so missing router_url/workload_manager_url errors are not masked by Docker/Kubernetes work"
        )

    if not publish_tests:
        errors.append("AR-022 must include publish-focused tests under cmd/cli/agentcube/tests")
    else:
        for token in ["PublishRuntime", "router_url", "workload_manager_url", "Deployment", "NodePort"]:
            if token not in test_text:
                errors.append(f"AR-022 publish tests missing token: {token}")
        if "Unsupported provider" not in test_text and "unsupported provider" not in test_text.lower():
            errors.append("AR-022 publish tests must cover unsupported provider errors")

    return errors


def _validate_ar023_cli_invoke_status_command(workspace: Path) -> list[str]:
    errors: list[str] = []
    cli_root = workspace / "cmd/cli"
    main = cli_root / "agentcube/cli/main.py"
    invoke_runtime = cli_root / "agentcube/runtime/invoke_runtime.py"
    status_runtime = cli_root / "agentcube/runtime/status_runtime.py"
    pyproject = cli_root / "pyproject.toml"
    tests_root = cli_root / "agentcube/tests"

    for rel, path in {
        "cmd/cli/agentcube/cli/main.py": main,
        "cmd/cli/agentcube/runtime/invoke_runtime.py": invoke_runtime,
        "cmd/cli/agentcube/runtime/status_runtime.py": status_runtime,
        "cmd/cli/agentcube/tests": tests_root,
    }.items():
        if not path.exists():
            errors.append(f"AR-023 must create or update {rel}")
    if errors:
        return errors

    main_text = main.read_text(encoding="utf-8", errors="replace")
    invoke_text = invoke_runtime.read_text(encoding="utf-8", errors="replace")
    status_text = status_runtime.read_text(encoding="utf-8", errors="replace")
    pyproject_text = pyproject.read_text(encoding="utf-8", errors="replace") if pyproject.exists() else ""
    combined_source = "\n".join([main_text, invoke_text, status_text])

    forbidden_files = [
        "agentcube/services/docker_service.py",
        "agentcube/services/metadata_service.py",
        "agentcube/services/k8s_provider.py",
        "agentcube/services/agentcube_provider.py",
        "agentcube/operations/__init__.py",
        "agentcube/tests/test_docker_service.py",
        "agentcube/tests/test_metadata_service.py",
        "agentcube/tests/test_k8s_provider.py",
        "agentcube/tests/test_agentcube_provider.py",
    ]
    existing_forbidden = [rel for rel in forbidden_files if (cli_root / rel).exists()]
    if existing_forbidden:
        errors.append(
            "AR-023 implemented CLI service/provider modules reserved for later ARs: "
            + ", ".join(existing_forbidden)
        )

    forbidden_imports = [
        "agentcube.services.metadata_service",
        "agentcube.services.k8s_provider",
        "agentcube.services.agentcube_provider",
        "DockerService",
        "MetadataService",
        "KubernetesProvider",
        "AgentCubeProvider",
    ]
    imported_forbidden = [token for token in forbidden_imports if token in combined_source]
    if imported_forbidden:
        errors.append(
            "AR-023 must not depend on later service/provider abstractions: "
            + ", ".join(imported_forbidden)
        )

    for token in [
        "def invoke(",
        "InvokeRuntime",
        "payload",
        "headers",
        "def status(",
        "StatusRuntime",
        "workspace",
        "provider",
    ]:
        if token not in main_text:
            errors.append(f"AR-023 CLI invoke/status command missing token in main.py: {token}")

    for token in [
        "class InvokeRuntime",
        "def invoke(",
        "agent_metadata.yaml",
        "agent_id",
        "agent_endpoint",
        "session_id",
        "headers",
        "payload",
        "http",
        "post",
        "ValueError",
        "RuntimeError",
    ]:
        if token not in invoke_text:
            errors.append(f"AR-023 InvokeRuntime missing behavior token: {token}")

    for token in [
        "class StatusRuntime",
        "def get_status(",
        "agent_metadata.yaml",
        "not_published",
        "agent_id",
        "agent_name",
        "agent_endpoint",
        "status",
        "provider",
        "Table",
        "error",
    ]:
        if token not in status_text:
            errors.append(f"AR-023 StatusRuntime missing behavior token: {token}")

    if "httpx" in invoke_text and "httpx" not in pyproject_text:
        errors.append("AR-023 invoke uses httpx but cmd/cli/pyproject.toml does not declare an httpx dependency")

    test_files = [
        p for p in tests_root.rglob("test_*.py")
        if "invoke" in p.name or "status" in p.name
    ]
    if not test_files:
        errors.append("AR-023 must include invoke/status-focused tests under cmd/cli/agentcube/tests")
    else:
        test_text = "\n".join(p.read_text(encoding="utf-8", errors="replace") for p in test_files)
        for token in ["InvokeRuntime", "StatusRuntime", "not_published", "session"]:
            if token not in test_text:
                errors.append(f"AR-023 invoke/status tests missing token: {token}")

    return errors


def _validate_ar024_cli_docker_service(workspace: Path) -> list[str]:
    errors: list[str] = []
    cli_root = workspace / "cmd/cli"
    services_init = cli_root / "agentcube/services/__init__.py"
    docker_service = cli_root / "agentcube/services/docker_service.py"
    pyproject = cli_root / "pyproject.toml"
    tests_root = cli_root / "agentcube/tests"

    for rel, path in {
        "cmd/cli/agentcube/services/__init__.py": services_init,
        "cmd/cli/agentcube/services/docker_service.py": docker_service,
        "cmd/cli/agentcube/tests": tests_root,
    }.items():
        if not path.exists():
            errors.append(f"AR-024 must create or update {rel}")
    if errors:
        return errors

    service_text = docker_service.read_text(encoding="utf-8", errors="replace")
    pyproject_text = pyproject.read_text(encoding="utf-8", errors="replace") if pyproject.exists() else ""

    forbidden_files = [
        "agentcube/services/metadata_service.py",
        "agentcube/services/k8s_provider.py",
        "agentcube/services/agentcube_provider.py",
        "agentcube/operations/__init__.py",
        "agentcube/tests/test_metadata_service.py",
        "agentcube/tests/test_k8s_provider.py",
        "agentcube/tests/test_agentcube_provider.py",
    ]
    existing_forbidden = [rel for rel in forbidden_files if (cli_root / rel).exists()]
    if existing_forbidden:
        errors.append(
            "AR-024 implemented CLI metadata/provider modules reserved for later ARs: "
            + ", ".join(existing_forbidden)
        )

    forbidden_tokens = [
        "MetadataService",
        "KubernetesProvider",
        "AgentCubeProvider",
        "kubernetes.client",
        "kubernetes.config",
    ]
    leaked_tokens = [token for token in forbidden_tokens if token in service_text]
    if leaked_tokens:
        errors.append(
            "AR-024 DockerService must not implement later metadata/Kubernetes/provider abstractions: "
            + ", ".join(leaked_tokens)
        )

    for token in [
        "class DockerService",
        "docker.from_env",
        "from docker.errors import",
        "check_docker_available",
        "build_image",
        "push_image",
        "remove_image",
        "client.images.build",
        "client.images.push",
        "client.images.remove",
        "login",
        "tag",
        "BuildError",
        "APIError",
        "DockerException",
        "_format_size",
        "raise RuntimeError",
    ]:
        if token not in service_text:
            errors.append(f"AR-024 DockerService missing behavior token: {token}")

    for token in ["except BuildError", "except APIError", "except DockerException"]:
        if token not in service_text:
            errors.append(f"AR-024 DockerService must handle Docker SDK exception path: {token}")

    local_exception_defs = [
        token for token in ["class DockerException", "class BuildError", "class APIError"]
        if token in service_text
    ]
    if local_exception_defs:
        errors.append(
            "AR-024 must import Docker SDK exceptions from docker.errors, not define local exception classes: "
            + ", ".join(local_exception_defs)
        )

    if "docker" not in pyproject_text.lower():
        errors.append("AR-024 DockerService requires cmd/cli/pyproject.toml to declare the docker dependency")

    if "NotImplementedError" in service_text:
        errors.append("AR-024 DockerService must not use NotImplementedError")

    docker_tests = [
        p for p in tests_root.rglob("test_*.py")
        if "docker" in p.name or "service" in p.name
    ]
    if not docker_tests:
        errors.append("AR-024 must include DockerService-focused tests under cmd/cli/agentcube/tests")
    else:
        test_text = "\n".join(p.read_text(encoding="utf-8", errors="replace") for p in docker_tests)
        for token in [
            "DockerService",
            "build_image",
            "push_image",
            "remove_image",
            "check_docker_available",
            "docker.from_env",
        ]:
            if token not in test_text:
                errors.append(f"AR-024 DockerService tests missing token: {token}")
        if "NotImplementedError" in test_text:
            errors.append("AR-024 DockerService tests must not assert placeholder NotImplementedError behavior")

    return errors


def _validate_ar025_cli_metadata_service(workspace: Path) -> list[str]:
    errors: list[str] = []
    cli_root = workspace / "cmd/cli"
    services_init = cli_root / "agentcube/services/__init__.py"
    metadata_service = cli_root / "agentcube/services/metadata_service.py"
    pack_models = cli_root / "agentcube/models/pack_models.py"
    pyproject = cli_root / "pyproject.toml"
    tests_root = cli_root / "agentcube/tests"

    for rel, path in {
        "cmd/cli/agentcube/services/__init__.py": services_init,
        "cmd/cli/agentcube/services/metadata_service.py": metadata_service,
        "cmd/cli/agentcube/tests": tests_root,
    }.items():
        if not path.exists():
            errors.append(f"AR-025 must create or update {rel}")
    if errors:
        return errors

    service_text = metadata_service.read_text(encoding="utf-8", errors="replace")
    init_text = services_init.read_text(encoding="utf-8", errors="replace")
    pack_models_text = pack_models.read_text(encoding="utf-8", errors="replace") if pack_models.exists() else ""
    pyproject_text = pyproject.read_text(encoding="utf-8", errors="replace") if pyproject.exists() else ""
    combined_source = "\n".join([service_text, init_text])

    if re.search(r"from\s+agentcube\.models\.pack_models\s+import\s+[^\n]*AgentMetadata", service_text):
        errors.append(
            "AR-025 metadata_service.py must define AgentMetadata locally; do not import it from pack_models.py"
        )

    forbidden_files = [
        "agentcube/services/k8s_provider.py",
        "agentcube/services/agentcube_provider.py",
        "agentcube/operations/__init__.py",
        "agentcube/tests/test_k8s_provider.py",
        "agentcube/tests/test_agentcube_provider.py",
    ]
    existing_forbidden = [rel for rel in forbidden_files if (cli_root / rel).exists()]
    if existing_forbidden:
        errors.append(
            "AR-025 implemented CLI provider modules reserved for AR-026: "
            + ", ".join(existing_forbidden)
        )

    forbidden_tokens = [
        "class KubernetesProvider",
        "class AgentCubeProvider",
        "kubernetes.client",
        "kubernetes.config",
        "CustomObjectsApi",
        "AppsV1Api",
        "CoreV1Api",
    ]
    leaked_tokens = [token for token in forbidden_tokens if token in combined_source]
    if leaked_tokens:
        errors.append(
            "AR-025 MetadataService must not implement provider/Kubernetes behavior: "
            + ", ".join(leaked_tokens)
        )

    for token in [
        "class AgentMetadata",
        "BaseModel",
        "Field",
        "field_validator",
        "agent_name",
        "description",
        "language",
        "entrypoint",
        "port",
        "build_mode",
        "region",
        "version",
        "image",
        "auth",
        "requirements_file",
        "registry_url",
        "registry_username",
        "registry_password",
        "agent_endpoint",
        "workload_manager_url",
        "router_url",
        "readiness_probe_path",
        "readiness_probe_port",
        "agent_id",
        "session_id",
        "k8s_deployment",
        "validate_language",
        "validate_build_mode",
        "validate_port",
        "class MetadataService",
        "load_metadata",
        "save_metadata",
        "update_metadata",
        "validate_workspace",
        "_validate_python_workspace",
        "_validate_java_workspace",
        "_validate_python_workspace(workspace_path, metadata)",
        "_validate_java_workspace(workspace_path, metadata)",
        "metadata.entrypoint",
        "metadata.requirements_file",
        "entrypoint_parts",
        "src_main_java",
        "src/main/java",
        "root.tag",
        "agent_metadata.yaml",
        "agent.yaml",
        "metadata.yaml",
        "yaml.safe_load",
        "yaml.dump",
        "ET.parse",
        "model_dump",
        "model_copy",
        "FileNotFoundError",
        "ValueError",
    ]:
        if token not in service_text:
            errors.append(f"AR-025 MetadataService missing behavior token: {token}")

    if "class MetadataOptions" not in pack_models_text:
        errors.append("AR-025 must keep the AR-020 MetadataOptions model in pack_models.py")

    contaminated_imports: list[str] = []
    contaminated_pack_model_imports: list[str] = []
    missing_runtime_integration: list[str] = []
    for rel in [
        "agentcube/runtime/pack_runtime.py",
        "agentcube/runtime/build_runtime.py",
        "agentcube/runtime/publish_runtime.py",
        "agentcube/runtime/invoke_runtime.py",
        "agentcube/runtime/status_runtime.py",
        "agentcube/tests/test_pack.py",
        "agentcube/tests/test_build.py",
        "agentcube/tests/test_build_runtime.py",
        "agentcube/tests/test_publish.py",
        "agentcube/tests/test_publish_runtime.py",
        "agentcube/tests/test_invoke.py",
        "agentcube/tests/test_status.py",
    ]:
        path = cli_root / rel
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if (
            "from agentcube.services import AgentMetadata" in text
            or "from agentcube.services import MetadataService" in text
        ):
            contaminated_imports.append(rel)
        if re.search(r"from\s+agentcube\.models\.pack_models\s+import\s+[^\n]*AgentMetadata", text):
            contaminated_pack_model_imports.append(rel)
        if rel.startswith("agentcube/runtime/") and "metadata_service" not in text and "MetadataService" not in text:
            missing_runtime_integration.append(rel)
    if contaminated_imports:
        errors.append(
            "AR-025 must import MetadataService/AgentMetadata directly from agentcube.services.metadata_service, "
            "not package-level agentcube.services: "
            + ", ".join(contaminated_imports[:8])
        )
    if contaminated_pack_model_imports:
        errors.append(
            "AR-025 must migrate runtime/tests off pack_models.AgentMetadata and use "
            "agentcube.services.metadata_service.AgentMetadata: "
            + ", ".join(contaminated_pack_model_imports[:8])
        )
    if missing_runtime_integration:
        errors.append(
            "AR-025 should integrate MetadataService with existing CLI runtimes: "
            + ", ".join(missing_runtime_integration[:8])
        )

    missing_deps = [
        dep for dep in ["pydantic", "pyyaml"]
        if dep not in pyproject_text.lower()
    ]
    if missing_deps:
        errors.append(
            "AR-025 MetadataService requires cmd/cli/pyproject.toml dependencies: "
            + ", ".join(missing_deps)
        )

    if "NotImplementedError" in service_text:
        errors.append("AR-025 MetadataService must not use NotImplementedError")

    metadata_tests = [
        p for p in tests_root.rglob("test_*.py")
        if "metadata" in p.name
    ]
    if not metadata_tests:
        errors.append("AR-025 must include MetadataService-focused tests under cmd/cli/agentcube/tests")
    else:
        test_text = "\n".join(p.read_text(encoding="utf-8", errors="replace") for p in metadata_tests)
        for token in [
            "MetadataService",
            "AgentMetadata",
            "load_metadata",
            "save_metadata",
            "update_metadata",
            "validate_workspace",
            "agent_metadata.yaml",
            "agent.yaml",
            "metadata.yaml",
            "python",
            "java",
            "pom.xml",
            "requirements.txt",
            "requirements_file",
            "entrypoint",
            "src/main/java",
        ]:
            if token not in test_text:
                errors.append(f"AR-025 MetadataService tests missing token: {token}")
        for token, alternatives in {
            "unsupported": ["unsupported", "not supported"],
            "invalid": ["invalid"],
            "port": ["port"],
        }.items():
            if not any(alt in test_text.lower() for alt in alternatives):
                errors.append(f"AR-025 MetadataService tests must cover {token} validation")
        if "NotImplementedError" in test_text:
            errors.append("AR-025 MetadataService tests must not assert placeholder NotImplementedError behavior")

    return errors


def _validate_ar026_cli_providers(workspace: Path) -> list[str]:
    errors: list[str] = []
    cli_root = workspace / "cmd/cli"
    services_init = cli_root / "agentcube/services/__init__.py"
    k8s_provider = cli_root / "agentcube/services/k8s_provider.py"
    agentcube_provider = cli_root / "agentcube/services/agentcube_provider.py"
    publish_runtime = cli_root / "agentcube/runtime/publish_runtime.py"
    status_runtime = cli_root / "agentcube/runtime/status_runtime.py"
    pyproject = cli_root / "pyproject.toml"
    tests_root = cli_root / "agentcube/tests"

    for rel, path in {
        "cmd/cli/agentcube/services/__init__.py": services_init,
        "cmd/cli/agentcube/services/k8s_provider.py": k8s_provider,
        "cmd/cli/agentcube/services/agentcube_provider.py": agentcube_provider,
        "cmd/cli/agentcube/runtime/publish_runtime.py": publish_runtime,
        "cmd/cli/agentcube/runtime/status_runtime.py": status_runtime,
        "cmd/cli/agentcube/tests": tests_root,
    }.items():
        if not path.exists():
            errors.append(f"AR-026 must create or update {rel}")
    if errors:
        return errors

    init_text = services_init.read_text(encoding="utf-8", errors="replace")
    k8s_text = k8s_provider.read_text(encoding="utf-8", errors="replace")
    agentcube_text = agentcube_provider.read_text(encoding="utf-8", errors="replace")
    publish_text = publish_runtime.read_text(encoding="utf-8", errors="replace")
    status_text = status_runtime.read_text(encoding="utf-8", errors="replace")
    pyproject_text = pyproject.read_text(encoding="utf-8", errors="replace") if pyproject.exists() else ""
    source_text = "\n".join([k8s_text, agentcube_text, publish_text, status_text])

    for token in [
        "class KubernetesProvider",
        "from kubernetes import client, config",
        "ApiException",
        "CoreV1Api",
        "AppsV1Api",
        "load_incluster_config",
        "load_kube_config",
        "ConfigException",
        "_ensure_namespace",
        "read_namespace",
        "create_namespace",
        "deploy_agent",
        "_create_deployment",
        "V1Container",
        "shlex.split",
        "V1Deployment",
        "patch_namespaced_deployment",
        "create_namespaced_deployment",
        "_create_service",
        "V1Service",
        "NodePort",
        "patch_namespaced_service",
        "create_namespaced_service",
        "wait_for_deployment_ready",
        "ready_replicas",
        "TimeoutError",
        "get_agent_status",
        "list_namespaced_pod",
        "delete_agent",
        "delete_namespaced_deployment",
        "delete_namespaced_service",
        "_sanitize_name",
        "RuntimeError",
    ]:
        if token not in k8s_text:
            errors.append(f"AR-026 KubernetesProvider missing behavior token: {token}")

    for token in [
        "class AgentCubeProvider",
        "from kubernetes import client, config",
        "ApiException",
        "CoreV1Api",
        "CustomObjectsApi",
        "load_incluster_config",
        "load_kube_config",
        "ConfigException",
        "_ensure_namespace",
        "read_namespace",
        "create_namespace",
        "deploy_agent_runtime",
        "runtime.agentcube.volcano.sh",
        "v1alpha1",
        "agentruntimes",
        "AgentRuntime",
        "targetPort",
        "podTemplate",
        "imagePullSecrets",
        "default-secret",
        "sessionTimeout",
        "15m",
        "maxSessionDuration",
        "8h",
        "WORKLOAD_MANAGER_URL",
        "ROUTER_URL",
        "shlex.split",
        "get_namespaced_custom_object",
        "patch_namespaced_custom_object",
        "create_namespaced_custom_object",
        "get_agent_runtime",
        "_sanitize_name",
        "RuntimeError",
    ]:
        if token not in agentcube_text:
            errors.append(f"AR-026 AgentCubeProvider missing behavior token: {token}")
    if "os.environ" not in agentcube_text and "os.getenv" not in agentcube_text:
        errors.append("AR-026 AgentCubeProvider missing behavior token: os.environ or os.getenv")

    for token in ["KubernetesProvider", "AgentCubeProvider"]:
        if token not in init_text:
            errors.append(f"AR-026 services package must export {token}")

    if "kubernetes" not in pyproject_text.lower():
        errors.append("AR-026 must add the real kubernetes dependency to cmd/cli/pyproject.toml")

    for token in [
        "KubernetesProvider",
        "AgentCubeProvider",
        "deploy_agent(",
        "wait_for_deployment_ready",
        "deploy_agent_runtime",
    ]:
        if token not in publish_text:
            errors.append(f"AR-026 publish runtime must integrate provider token: {token}")

    for token in [
        "KubernetesProvider",
        "AgentCubeProvider",
        "get_agent_status",
        "get_agent_runtime",
        "created_no_status",
        "not_found_in_k8s",
    ]:
        if token not in status_text:
            errors.append(f"AR-026 status runtime must integrate provider token: {token}")

    runtime_inline_tokens = [
        "CustomObjectsApi",
        "AppsV1Api",
        "CoreV1Api",
        "create_namespaced_custom_object",
        "create_namespaced_deployment",
        "create_namespaced_service",
        "read_namespaced_deployment(",
        "read_namespaced_service(",
    ]
    inline_leaks = [
        f"{rel}:{token}"
        for rel, text in {
            "publish_runtime.py": publish_text,
            "status_runtime.py": status_text,
        }.items()
        for token in runtime_inline_tokens
        if token in text
    ]
    if inline_leaks:
        errors.append(
            "AR-026 must move direct Kubernetes API deployment/status logic out of runtimes into providers: "
            + ", ".join(inline_leaks[:10])
        )

    if "NotImplementedError" in source_text:
        errors.append("AR-026 provider source must not use NotImplementedError")

    provider_tests = []
    if tests_root.exists():
        provider_tests = [
            p for p in tests_root.rglob("test_*.py")
            if any(token in p.read_text(encoding="utf-8", errors="replace")
                   for token in ["KubernetesProvider", "AgentCubeProvider"])
        ]
    if not provider_tests:
        errors.append("AR-026 must include provider-focused tests under cmd/cli/agentcube/tests")
    else:
        test_text = "\n".join(p.read_text(encoding="utf-8", errors="replace") for p in provider_tests)
        for token in [
            "KubernetesProvider",
            "AgentCubeProvider",
            "deploy_agent",
            "wait_for_deployment_ready",
            "delete_agent",
            "get_agent_status",
            "deploy_agent_runtime",
            "get_agent_runtime",
            "runtime.agentcube.volcano.sh",
            "agentruntimes",
            "TimeoutError",
            "ApiException",
            "Mock",
        ]:
            if token not in test_text:
                errors.append(f"AR-026 provider tests missing token: {token}")
        if "NodePort" not in test_text and "node_port" not in test_text:
            errors.append("AR-026 provider tests missing token: NodePort or node_port")
        if "NotImplementedError" in test_text:
            errors.append("AR-026 provider tests must not assert placeholder NotImplementedError behavior")

    return errors


def _validate_ar027_sdk_code_interpreter(workspace: Path) -> list[str]:
    errors: list[str] = []
    sdk_root = workspace / "sdk-python"
    package_init = sdk_root / "agentcube/__init__.py"
    code_interpreter = sdk_root / "agentcube/code_interpreter.py"
    pyproject = sdk_root / "pyproject.toml"
    tests_root = sdk_root / "tests"

    for rel, path in {
        "sdk-python/agentcube/__init__.py": package_init,
        "sdk-python/agentcube/code_interpreter.py": code_interpreter,
        "sdk-python/pyproject.toml": pyproject,
        "sdk-python/tests": tests_root,
    }.items():
        if not path.exists():
            errors.append(f"AR-027 must create {rel}")
    if errors:
        return errors

    if (workspace / "agentcube").exists():
        errors.append("AR-027 must not create a top-level agentcube/ package; SDK code belongs under sdk-python/")

    forbidden_files = [
        "agentcube/agent_runtime.py",
        "agentcube/clients/agent_runtime_data_plane.py",
        "tests/test_agent_runtime.py",
        "tests/test_code_interpreter_data_plane.py",
        "tests/test_control_plane.py",
        "tests/test_http.py",
        "tests/test_log.py",
        "tests/test_exceptions.py",
    ]
    existing_forbidden = [rel for rel in forbidden_files if (sdk_root / rel).exists()]
    if existing_forbidden:
        errors.append(
            "AR-027 must not implement SDK AgentRuntime or low-level HTTP/data-plane tests reserved for AR-028/AR-029: "
            + ", ".join(existing_forbidden)
        )

    init_text = package_init.read_text(encoding="utf-8", errors="replace")
    code_text = code_interpreter.read_text(encoding="utf-8", errors="replace")
    pyproject_text = pyproject.read_text(encoding="utf-8", errors="replace")

    for token in [
        "CodeInterpreterClient",
        "__all__",
    ]:
        if token not in init_text:
            errors.append(f"AR-027 sdk-python/agentcube/__init__.py missing token: {token}")
    if "AgentRuntimeClient" in init_text:
        errors.append("AR-027 must not export AgentRuntimeClient before AR-028")

    for token in [
        "class CodeInterpreterClient",
        "def __init__(",
        "name",
        "namespace",
        "ttl",
        "workload_manager_url",
        "router_url",
        "auth_token",
        "verbose",
        "session_id",
        "os.getenv",
        "ROUTER_URL",
        "ValueError",
        "ControlPlaneClient",
        "CodeInterpreterDataPlaneClient",
        "create_session",
        "delete_session",
        "_init_data_plane",
        "self.session_id",
        "self.dp_client",
        "def __enter__(",
        "def __exit__(",
        "def stop(",
        "def execute_command(",
        "def run_code(",
        "def write_file(",
        "def upload_file(",
        "def download_file(",
        "def list_files(",
        "close",
        "logger.warning",
    ]:
        if token not in code_text:
            errors.append(f"AR-027 CodeInterpreterClient missing behavior token: {token}")

    if "NotImplementedError" in code_text:
        errors.append("AR-027 CodeInterpreterClient must not use NotImplementedError")
    if re.search(r"^\s*pass\s*(#.*)?$", code_text, flags=re.MULTILINE):
        errors.append("AR-027 CodeInterpreterClient source must not contain pass-only placeholders")

    for token in ["agentcube-sdk", "setuptools", "agentcube*"]:
        if token not in pyproject_text:
            errors.append(f"AR-027 sdk-python/pyproject.toml missing token: {token}")

    code_tests = [
        p for p in tests_root.rglob("test_*.py")
        if "code" in p.name or "interpreter" in p.name
    ]
    if not code_tests:
        errors.append("AR-027 must include CodeInterpreterClient-focused tests under sdk-python/tests")
    else:
        test_text = "\n".join(p.read_text(encoding="utf-8", errors="replace") for p in code_tests)
        for token in [
            "CodeInterpreterClient",
            "ControlPlaneClient",
            "CodeInterpreterDataPlaneClient",
            "Mock",
            "patch",
            "create_session",
            "delete_session",
            "session_id",
            "ROUTER_URL",
            "ValueError",
            "stop",
            "side_effect",
            "execute_command",
            "run_code",
            "write_file",
            "upload_file",
            "download_file",
            "list_files",
        ]:
            if token not in test_text:
                errors.append(f"AR-027 CodeInterpreterClient tests missing token: {token}")
        if "with CodeInterpreterClient" not in test_text and "__enter__" not in test_text and "context manager" not in test_text:
            errors.append("AR-027 CodeInterpreterClient tests missing context manager coverage")
        if "NotImplementedError" in test_text:
            errors.append("AR-027 CodeInterpreterClient tests must not assert placeholder NotImplementedError behavior")

    return errors


def _validate_ar028_sdk_agent_runtime(workspace: Path) -> list[str]:
    errors: list[str] = []
    sdk_root = workspace / "sdk-python"
    package_init = sdk_root / "agentcube/__init__.py"
    agent_runtime = sdk_root / "agentcube/agent_runtime.py"
    data_plane = sdk_root / "agentcube/clients/agent_runtime_data_plane.py"
    tests_root = sdk_root / "tests"
    agent_tests = tests_root / "test_agent_runtime.py"

    for rel, path in {
        "sdk-python/agentcube/__init__.py": package_init,
        "sdk-python/agentcube/agent_runtime.py": agent_runtime,
        "sdk-python/agentcube/clients/agent_runtime_data_plane.py": data_plane,
        "sdk-python/tests/test_agent_runtime.py": agent_tests,
    }.items():
        if not path.exists():
            errors.append(f"AR-028 must create or update {rel}")
    if errors:
        return errors

    if (workspace / "agentcube").exists():
        errors.append("AR-028 must not create a top-level agentcube/ package; SDK code belongs under sdk-python/")

    forbidden_tests = [
        "test_code_interpreter_data_plane.py",
        "test_control_plane.py",
        "test_http.py",
        "test_log.py",
        "test_exceptions.py",
    ]
    existing_forbidden = [name for name in forbidden_tests if (tests_root / name).exists()]
    if existing_forbidden:
        errors.append(
            "AR-028 must not implement low-level SDK tests reserved for AR-029: "
            + ", ".join(existing_forbidden)
        )

    init_text = package_init.read_text(encoding="utf-8", errors="replace")
    agent_text = agent_runtime.read_text(encoding="utf-8", errors="replace")
    data_plane_text = data_plane.read_text(encoding="utf-8", errors="replace")
    test_text = agent_tests.read_text(encoding="utf-8", errors="replace")

    for token in ["CodeInterpreterClient", "AgentRuntimeClient", "__all__"]:
        if token not in init_text:
            errors.append(f"AR-028 sdk-python/agentcube/__init__.py missing token: {token}")

    for token in [
        "class AgentRuntimeClient",
        "def __init__(",
        "agent_name",
        "namespace",
        "router_url",
        "verbose",
        "session_id",
        "timeout",
        "connect_timeout",
        "os.getenv",
        "ROUTER_URL",
        "ValueError",
        "AgentRuntimeDataPlaneClient",
        "bootstrap_session_id",
        "self.session_id",
        "def __enter__(",
        "def __exit__(",
        "def invoke(",
        "raise_for_status",
        "JSONDecodeError",
        "resp.json",
        "resp.text",
        "AgentRuntime session_id is not initialized",
        "def close(",
        "dp_client.close",
    ]:
        if token not in agent_text:
            errors.append(f"AR-028 AgentRuntimeClient missing behavior token: {token}")

    for token in [
        "class AgentRuntimeDataPlaneClient",
        "SESSION_HEADER",
        "x-agentcube-session-id",
        "urljoin",
        "agent-runtimes",
        "invocations",
        "create_session",
        "self.base_url",
        "def bootstrap_session_id(",
        "self.session.get",
        "headers.get",
        "Missing required response header",
        "def invoke(",
        "self.session.post",
        "json=payload",
        "headers=headers",
        "Content-Type",
        "def close(",
        "self.session.close",
    ]:
        if token not in data_plane_text:
            errors.append(f"AR-028 AgentRuntimeDataPlaneClient missing behavior token: {token}")

    combined_source = "\n".join([agent_text, data_plane_text])
    if "NotImplementedError" in combined_source:
        errors.append("AR-028 SDK source must not use NotImplementedError")
    if re.search(r"^\s*pass\s*(#.*)?$", combined_source, flags=re.MULTILINE):
        errors.append("AR-028 SDK source must not contain pass-only placeholders")

    for token in [
        "AgentRuntimeClient",
        "AgentRuntimeDataPlaneClient",
        "Mock",
        "patch",
        "bootstrap_session_id",
        "session_id",
        "invoke",
        "raise_for_status",
        "JSONDecodeError",
        "ROUTER_URL",
        "ValueError",
        "x-agentcube-session-id",
        "Missing required response header",
        "close",
    ]:
        if token not in test_text:
            errors.append(f"AR-028 AgentRuntime tests missing token: {token}")
    if "NotImplementedError" in test_text:
        errors.append("AR-028 AgentRuntime tests must not assert placeholder NotImplementedError behavior")

    return errors


def _validate_ar029_sdk_http_clients(workspace: Path) -> list[str]:
    errors: list[str] = []
    sdk_root = workspace / "sdk-python"
    control_plane = sdk_root / "agentcube/clients/control_plane.py"
    code_dp = sdk_root / "agentcube/clients/code_interpreter_data_plane.py"
    http_utils = sdk_root / "agentcube/utils/http.py"
    misc_utils = sdk_root / "agentcube/utils/utils.py"
    exceptions = sdk_root / "agentcube/exceptions.py"
    tests_root = sdk_root / "tests"

    for rel, path in {
        "sdk-python/agentcube/clients/control_plane.py": control_plane,
        "sdk-python/agentcube/clients/code_interpreter_data_plane.py": code_dp,
        "sdk-python/agentcube/utils/http.py": http_utils,
        "sdk-python/agentcube/utils/utils.py": misc_utils,
        "sdk-python/agentcube/exceptions.py": exceptions,
        "sdk-python/tests": tests_root,
    }.items():
        if not path.exists():
            errors.append(f"AR-029 must create or update {rel}")
    if errors:
        return errors

    if (workspace / "agentcube").exists():
        errors.append("AR-029 must not create a top-level agentcube/ package; SDK code belongs under sdk-python/")

    control_text = control_plane.read_text(encoding="utf-8", errors="replace")
    code_dp_text = code_dp.read_text(encoding="utf-8", errors="replace")
    http_text = http_utils.read_text(encoding="utf-8", errors="replace")
    utils_text = misc_utils.read_text(encoding="utf-8", errors="replace")
    exceptions_text = exceptions.read_text(encoding="utf-8", errors="replace")
    source_text = "\n".join([control_text, code_dp_text, http_text, utils_text, exceptions_text])

    for token in [
        "class ControlPlaneClient",
        "WORKLOAD_MANAGER_URL",
        "read_token_from_file",
        "create_session",
        "self.session.headers.update",
        "Content-Type",
        "Authorization",
        "Bearer",
        "def create_session(",
        "/v1/code-interpreter",
        "metadata",
        "ttl",
        "self.session.post",
        "timeout=(self.connect_timeout, self.timeout)",
        "sessionId",
        "ValueError",
        "def delete_session(",
        "/v1/code-interpreter/sessions",
        "status_code == 404",
        "return True",
        "def close(",
        "self.session.close",
    ]:
        if token not in control_text:
            errors.append(f"AR-029 ControlPlaneClient missing behavior token: {token}")
    if "requests.exceptions.RequestException" not in control_text and "RequestException" not in control_text:
        errors.append("AR-029 ControlPlaneClient missing behavior token: RequestException")

    for token in [
        "class CodeInterpreterDataPlaneClient",
        "session_id",
        "router_url",
        "namespace",
        "cr_name",
        "base_url",
        "urljoin",
        "code-interpreters",
        "invocations",
        "x-agentcube-session-id",
        "def _request(",
        "self.session.request",
        "Content-Type",
        "def execute_command(",
        "shlex.split",
        "timeout_str",
        "api/execute",
        "exit_code",
        "CommandExecutionError",
        "def run_code(",
        "ast.parse",
        "python3",
        "self.write_file",
        "def write_file(",
        "base64.b64encode",
        "api/files",
        "def upload_file(",
        "FileNotFoundError",
        "files",
        "def download_file(",
        "iter_content",
        "def list_files(",
        "params",
        "def close(",
        "self.session.close",
    ]:
        if token not in code_dp_text:
            errors.append(f"AR-029 CodeInterpreterDataPlaneClient missing behavior token: {token}")
    if not any(token in code_dp_text for token in [
        "timeout=(self.connect_timeout, kwargs",
        "timeout=(self.connect_timeout, self.timeout)",
        "timeout = (self.connect_timeout, self.timeout)",
        "timeout=(self.connect_timeout, read_timeout)",
        "kwargs[\"timeout\"]",
    ]):
        errors.append("AR-029 CodeInterpreterDataPlaneClient missing request timeout tuple behavior")
    if 'result["exit_code"]' not in code_dp_text and "result.get(\"exit_code\"" not in code_dp_text:
        errors.append("AR-029 CodeInterpreterDataPlaneClient must parse PicoD exit_code response field")

    for token in ["HTTPAdapter", "pool_connections", "pool_maxsize"]:
        if token not in http_text:
            errors.append(f"AR-029 HTTP utility missing token: {token}")
    if 'session.mount("http://"' not in http_text and "session.mount('http://'" not in http_text:
        errors.append("AR-029 HTTP utility missing token: session.mount('http://')")
    if 'session.mount("https://"' not in http_text and "session.mount('https://'" not in http_text:
        errors.append("AR-029 HTTP utility missing token: session.mount('https://')")

    for token in ["def read_token_from_file", "return \"\""]:
        if token not in utils_text:
            errors.append(f"AR-029 utils missing token: {token}")
    if "FileNotFoundError" not in utils_text and "os.path.exists" not in utils_text:
        errors.append("AR-029 utils must handle missing token files")

    for token in ["class AgentCubeError", "class CommandExecutionError", "exit_code", "stderr", "command"]:
        if token not in exceptions_text:
            errors.append(f"AR-029 exceptions missing token: {token}")

    if "NotImplementedError" in source_text:
        errors.append("AR-029 SDK source must not use NotImplementedError")

    low_level_tests = []
    for p in tests_root.rglob("test_*.py"):
        text = p.read_text(encoding="utf-8", errors="replace")
        if (
            any(name in p.name for name in ["control", "data_plane", "http", "utils", "exceptions", "client"])
            or "ControlPlaneClient" in text
            or "CodeInterpreterDataPlaneClient" in text
            or "read_token_from_file" in text
        ):
            low_level_tests.append(p)
    if not low_level_tests:
        errors.append("AR-029 must include focused low-level SDK tests under sdk-python/tests")
    else:
        test_text = "\n".join(p.read_text(encoding="utf-8", errors="replace") for p in low_level_tests)
        for token in [
            "ControlPlaneClient",
            "CodeInterpreterDataPlaneClient",
            "create_session",
            "delete_session",
            "sessionId",
            "x-agentcube-session-id",
            "execute_command",
            "CommandExecutionError",
            "run_code",
            "write_file",
            "upload_file",
            "download_file",
            "list_files",
            "pool_connections",
            "read_token_from_file",
            "Mock",
            "patch",
        ]:
            if token not in test_text:
                errors.append(f"AR-029 low-level SDK tests missing token: {token}")
        if "NotImplementedError" in test_text:
            errors.append("AR-029 low-level SDK tests must not assert placeholder NotImplementedError behavior")

    return errors


def _validate_ar030_helm_chart(workspace: Path) -> list[str]:
    errors: list[str] = []
    chart_root = workspace / "manifests/charts/base"
    chart_yaml = chart_root / "Chart.yaml"
    values_yaml = chart_root / "values.yaml"
    templates_root = chart_root / "templates"
    crds_root = chart_root / "crds"

    for rel, path in {
        "manifests/charts/base/Chart.yaml": chart_yaml,
        "manifests/charts/base/values.yaml": values_yaml,
        "manifests/charts/base/templates": templates_root,
        "manifests/charts/base/crds": crds_root,
    }.items():
        if not path.exists():
            errors.append(f"AR-030 must create {rel}")
    if errors:
        return errors

    def load_yaml(rel: str, path: Path) -> dict:
        try:
            import yaml
            data = yaml.safe_load(path.read_text(encoding="utf-8", errors="replace"))
        except Exception as exc:
            errors.append(f"AR-030 {rel} must be valid YAML: {exc}")
            return {}
        if not isinstance(data, dict):
            errors.append(f"AR-030 {rel} must contain a YAML mapping")
            return {}
        return data

    def nested(data: dict, dotted: str):
        cur = data
        for part in dotted.split("."):
            if not isinstance(cur, dict) or part not in cur:
                return None
            cur = cur[part]
        return cur

    def require_nested(data: dict, label: str, expected=None) -> None:
        value = nested(data, label)
        if value is None:
            errors.append(f"AR-030 values.yaml missing key: {label}")
            return
        if expected is not None and value != expected:
            errors.append(f"AR-030 values.yaml key {label} expected {expected!r}, got {value!r}")

    def require_token(label: str, text: str, token: str) -> None:
        if token not in text:
            errors.append(f"AR-030 {label} missing token: {token}")

    chart = load_yaml("Chart.yaml", chart_yaml)
    values = load_yaml("values.yaml", values_yaml)
    chart_text = chart_yaml.read_text(encoding="utf-8", errors="replace")
    values_text = values_yaml.read_text(encoding="utf-8", errors="replace")

    for key, expected in {
        "apiVersion": "v1",
        "name": "agentcube",
        "description": "A Helm chart for AgentCube",
        "version": "0.1.0",
        "appVersion": "1.0.0",
    }.items():
        if chart.get(key) != expected:
            errors.append(f"AR-030 Chart.yaml {key} expected {expected!r}, got {chart.get(key)!r}")

    if not isinstance(values.get("imagePullSecrets"), list):
        errors.append("AR-030 values.yaml imagePullSecrets must be a list")
    require_nested(values, "nameOverride", "")
    require_nested(values, "fullnameOverride", "")
    require_nested(values, "redis.addr", "")
    require_nested(values, "redis.password", "")
    for prefix, repository in {
        "router": "ghcr.io/volcano-sh/agentcube-router",
        "workloadmanager": "ghcr.io/volcano-sh/workloadmanager",
    }.items():
        require_nested(values, f"{prefix}.replicas", 1)
        require_nested(values, f"{prefix}.image.repository", repository)
        require_nested(values, f"{prefix}.image.pullPolicy", "IfNotPresent")
        require_nested(values, f"{prefix}.image.tag", "latest")
        require_nested(values, f"{prefix}.service.type", "ClusterIP")
        require_nested(values, f"{prefix}.service.port", 8080)
        require_nested(values, f"{prefix}.resources.limits.cpu", "500m")
        require_nested(values, f"{prefix}.resources.limits.memory", "512Mi")
        require_nested(values, f"{prefix}.resources.requests.cpu", "100m")
        require_nested(values, f"{prefix}.resources.requests.memory", "128Mi")
        if not isinstance(nested(values, f"{prefix}.extraEnv"), list):
            errors.append(f"AR-030 values.yaml {prefix}.extraEnv must be a list")
    require_nested(values, "router.service.targetPort", 8080)
    if not isinstance(nested(values, "router.config"), dict):
        errors.append("AR-030 values.yaml router.config must be a mapping")
    require_nested(values, "router.serviceAccountName", "")
    require_nested(values, "router.rbac.create", False)
    require_nested(values, "volcano.scheduler.enabled", False)
    require_nested(values, "volcano.scheduler.replicas", 1)
    require_nested(values, "volcano.scheduler.image.repository", "ghcr.io/volcano-sh/vc-agent-scheduler")
    require_nested(values, "volcano.scheduler.image.pullPolicy", "IfNotPresent")
    require_nested(values, "volcano.scheduler.image.tag", "latest")

    template_files = sorted(
        p for p in templates_root.rglob("*")
        if p.is_file() and p.suffix.lower() in {".yaml", ".yml", ".tpl"}
    )
    if not template_files:
        errors.append("AR-030 must include Helm template files under manifests/charts/base/templates")
    template_texts = {
        p: p.read_text(encoding="utf-8", errors="replace")
        for p in template_files
    }
    templates_text = "\n".join(template_texts.values())

    if "kind: Deployment" not in templates_text:
        errors.append("AR-030 templates must define Kubernetes Deployments")
    if "kind: Service" not in templates_text:
        errors.append("AR-030 templates must define Kubernetes Services")
    for token in [
        "workloadmanager",
        ".Values.workloadmanager.replicas",
        ".Values.workloadmanager.image.repository",
        ".Values.workloadmanager.image.tag",
        ".Values.workloadmanager.image.pullPolicy",
        ".Values.workloadmanager.service.port",
        ".Values.workloadmanager.service.type",
        "serviceAccountName",
        "imagePullSecrets",
        "AGENTCUBE_NAMESPACE",
        "fieldRef",
        "metadata.namespace",
        "REDIS_ADDR",
        "REDIS_PASSWORD",
        ".Values.redis.addr",
        ".Values.redis.password",
        ".Values.workloadmanager.extraEnv",
        "--port={{",
        "--runtime-class-name=",
        "resources:",
        "livenessProbe:",
        "readinessProbe:",
        "/health",
    ]:
        require_token("workloadmanager template", templates_text, token)
    for token in [
        "agentcube-router",
        ".Values.router.replicas",
        ".Values.router.image.repository",
        ".Values.router.image.tag",
        ".Values.router.image.pullPolicy",
        ".Values.router.service.port",
        ".Values.router.service.targetPort",
        ".Values.router.service.type",
        ".Values.router.serviceAccountName",
        ".Values.router.extraEnv",
        "WORKLOAD_MANAGER_URL",
        "workloadmanager.{{ .Release.Namespace }}.svc.cluster.local",
        ".Values.workloadmanager.service.port",
        "--debug",
        "/health/live",
        "/health/ready",
    ]:
        require_token("router template", templates_text, token)

    for path, text in template_texts.items():
        for token in [
            "kind: ServiceAccount",
            "kind: Role",
            "kind: ClusterRole",
            "kind: RoleBinding",
            "kind: ClusterRoleBinding",
            "rbac.authorization.k8s.io",
        ]:
            if token in text:
                errors.append(
                    "AR-030 must not implement RBAC resources reserved for AR-031: "
                    f"{path.relative_to(workspace)} contains {token}"
                )

    crd_files = sorted(
        p for p in crds_root.rglob("*")
        if p.is_file() and p.suffix.lower() in {".yaml", ".yml"}
    )
    if len(crd_files) < 2:
        errors.append("AR-030 must include AgentRuntime and CodeInterpreter CRD YAML files")
    crd_text = "\n".join(p.read_text(encoding="utf-8", errors="replace") for p in crd_files)
    for token in [
        "kind: CustomResourceDefinition",
        "runtime.agentcube.volcano.sh",
        "v1alpha1",
        "scope: Namespaced",
        "agentruntimes",
        "codeinterpreters",
    ]:
        require_token("CRD manifests", crd_text, token)

    combined = "\n".join([chart_text, values_text, templates_text, crd_text]).lower()
    for token in ["notimplemented", "todo", "placeholder", "stub implementation"]:
        if token in combined:
            errors.append(f"AR-030 Helm chart must not contain placeholder marker: {token}")
    for forbidden in ["dockerfile", "github/workflows", "kind: job"]:
        if forbidden in combined:
            errors.append(f"AR-030 must not include out-of-scope deployment artifact token: {forbidden}")

    return errors


def _validate_ar031_helm_rbac(workspace: Path) -> list[str]:
    errors: list[str] = []
    chart_root = workspace / "manifests/charts/base"
    workload_rbac = chart_root / "templates/rbac/workloadmanager.yaml"
    router_rbac = chart_root / "templates/rbac-router.yaml"
    volcano_scheduler = chart_root / "templates/volcano-agent-scheduler-development.yaml"

    for rel, path in {
        "manifests/charts/base/templates/rbac/workloadmanager.yaml": workload_rbac,
        "manifests/charts/base/templates/rbac-router.yaml": router_rbac,
        "manifests/charts/base/templates/volcano-agent-scheduler-development.yaml": volcano_scheduler,
    }.items():
        if not path.exists():
            errors.append(f"AR-031 must create {rel}")
    if errors:
        return errors

    def require_token(label: str, text: str, token: str) -> None:
        if token not in text:
            errors.append(f"AR-031 {label} missing token: {token}")

    def require_kind(label: str, text: str, kind: str) -> None:
        if not re.search(rf"^\s*kind:\s+{re.escape(kind)}\s*$", text, flags=re.MULTILINE):
            errors.append(f"AR-031 {label} missing Kubernetes kind: {kind}")

    workload_text = workload_rbac.read_text(encoding="utf-8", errors="replace")
    router_text = router_rbac.read_text(encoding="utf-8", errors="replace")
    volcano_text = volcano_scheduler.read_text(encoding="utf-8", errors="replace")

    for kind in ["ServiceAccount", "ClusterRole", "ClusterRoleBinding"]:
        require_kind("workloadmanager RBAC", workload_text, kind)
    for token in [
        "name: workloadmanager",
        "namespace: {{ .Release.Namespace }}",
        "rbac.authorization.k8s.io/v1",
        "roleRef:",
        "subjects:",
        "kind: ClusterRole",
        "kind: ServiceAccount",
        "agents.x-k8s.io",
        "sandboxes",
        "extensions.agents.x-k8s.io",
        "sandboxclaims",
        "sandboxtemplates",
        "sandboxwarmpools",
        "sandboxwarmpools/status",
        "runtime.agentcube.volcano.sh",
        "codeinterpreters",
        "codeinterpreters/status",
        "codeinterpreters/finalizers",
        "agentruntimes",
        "agentruntimes/status",
        "pods",
        "authentication.k8s.io",
        "tokenreviews",
        "secrets",
        "\"get\"",
        "\"list\"",
        "\"watch\"",
        "\"create\"",
        "\"update\"",
        "\"patch\"",
        "\"delete\"",
    ]:
        require_token("workloadmanager RBAC", workload_text, token)

    for kind in ["ServiceAccount", "Role", "RoleBinding"]:
        require_kind("router RBAC", router_text, kind)
    for token in [
        ".Values.router.rbac.create",
        ".Values.router.serviceAccountName",
        "default \"agentcube-router\"",
        "namespace: {{ .Release.Namespace }}",
        "rbac.authorization.k8s.io/v1",
        "roleRef:",
        "subjects:",
        "resources: [\"secrets\"]",
        "\"get\"",
        "\"list\"",
        "\"watch\"",
        "\"create\"",
        "\"update\"",
        "\"patch\"",
        "\"delete\"",
        "{{- end",
    ]:
        require_token("router RBAC", router_text, token)

    for kind in [
        "ServiceAccount",
        "ConfigMap",
        "ClusterRole",
        "ClusterRoleBinding",
        "Service",
        "Deployment",
    ]:
        require_kind("Volcano scheduler template", volcano_text, kind)
    for token in [
        ".Values.volcano.scheduler.enabled",
        "volcano-agent-scheduler",
        "volcano-agent-scheduler-configmap",
        "agent-scheduler.conf",
        "actions: \"allocate\"",
        "predicates",
        "nodeorder",
        "volcano-agent-scheduler-role",
        "prometheus.io/scrape",
        ".Values.volcano.scheduler.replicas",
        ".Values.volcano.scheduler.image.repository",
        ".Values.volcano.scheduler.image.tag",
        ".Values.volcano.scheduler.image.pullPolicy",
        "--scheduler-name=agent-scheduler",
        "securityContext",
        "volumeMounts",
        "emptyDir",
        "customresourcedefinitions",
        "events",
        "pods",
        "pods/status",
        "pods/binding",
        "persistentvolumeclaims",
        "persistentvolumes",
        "nodes",
        "priorityclasses",
        "podgroups",
        "leases",
        "resourceclaims",
        "resourceclaims/status",
        "nodeshards",
    ]:
        require_token("Volcano scheduler template", volcano_text, token)
    if (
        "serviceAccount: volcano-agent-scheduler" not in volcano_text
        and "serviceAccountName: volcano-agent-scheduler" not in volcano_text
    ):
        errors.append("AR-031 Volcano scheduler template must bind pods to ServiceAccount volcano-agent-scheduler")

    combined = "\n".join([workload_text, router_text, volcano_text]).lower()
    for token in ["notimplemented", "todo", "placeholder", "stub implementation"]:
        if token in combined:
            errors.append(f"AR-031 RBAC templates must not contain placeholder marker: {token}")
    for forbidden in ["dockerfile", "github/workflows", "kind: job"]:
        if forbidden in combined:
            errors.append(f"AR-031 must not include out-of-scope deployment artifact token: {forbidden}")

    return errors


def _validate_ar032_dockerfiles(workspace: Path) -> list[str]:
    errors: list[str] = []
    docker_root = workspace / "docker"
    workload = docker_root / "Dockerfile"
    router = docker_root / "Dockerfile.router"
    picod = docker_root / "Dockerfile.picod"

    for rel, path in {
        "docker/Dockerfile": workload,
        "docker/Dockerfile.router": router,
        "docker/Dockerfile.picod": picod,
    }.items():
        if not path.exists():
            errors.append(f"AR-032 must create {rel}")
    if errors:
        return errors

    def require_token(label: str, text: str, token: str) -> None:
        if token not in text:
            errors.append(f"AR-032 {label} missing token: {token}")

    def require_from_count(label: str, text: str) -> None:
        if len(re.findall(r"^\s*FROM\s+", text, flags=re.MULTILINE | re.IGNORECASE)) < 2:
            errors.append(f"AR-032 {label} must be a multi-stage Dockerfile with at least two FROM instructions")

    workload_text = workload.read_text(encoding="utf-8", errors="replace")
    router_text = router.read_text(encoding="utf-8", errors="replace")
    picod_text = picod.read_text(encoding="utf-8", errors="replace")

    for label, text in {
        "workloadmanager Dockerfile": workload_text,
        "router Dockerfile": router_text,
        "picod Dockerfile": picod_text,
    }.items():
        require_from_count(label, text)
        for token in [
            "ARG TARGETOS=linux",
            "ARG TARGETARCH",
            "go mod download",
            "--mount=type=cache,target=/go/pkg/mod",
            "--mount=type=cache,target=/root/.cache/go-build",
            "CGO_ENABLED=0",
            "GOOS=${TARGETOS}",
            "GOARCH=${TARGETARCH}",
            "go build",
            "-ldflags=\"-s -w\"",
        ]:
            require_token(label, text, token)

    for token in [
        "FROM golang:1.24.9-alpine AS builder",
        "WORKDIR /workspace",
        "COPY go.mod go.sum ./",
        "COPY cmd/ cmd/",
        "COPY pkg/ pkg/",
        "-o workloadmanager",
        "./cmd/workload-manager",
        "FROM alpine:3.19",
        "apk --no-cache add ca-certificates",
        "WORKDIR /app",
        "COPY --from=builder /workspace/workloadmanager .",
        "adduser -D -u 1000 apiserver",
        "USER apiserver",
        "EXPOSE 8080",
        "ENTRYPOINT [\"/app/workloadmanager\"]",
        "CMD [\"--port=8080\"]",
    ]:
        require_token("workloadmanager Dockerfile", workload_text, token)

    for token in [
        "FROM golang:1.24.9-alpine AS builder",
        "WORKDIR /workspace",
        "COPY go.mod go.sum ./",
        "COPY cmd/ cmd/",
        "COPY pkg/ pkg/",
        "COPY client-go/ client-go/",
        "-o agentcube-router",
        "./cmd/router",
        "FROM alpine:3.19",
        "apk --no-cache add ca-certificates",
        "WORKDIR /app",
        "COPY --from=builder /workspace/agentcube-router .",
        "adduser -D -u 1000 router",
        "USER router",
        "EXPOSE 8080",
        "ENTRYPOINT [\"/app/agentcube-router\"]",
        "CMD [\"--port=8080\", \"--debug\"]",
    ]:
        require_token("router Dockerfile", router_text, token)

    for token in [
        "FROM golang:1.24.4 AS builder",
        "WORKDIR /app",
        "COPY go.mod go.sum ./",
        "COPY . .",
        "-o picod",
        "./cmd/picod",
        "FROM ubuntu:24.04",
        "apt-get update",
        "apt-get install -y python3",
        "WORKDIR /root/",
        "COPY --from=builder /app/picod .",
        "ENTRYPOINT [\"./picod\"]",
    ]:
        require_token("picod Dockerfile", picod_text, token)

    combined = "\n".join([workload_text, router_text, picod_text]).lower()
    for token in ["notimplemented", "todo", "placeholder", "stub implementation"]:
        if token in combined:
            errors.append(f"AR-032 Dockerfiles must not contain placeholder marker: {token}")
    for forbidden in ["kind: deployment", "apiVersion:", "github/workflows", "makefile"]:
        if forbidden.lower() in combined:
            errors.append(f"AR-032 must not include out-of-scope artifact token: {forbidden}")

    return errors


def _validate_ar033_makefile(workspace: Path) -> list[str]:
    errors: list[str] = []
    makefile = workspace / "Makefile"
    if not makefile.exists():
        return ["AR-033 must create project-root Makefile"]
    if (workspace / "root/Makefile").exists():
        errors.append("AR-033 must not create root/Makefile; Makefile belongs at repository root")

    text = makefile.read_text(encoding="utf-8", errors="replace")

    def require_token(label: str, token: str) -> None:
        if token not in text:
            errors.append(f"AR-033 Makefile missing {label}: {token}")

    def require_target(target: str) -> None:
        if not re.search(rf"^{re.escape(target)}\s*:", text, flags=re.MULTILINE):
            errors.append(f"AR-033 Makefile missing target: {target}")

    for token in [
        "HUB ?= ghcr.io/volcano-sh",
        "TAG ?= latest",
        "PROJECT_DIR :=",
        "go env GOBIN",
        "CONTAINER_TOOL ?= docker",
        "SHELL = /usr/bin/env bash -o pipefail",
        ".SHELLFLAGS = -ec",
        "WORKLOAD_MANAGER_IMAGE ?= workloadmanager:latest",
        "ROUTER_IMAGE ?= agentcube-router:latest",
        "PICOD_IMAGE ?= picod:latest",
        "IMAGE_REGISTRY ?= \"\"",
        "LOCALBIN ?= $(shell pwd)/bin",
        "CONTROLLER_GEN ?= $(LOCALBIN)/controller-gen",
        "GOLANGCI_LINT ?= $(LOCALBIN)/golangci-lint",
        "CONTROLLER_TOOLS_VERSION ?= v0.17.2",
        "GOLANGCI_LINT_VERSION ?= v1.64.1",
        "E2E_CLUSTER_NAME ?= agentcube-e2e",
        "AGENT_SANDBOX_REPO ?= https://github.com/kubernetes-sigs/agent-sandbox.git",
        "AGENT_SANDBOX_VERSION ?= main",
    ]:
        require_token("variable", token)

    for target in [
        "all",
        "help",
        "gen-crd",
        "generate",
        "gen-client",
        "gen-all",
        "gen-check",
        "build",
        "build-agentd",
        "build-router",
        "build-all",
        "run",
        "run-local",
        "run-router",
        "clean",
        "deps",
        "update-deps",
        "test",
        "fmt",
        "vet",
        "lint",
        "gen-copyright",
        "install",
        "docker-build",
        "docker-buildx",
        "docker-buildx-push",
        "docker-push",
        "kind-load",
        "docker-build-router",
        "docker-buildx-router",
        "docker-buildx-push-router",
        "docker-push-router",
        "kind-load-router",
        "docker-build-picod",
        "docker-buildx-picod",
        "docker-buildx-push-picod",
        "docker-push-picod",
        "controller-gen",
        "golangci-lint",
        "e2e",
        "e2e-clean",
        "build-python-sdk",
    ]:
        require_target(target)

    for token in [
        "all: build",
        "gen-crd: controller-gen",
        "generate: controller-gen gen-crd",
        "gen-all: generate gen-client",
        "gen-check: gen-all",
        "build: generate",
        "build-agentd: generate",
        "build-router: generate",
        "build-all: build build-agentd build-router",
        "install: build",
        "docker-push: docker-build",
        "docker-push-router: docker-build-router",
        "docker-push-picod: docker-build-picod",
        "controller-gen: $(CONTROLLER_GEN)",
        "golangci-lint: $(GOLANGCI_LINT)",
        "awk",
        "$(CONTROLLER_GEN) crd paths=\"./pkg/apis/runtime/v1alpha1/...\"",
        "output:crd:artifacts:config=manifests/charts/base/crds",
        "$(CONTROLLER_GEN) object:headerFile=\"hack/boilerplate.go.txt\" paths=\"./pkg/apis/...\"",
        "go mod tidy",
        "bash hack/update-codegen.sh",
        "git diff --exit-code",
        "go build -o bin/workloadmanager ./cmd/workload-manager",
        "go build -o bin/agentd ./cmd/agentd",
        "go build -o bin/agentcube-router ./cmd/router",
        "go run ./cmd/workload-manager/main.go",
        "--kubeconfig=${HOME}/.kube/config",
        "go run ./cmd/router/main.go",
        "rm -rf bin/",
        "go mod download",
        "go get -u ./...",
        "go test -v ./...",
        "go fmt ./...",
        "go vet ./...",
        "$(GOLANGCI_LINT) run ./...",
        "hack/update-copyright.sh",
        "sudo cp bin/workloadmanager /usr/local/bin/",
        "docker build -f docker/Dockerfile -t $(WORKLOAD_MANAGER_IMAGE) .",
        "docker buildx build -f docker/Dockerfile --platform linux/amd64,linux/arm64",
        "docker tag $(WORKLOAD_MANAGER_IMAGE) $(IMAGE_REGISTRY)/$(WORKLOAD_MANAGER_IMAGE)",
        "docker push $(IMAGE_REGISTRY)/$(WORKLOAD_MANAGER_IMAGE)",
        "kind load docker-image $(WORKLOAD_MANAGER_IMAGE)",
        "docker build -f docker/Dockerfile.router -t $(ROUTER_IMAGE) .",
        "docker buildx build -f docker/Dockerfile.router --platform linux/amd64,linux/arm64",
        "docker tag $(ROUTER_IMAGE) $(IMAGE_REGISTRY)/$(ROUTER_IMAGE)",
        "docker push $(IMAGE_REGISTRY)/$(ROUTER_IMAGE)",
        "kind load docker-image $(ROUTER_IMAGE)",
        "docker build -f docker/Dockerfile.picod -t $(PICOD_IMAGE) .",
        "docker buildx build -f docker/Dockerfile.picod --platform linux/amd64,linux/arm64",
        "docker tag $(PICOD_IMAGE) $(IMAGE_REGISTRY)/$(PICOD_IMAGE)",
        "docker push $(IMAGE_REGISTRY)/$(PICOD_IMAGE)",
        "define go-install-tool",
        "go install $${package}",
        "ln -sf $(1)-$(3) $(1)",
        "./test/e2e/run_e2e.sh",
        "kind delete cluster --name $(E2E_CLUSTER_NAME)",
        "rm -rf /tmp/agent-sandbox",
        "cp LICENSE sdk-python/LICENSE",
        "cd sdk-python && python3 -m build",
        "rm -f sdk-python/LICENSE",
    ]:
        require_token("command", token)

    combined = text.lower()
    for token in ["notimplemented", "todo", "placeholder", "stub implementation"]:
        if token in combined:
            errors.append(f"AR-033 Makefile must not contain placeholder marker: {token}")
    for forbidden in ["dockerfile\n", "apiVersion:", "kind: deployment", "github/workflows"]:
        if forbidden.lower() in combined:
            errors.append(f"AR-033 must not include out-of-scope artifact token: {forbidden}")

    return errors


def _validate_ar034_github_workflows(workspace: Path) -> list[str]:
    errors: list[str] = []
    workflows_root = workspace / ".github/workflows"
    required = {
        "main.yml": [
            "name: Agentcube CI Workflow", "pull_request:", "main", "release-*",
            "docker/setup-buildx-action", "docker --version", "docker buildx version", "make docker-build",
        ],
        "e2e.yml": [
            "name: Agentcube E2E Tests", "pull_request:", "ubuntu-22.04", "actions/setup-go@v5",
            "go-version: \"1.23\"", "helm/kind-action@v1", "version: v0.30.0",
            "cluster_name: agentcube-e2e", "install_only: true", "ARTIFACTS_PATH",
            "make e2e", "actions/upload-artifact@v4", "make e2e-clean", "if: always",
        ],
        "lint.yml": [
            "name: Lint", "dorny/paths-filter@v3", "'**/*.go'", "'go.mod'", "'go.sum'",
            "'.golangci.yml'", "'.github/workflows/lint.yml'", "actions/setup-go@v5",
            "go-version: \"1.24\"", "make lint",
        ],
        "python-sdk-tests.yml": [
            "name: Python SDK Tests", "pull_request:", "merge_group:", "working-directory: sdk-python",
            "dorny/paths-filter@v3", "'sdk-python/**'", "actions/setup-python@v5",
            "python-version: \"3.12\"", "pip install pytest", "pip install -e .",
            "python -m pytest tests/ -v",
        ],
        "python-lint.yml": [
            "name: Python Lint", "pull_request:", "dorny/paths-filter@v3", "\"cmd/cli/**\"",
            "\"sdk-python/**\"", "\"example/**\"", "\"test/**/*.py\"", "\"pyproject.toml\"",
            "actions/setup-python@v4", "python-version: \"3.10\"", "python3 -m pip install ruff",
            "python3 -m ruff check . --config pyproject.toml",
        ],
        "test-coverage.yml": [
            "name: Test Coverage", "pull_request:", "merge_group:", "workflow_call:", "CODECOV_TOKEN",
            "dorny/paths-filter@v3", "jlumbroso/free-disk-space@v1.3.1", "actions/setup-go@v5",
            "go-version: \"1.24\"", "go test -race -v -coverprofile=coverage.out -coverpkg=./pkg/... ./pkg/...",
            "codecov/codecov-action@v4", "secrets.CODECOV_TOKEN", "actions/upload-artifact@v4", "go-coverage",
        ],
        "codegen-check.yml": [
            "name: Codegen Check", "pull_request:", "dorny/paths-filter@v3", "'pkg/apis/**'",
            "'hack/**'", "'.github/workflows/**'", "'Makefile'", "actions/setup-go@v5",
            "go-version: \"1.24.4\"", "make gen-check",
        ],
        "copyright-check.yml": [
            "name: Copyright Check", "pull_request:", "dorny/paths-filter@v3", "copyright:",
            "'!**/*.md'", "'!docs/**'", "sudo apt-get update && sudo apt-get install -y moreutils",
            "make gen-copyright", "git diff --exit-code",
        ],
        "codespell.yml": [
            "name: Codespell", "pull_request:", "pyproject.toml", "package-lock.json", "package.json",
            "pip install codespell", "codespell", "--check-filenames", "--skip", "--ignore-words-list fo,nam,te,notin,NotIn",
            "Restore backed up files",
        ],
        "build-push-release.yml": [
            "name: Build and Push Release Images", "push:", "branches:", "tags:", "\"v*.*.*\"",
            "actions/checkout@v3", "actions/setup-go@v4", "go-version: '1.24.4'",
            "docker/setup-buildx-action@v2", "docker/login-action@v3", "ghcr.io",
            "secrets.GITHUB_TOKEN", "github.ref_type", "TAG=latest",
            "IMAGE_REGISTRY: ghcr.io/${{ github.repository_owner }}", "make docker-buildx-push",
            "make docker-buildx-push-router", "make docker-buildx-push-picod",
        ],
        "dify-plugin-publish.yml": [
            "name: Dify Plugin Publish", "dify-plugin/v*", "wget", "dify-plugin-linux-amd64",
            "Install yq", "working-directory: integrations/dify-plugin", "manifest.yaml",
            "plugin package", "secrets.PLUGIN_ACTION", "langgenius/dify-plugins", "gh pr create",
            "GH_TOKEN",
        ],
        "workflows-approve.yml": [
            "name: Approve Workflows", "pull_request_target:", "labeled", "synchronize",
            "release-**", "actions: write", "actions/github-script@v7", "ok-to-test",
            "action_required", "approveWorkflowRun", "secrets.GITHUB_TOKEN",
        ],
    }

    if not workflows_root.exists():
        return ["AR-034 must create .github/workflows"]

    workflow_files = sorted(
        p.name for p in workflows_root.iterdir()
        if p.is_file() and p.suffix.lower() in {".yml", ".yaml"}
    )
    if len(workflow_files) < len(required):
        errors.append(f"AR-034 must create at least {len(required)} workflow files, found {len(workflow_files)}")
    for name, tokens in required.items():
        path = workflows_root / name
        if not path.exists():
            errors.append(f"AR-034 must create .github/workflows/{name}")
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for token in tokens:
            if token not in text:
                errors.append(f"AR-034 {name} missing token: {token}")
        lower = text.lower()
        for token in ["notimplemented", "todo", "placeholder", "stub implementation"]:
            if token in lower:
                errors.append(f"AR-034 {name} must not contain placeholder marker: {token}")

    allowed_non_workflow = {
        ".github/copilot-instructions.md",
        ".github/PULL_REQUEST_TEMPLATE.md",
        ".github/ISSUE_TEMPLATE/question.md",
        ".github/ISSUE_TEMPLATE/bug-report.md",
        ".github/ISSUE_TEMPLATE/good-first.md",
        ".github/ISSUE_TEMPLATE/enhancement.md",
    }
    misplaced = []
    if (workspace / ".github").exists():
        for p in (workspace / ".github").rglob("*"):
            rel = str(p.relative_to(workspace))
            if (
                p.is_file()
                and rel.startswith(".github/")
                and not rel.startswith(".github/workflows/")
                and rel not in allowed_non_workflow
            ):
                misplaced.append(p)
    if misplaced:
        errors.append(
            "AR-034 must not create unexpected non-workflow GitHub files: "
            + ", ".join(str(p.relative_to(workspace)) for p in misplaced[:8])
        )

    return errors


def _validate_ar035_client_go(workspace: Path) -> list[str]:
    errors: list[str] = []
    root = workspace / "client-go"
    required = {
        "clientset/versioned/clientset.go": [
            "Code generated by client-gen. DO NOT EDIT.",
            "type Interface interface",
            "Discovery() discovery.DiscoveryInterface",
            "RuntimeV1alpha1() runtimev1alpha1.RuntimeV1alpha1Interface",
            "type Clientset struct",
            "runtimeV1alpha1 *runtimev1alpha1.RuntimeV1alpha1Client",
            "func NewForConfig(c *rest.Config) (*Clientset, error)",
            "func NewForConfigAndClient(c *rest.Config, httpClient *http.Client) (*Clientset, error)",
            "flowcontrol.NewTokenBucketRateLimiter",
            "runtimev1alpha1.NewForConfigAndClient",
            "discovery.NewDiscoveryClientForConfigAndClient",
            "func NewForConfigOrDie(c *rest.Config) *Clientset",
            "func New(c rest.Interface) *Clientset",
        ],
        "clientset/versioned/scheme/doc.go": [
            "Code generated by client-gen. DO NOT EDIT.",
            "automatically generated clientset",
            "package scheme",
        ],
        "clientset/versioned/scheme/register.go": [
            "Code generated by client-gen. DO NOT EDIT.",
            "var Scheme = runtime.NewScheme()",
            "var Codecs = serializer.NewCodecFactory(Scheme)",
            "var ParameterCodec = runtime.NewParameterCodec(Scheme)",
            "runtimev1alpha1.AddToScheme",
            "var AddToScheme = localSchemeBuilder.AddToScheme",
            "v1.AddToGroupVersion(Scheme, schema.GroupVersion{Version: \"v1\"})",
            "utilruntime.Must(AddToScheme(Scheme))",
        ],
        "clientset/versioned/fake/doc.go": [
            "Code generated by client-gen. DO NOT EDIT.",
            "automatically generated fake clientset",
            "package fake",
        ],
        "clientset/versioned/fake/register.go": [
            "Code generated by client-gen. DO NOT EDIT.",
            "var scheme = runtime.NewScheme()",
            "var codecs = serializer.NewCodecFactory(scheme)",
            "runtimev1alpha1.AddToScheme",
            "var AddToScheme = localSchemeBuilder.AddToScheme",
            "v1.AddToGroupVersion(scheme, schema.GroupVersion{Version: \"v1\"})",
            "utilruntime.Must(AddToScheme(scheme))",
        ],
        "clientset/versioned/fake/clientset_generated.go": [
            "Code generated by client-gen. DO NOT EDIT.",
            "func NewSimpleClientset(objects ...runtime.Object) *Clientset",
            "testing.NewObjectTracker(scheme, codecs.UniversalDecoder())",
            "testing.ObjectReaction(o)",
            "cs.AddWatchReactor(\"*\", func(action testing.Action)",
            "fakediscovery.FakeDiscovery",
            "type Clientset struct",
            "testing.Fake",
            "Tracker() testing.ObjectTracker",
            "RuntimeV1alpha1() runtimev1alpha1.RuntimeV1alpha1Interface",
            "fakeruntimev1alpha1.FakeRuntimeV1alpha1",
        ],
        "clientset/versioned/typed/runtime/v1alpha1/doc.go": [
            "Code generated by client-gen. DO NOT EDIT.",
            "automatically generated typed clients",
            "package v1alpha1",
        ],
        "clientset/versioned/typed/runtime/v1alpha1/runtime_client.go": [
            "Code generated by client-gen. DO NOT EDIT.",
            "type RuntimeV1alpha1Interface interface",
            "RESTClient() rest.Interface",
            "AgentRuntimesGetter",
            "CodeInterpretersGetter",
            "type RuntimeV1alpha1Client struct",
            "func (c *RuntimeV1alpha1Client) AgentRuntimes(namespace string) AgentRuntimeInterface",
            "func (c *RuntimeV1alpha1Client) CodeInterpreters(namespace string) CodeInterpreterInterface",
            "func NewForConfig(c *rest.Config) (*RuntimeV1alpha1Client, error)",
            "func NewForConfigAndClient(c *rest.Config, h *http.Client) (*RuntimeV1alpha1Client, error)",
            "func setConfigDefaults(config *rest.Config)",
            "runtimev1alpha1.SchemeGroupVersion",
            "config.APIPath = \"/apis\"",
            "rest.CodecFactoryForGeneratedClient(scheme.Scheme, scheme.Codecs).WithoutConversion()",
        ],
        "clientset/versioned/typed/runtime/v1alpha1/agentruntime.go": [
            "Code generated by client-gen. DO NOT EDIT.",
            "type AgentRuntimesGetter interface",
            "AgentRuntimes(namespace string) AgentRuntimeInterface",
            "type AgentRuntimeInterface interface",
            "Create(ctx context.Context, agentRuntime *runtimev1alpha1.AgentRuntime, opts v1.CreateOptions)",
            "UpdateStatus(ctx context.Context, agentRuntime *runtimev1alpha1.AgentRuntime, opts v1.UpdateOptions)",
            "DeleteCollection(ctx context.Context, opts v1.DeleteOptions, listOpts v1.ListOptions)",
            "Watch(ctx context.Context, opts v1.ListOptions) (watch.Interface, error)",
            "Patch(ctx context.Context, name string, pt types.PatchType, data []byte, opts v1.PatchOptions",
            "AgentRuntimeExpansion",
            "gentype.NewClientWithList[*runtimev1alpha1.AgentRuntime, *runtimev1alpha1.AgentRuntimeList]",
            "\"agentruntimes\"",
            "func() *runtimev1alpha1.AgentRuntime { return &runtimev1alpha1.AgentRuntime{} }",
            "func() *runtimev1alpha1.AgentRuntimeList { return &runtimev1alpha1.AgentRuntimeList{} }",
        ],
        "clientset/versioned/typed/runtime/v1alpha1/codeinterpreter.go": [
            "Code generated by client-gen. DO NOT EDIT.",
            "type CodeInterpretersGetter interface",
            "CodeInterpreters(namespace string) CodeInterpreterInterface",
            "type CodeInterpreterInterface interface",
            "Create(ctx context.Context, codeInterpreter *runtimev1alpha1.CodeInterpreter, opts v1.CreateOptions)",
            "UpdateStatus(ctx context.Context, codeInterpreter *runtimev1alpha1.CodeInterpreter, opts v1.UpdateOptions)",
            "DeleteCollection(ctx context.Context, opts v1.DeleteOptions, listOpts v1.ListOptions)",
            "Watch(ctx context.Context, opts v1.ListOptions) (watch.Interface, error)",
            "Patch(ctx context.Context, name string, pt types.PatchType, data []byte, opts v1.PatchOptions",
            "CodeInterpreterExpansion",
            "gentype.NewClientWithList[*runtimev1alpha1.CodeInterpreter, *runtimev1alpha1.CodeInterpreterList]",
            "\"codeinterpreters\"",
            "func() *runtimev1alpha1.CodeInterpreter { return &runtimev1alpha1.CodeInterpreter{} }",
            "func() *runtimev1alpha1.CodeInterpreterList { return &runtimev1alpha1.CodeInterpreterList{} }",
        ],
        "clientset/versioned/typed/runtime/v1alpha1/generated_expansion.go": [
            "Code generated by client-gen. DO NOT EDIT.",
            "type AgentRuntimeExpansion interface{}",
            "type CodeInterpreterExpansion interface{}",
        ],
        "clientset/versioned/typed/runtime/v1alpha1/fake/doc.go": [
            "Code generated by client-gen. DO NOT EDIT.",
            "Package fake has the automatically generated clients",
            "package fake",
        ],
        "clientset/versioned/typed/runtime/v1alpha1/fake/fake_runtime_client.go": [
            "Code generated by client-gen. DO NOT EDIT.",
            "type FakeRuntimeV1alpha1 struct",
            "*testing.Fake",
            "AgentRuntimes(namespace string) v1alpha1.AgentRuntimeInterface",
            "return newFakeAgentRuntimes(c, namespace)",
            "CodeInterpreters(namespace string) v1alpha1.CodeInterpreterInterface",
            "return newFakeCodeInterpreters(c, namespace)",
            "RESTClient() rest.Interface",
        ],
        "clientset/versioned/typed/runtime/v1alpha1/fake/fake_agentruntime.go": [
            "Code generated by client-gen. DO NOT EDIT.",
            "type fakeAgentRuntimes struct",
            "gentype.FakeClientWithList[*v1alpha1.AgentRuntime, *v1alpha1.AgentRuntimeList]",
            "func newFakeAgentRuntimes(fake *FakeRuntimeV1alpha1, namespace string) runtimev1alpha1.AgentRuntimeInterface",
            "v1alpha1.SchemeGroupVersion.WithResource(\"agentruntimes\")",
            "v1alpha1.SchemeGroupVersion.WithKind(\"AgentRuntime\")",
            "gentype.ToPointerSlice(list.Items)",
            "gentype.FromPointerSlice(items)",
        ],
        "clientset/versioned/typed/runtime/v1alpha1/fake/fake_codeinterpreter.go": [
            "Code generated by client-gen. DO NOT EDIT.",
            "type fakeCodeInterpreters struct",
            "gentype.FakeClientWithList[*v1alpha1.CodeInterpreter, *v1alpha1.CodeInterpreterList]",
            "func newFakeCodeInterpreters(fake *FakeRuntimeV1alpha1, namespace string) runtimev1alpha1.CodeInterpreterInterface",
            "v1alpha1.SchemeGroupVersion.WithResource(\"codeinterpreters\")",
            "v1alpha1.SchemeGroupVersion.WithKind(\"CodeInterpreter\")",
            "gentype.ToPointerSlice(list.Items)",
            "gentype.FromPointerSlice(items)",
        ],
        "informers/externalversions/factory.go": [
            "Code generated by informer-gen. DO NOT EDIT.",
            "type SharedInformerOption func(*sharedInformerFactory) *sharedInformerFactory",
            "type sharedInformerFactory struct",
            "informers map[reflect.Type]cache.SharedIndexInformer",
            "startedInformers map[reflect.Type]bool",
            "func WithCustomResyncConfig(resyncConfig map[v1.Object]time.Duration) SharedInformerOption",
            "func WithTweakListOptions(tweakListOptions internalinterfaces.TweakListOptionsFunc) SharedInformerOption",
            "func WithNamespace(namespace string) SharedInformerOption",
            "func WithTransform(transform cache.TransformFunc) SharedInformerOption",
            "func NewSharedInformerFactory(client versioned.Interface, defaultResync time.Duration) SharedInformerFactory",
            "func NewSharedInformerFactoryWithOptions(client versioned.Interface, defaultResync time.Duration, options ...SharedInformerOption) SharedInformerFactory",
            "func (f *sharedInformerFactory) Start(stopCh <-chan struct{})",
            "func (f *sharedInformerFactory) Shutdown()",
            "func (f *sharedInformerFactory) WaitForCacheSync(stopCh <-chan struct{}) map[reflect.Type]bool",
            "func (f *sharedInformerFactory) InformerFor(obj runtime.Object, newFunc internalinterfaces.NewInformerFunc) cache.SharedIndexInformer",
            "Runtime() externalversionsruntime.Interface",
        ],
        "informers/externalversions/generic.go": [
            "Code generated by informer-gen. DO NOT EDIT.",
            "type GenericInformer interface",
            "Informer() cache.SharedIndexInformer",
            "Lister() cache.GenericLister",
            "func (f *sharedInformerFactory) ForResource(resource schema.GroupVersionResource) (GenericInformer, error)",
            "v1alpha1.SchemeGroupVersion.WithResource(\"agentruntimes\")",
            "f.Runtime().V1alpha1().AgentRuntimes().Informer()",
            "v1alpha1.SchemeGroupVersion.WithResource(\"codeinterpreters\")",
            "f.Runtime().V1alpha1().CodeInterpreters().Informer()",
            "fmt.Errorf(\"no informer found for %v\", resource)",
        ],
        "informers/externalversions/internalinterfaces/factory_interfaces.go": [
            "Code generated by informer-gen. DO NOT EDIT.",
            "type NewInformerFunc func(versioned.Interface, time.Duration) cache.SharedIndexInformer",
            "type SharedInformerFactory interface",
            "Start(stopCh <-chan struct{})",
            "InformerFor(obj runtime.Object, newFunc NewInformerFunc) cache.SharedIndexInformer",
            "type TweakListOptionsFunc func(*v1.ListOptions)",
        ],
        "informers/externalversions/runtime/interface.go": [
            "Code generated by informer-gen. DO NOT EDIT.",
            "type Interface interface",
            "V1alpha1() v1alpha1.Interface",
            "type group struct",
            "func New(f internalinterfaces.SharedInformerFactory, namespace string, tweakListOptions internalinterfaces.TweakListOptionsFunc) Interface",
            "func (g *group) V1alpha1() v1alpha1.Interface",
        ],
        "informers/externalversions/runtime/v1alpha1/interface.go": [
            "Code generated by informer-gen. DO NOT EDIT.",
            "type Interface interface",
            "AgentRuntimes() AgentRuntimeInformer",
            "CodeInterpreters() CodeInterpreterInformer",
            "type version struct",
            "func New(f internalinterfaces.SharedInformerFactory, namespace string, tweakListOptions internalinterfaces.TweakListOptionsFunc) Interface",
            "return &agentRuntimeInformer{factory: v.factory, namespace: v.namespace, tweakListOptions: v.tweakListOptions}",
            "return &codeInterpreterInformer{factory: v.factory, namespace: v.namespace, tweakListOptions: v.tweakListOptions}",
        ],
        "informers/externalversions/runtime/v1alpha1/agentruntime.go": [
            "Code generated by informer-gen. DO NOT EDIT.",
            "type AgentRuntimeInformer interface",
            "Informer() cache.SharedIndexInformer",
            "Lister() runtimev1alpha1.AgentRuntimeLister",
            "func NewAgentRuntimeInformer(client versioned.Interface, namespace string, resyncPeriod time.Duration, indexers cache.Indexers) cache.SharedIndexInformer",
            "func NewFilteredAgentRuntimeInformer(client versioned.Interface, namespace string, resyncPeriod time.Duration, indexers cache.Indexers, tweakListOptions internalinterfaces.TweakListOptionsFunc) cache.SharedIndexInformer",
            "cache.NewSharedIndexInformer",
            "client.RuntimeV1alpha1().AgentRuntimes(namespace).List",
            "client.RuntimeV1alpha1().AgentRuntimes(namespace).Watch",
            "ListWithContextFunc",
            "WatchFuncWithContext",
            "runtimev1alpha1.NewAgentRuntimeLister(f.Informer().GetIndexer())",
        ],
        "informers/externalversions/runtime/v1alpha1/codeinterpreter.go": [
            "Code generated by informer-gen. DO NOT EDIT.",
            "type CodeInterpreterInformer interface",
            "Informer() cache.SharedIndexInformer",
            "Lister() runtimev1alpha1.CodeInterpreterLister",
            "func NewCodeInterpreterInformer(client versioned.Interface, namespace string, resyncPeriod time.Duration, indexers cache.Indexers) cache.SharedIndexInformer",
            "func NewFilteredCodeInterpreterInformer(client versioned.Interface, namespace string, resyncPeriod time.Duration, indexers cache.Indexers, tweakListOptions internalinterfaces.TweakListOptionsFunc) cache.SharedIndexInformer",
            "cache.NewSharedIndexInformer",
            "client.RuntimeV1alpha1().CodeInterpreters(namespace).List",
            "client.RuntimeV1alpha1().CodeInterpreters(namespace).Watch",
            "ListWithContextFunc",
            "WatchFuncWithContext",
            "runtimev1alpha1.NewCodeInterpreterLister(f.Informer().GetIndexer())",
        ],
        "listers/runtime/v1alpha1/agentruntime.go": [
            "Code generated by lister-gen. DO NOT EDIT.",
            "type AgentRuntimeLister interface",
            "List(selector labels.Selector) (ret []*runtimev1alpha1.AgentRuntime, err error)",
            "AgentRuntimes(namespace string) AgentRuntimeNamespaceLister",
            "listers.ResourceIndexer[*runtimev1alpha1.AgentRuntime]",
            "func NewAgentRuntimeLister(indexer cache.Indexer) AgentRuntimeLister",
            "runtimev1alpha1.Resource(\"agentruntime\").GroupResource()",
            "listers.NewNamespaced[*runtimev1alpha1.AgentRuntime]",
            "type AgentRuntimeNamespaceLister interface",
            "Get(name string) (*runtimev1alpha1.AgentRuntime, error)",
        ],
        "listers/runtime/v1alpha1/codeinterpreter.go": [
            "Code generated by lister-gen. DO NOT EDIT.",
            "type CodeInterpreterLister interface",
            "List(selector labels.Selector) (ret []*runtimev1alpha1.CodeInterpreter, err error)",
            "CodeInterpreters(namespace string) CodeInterpreterNamespaceLister",
            "listers.ResourceIndexer[*runtimev1alpha1.CodeInterpreter]",
            "func NewCodeInterpreterLister(indexer cache.Indexer) CodeInterpreterLister",
            "runtimev1alpha1.Resource(\"codeinterpreter\").GroupResource()",
            "listers.NewNamespaced[*runtimev1alpha1.CodeInterpreter]",
            "type CodeInterpreterNamespaceLister interface",
            "Get(name string) (*runtimev1alpha1.CodeInterpreter, error)",
        ],
        "listers/runtime/v1alpha1/expansion_generated.go": [
            "Code generated by lister-gen. DO NOT EDIT.",
            "type AgentRuntimeListerExpansion interface{}",
            "type AgentRuntimeNamespaceListerExpansion interface{}",
            "type CodeInterpreterListerExpansion interface{}",
            "type CodeInterpreterNamespaceListerExpansion interface{}",
        ],
    }

    if not root.exists():
        return ["AR-035 must create client-go generated client tree"]

    go_mod_path = workspace / "go.mod"
    if not go_mod_path.exists():
        errors.append("AR-035 must keep a root go.mod with the real AgentCube dependency baseline")
    else:
        go_mod = go_mod_path.read_text(encoding="utf-8", errors="replace")
        if not re.search(r"(?m)^go\s+1\.24\.4\s*$", go_mod):
            errors.append("AR-035 go.mod must use original `go 1.24.4`")
        if not re.search(r"(?m)^toolchain\s+go1\.24\.9\s*$", go_mod):
            errors.append("AR-035 go.mod must use original `toolchain go1.24.9`")
        for dep in ("k8s.io/api", "k8s.io/apimachinery", "k8s.io/client-go"):
            if not re.search(rf"(?m)^\s*{re.escape(dep)}\s+v0\.34\.1(?:\s|$)", go_mod):
                errors.append(f"AR-035 go.mod must require {dep} v0.34.1")
        for dep in ("k8s.io/api", "k8s.io/apimachinery", "k8s.io/client-go"):
            if re.search(rf"(?m)^\s*replace\s+{re.escape(dep)}\b", go_mod):
                errors.append(f"AR-035 must not replace external dependency {dep}")
        if "github.com/volcano-sh/agentcube/pkg/gentype" in go_mod:
            errors.append("AR-035 must not add a local pkg/gentype dependency")

    for forbidden in (workspace / "pkg" / "gentype", root / "k8s.io"):
        if forbidden.exists():
            errors.append(f"AR-035 must not create local replacement dependency path {forbidden.relative_to(workspace)}")

    expected_paths = set(required)
    go_files = sorted(p for p in root.rglob("*.go") if p.is_file())
    actual_paths = {str(p.relative_to(root)) for p in go_files}
    if len(go_files) < len(required):
        errors.append(f"AR-035 must create at least {len(required)} generated Go files, found {len(go_files)}")
    missing = sorted(expected_paths - actual_paths)
    for rel in missing:
        errors.append(f"AR-035 must create client-go/{rel}")
    unexpected = sorted(
        str(p.relative_to(root))
        for p in root.rglob("*")
        if p.is_file() and str(p.relative_to(root)) not in expected_paths
    )
    if unexpected:
        errors.append("AR-035 must not create unexpected files under client-go: " + ", ".join(unexpected[:12]))

    total_loc = 0
    for rel, tokens in required.items():
        path = root / rel
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        total_loc += len(text.splitlines())
        lower = text.lower()
        for token in ["notimplemented", "placeholder", "stub implementation", "panic(\"todo", "panic(\"not implemented"]:
            if token in lower:
                errors.append(f"AR-035 client-go/{rel} must not contain placeholder marker: {token}")
        for token in tokens:
            if token not in text:
                errors.append(f"AR-035 client-go/{rel} missing token: {token}")

    if total_loc < 1200:
        errors.append(f"AR-035 generated client-go LOC is too small: {total_loc} < 1200")

    return errors


def _validate_ar036_dify_plugin(workspace: Path) -> list[str]:
    errors: list[str] = []
    root = workspace / "integrations" / "dify-plugin"
    required = {
        "manifest.yaml": [
            "version: 0.0.2",
            "type: plugin",
            "author: volcano-sh",
            "name: agentcube",
            "icon: icon.png",
            "icon_dark: icon-dark.png",
            "memory: 268435456",
            "provider/agentcube.yaml",
            "language: python",
            'version: "3.12"',
            "entrypoint: main",
            "privacy: PRIVACY.md",
            "repo: https://github.com/volcano-sh/agentcube",
        ],
        "main.py": [
            "from dify_plugin import Plugin, DifyPluginEnv",
            "Plugin(DifyPluginEnv(MAX_REQUEST_TIMEOUT=120))",
            "plugin.run()",
        ],
        "requirements.txt": [
            "dify-plugin>=0.4.2,<0.5.0",
            "agentcube-sdk>=0.0.10",
        ],
        ".difyignore": [
            "__pycache__/",
            "*.py[cod]",
            ".pytest_cache/",
            ".git/",
            "*.difypkg",
        ],
        "README.md": [
            "# Agentcube Dify Plugin",
            "Agentcube Code Interpreter",
            "router_url",
            "workload_manager_url",
            "session_reuse",
        ],
        "GUIDE.md": [
            "# Dify Plugin Development Guide",
            "manifest.yaml",
            "dify-plugin plugin package",
            "PRIVACY.md",
        ],
        "PRIVACY.md": [
            "# Privacy Policy",
            "No Data Collection",
            "Self-Hosted Infrastructure",
            "No data is sent",
        ],
        "provider/agentcube.yaml": [
            "identity:",
            'name: "agentcube"',
            "tools/agentcube-code-interpreter.yaml",
            "extra:",
            "source: provider/agentcube.py",
        ],
        "provider/agentcube.py": [
            "from dify_plugin import ToolProvider",
            "ToolProviderCredentialValidationError",
            "class AgentcubeCodeInterpreterProvider(ToolProvider):",
            "def _validate_credentials(self, credentials: dict[str, Any]) -> None:",
        ],
        "tools/agentcube-code-interpreter.yaml": [
            'name: "agentcube-code-interpreter"',
            "router_url",
            "workload_manager_url",
            "session_reuse",
            "code_interpreter_id",
            "value: python",
            "value: javascript",
            "value: typescript",
            "source: tools/agentcube-code-interpreter.py",
        ],
        "tools/agentcube-code-interpreter.py": [
            "from dify_plugin import Tool",
            "from dify_plugin.entities.tool import ToolInvokeMessage",
            "from agentcube import CodeInterpreterClient",
            "class AgentcubeCodeInterpreterTool(Tool):",
            "def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:",
            "yield self.create_json_message(result)",
            "def execute(",
            "router_url=None",
            "workload_manager_url=None",
            "language=\"python\"",
            "session_reuse=False",
            "CodeInterpreterClient(**client_kwargs)",
            "ci_client.execute_command(command)",
            "ci_client.run_code(language, code)",
            "Either command or code must be provided",
            "ci_client.stop()",
        ],
        "_assets/icon.png": [],
        "_assets/icon-dark.png": [],
    }

    if not root.exists():
        return ["AR-036 must create integrations/dify-plugin"]

    expected_paths = set(required)
    actual_paths = {
        str(p.relative_to(root))
        for p in root.rglob("*")
        if p.is_file() and not any(part in GENERATED_ARTIFACT_DIRS for part in p.relative_to(root).parts)
    }
    missing = sorted(expected_paths - actual_paths)
    for rel in missing:
        errors.append(f"AR-036 must create integrations/dify-plugin/{rel}")

    unexpected = sorted(actual_paths - expected_paths)
    if unexpected:
        errors.append("AR-036 must not create unexpected files under integrations/dify-plugin: " + ", ".join(unexpected[:12]))

    pcap_paths = sorted(
        str(p.relative_to(workspace))
        for p in root.rglob("*")
        if "pcap" in str(p.relative_to(root)).lower()
    )
    if pcap_paths:
        errors.append("AR-036 must not create PCAP analyzer files under Dify plugin: " + ", ".join(pcap_paths[:12]))

    total_text_loc = 0
    for rel, tokens in required.items():
        path = root / rel
        if not path.exists() or rel.startswith("_assets/"):
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        total_text_loc += len(text.splitlines())
        lower = text.lower()
        for token in ["notimplementederror", "stub implementation", "mock implementation"]:
            if token in lower:
                errors.append(f"AR-036 integrations/dify-plugin/{rel} must not contain placeholder marker: {token}")
        for token in tokens:
            if token not in text:
                errors.append(f"AR-036 integrations/dify-plugin/{rel} missing token: {token}")

    for rel in ("main.py", "provider/agentcube.py", "tools/agentcube-code-interpreter.py"):
        path = root / rel
        if not path.exists():
            continue
        try:
            compile(path.read_text(encoding="utf-8", errors="replace"), str(path), "exec")
        except SyntaxError as exc:
            errors.append(f"AR-036 integrations/dify-plugin/{rel} has Python syntax error: {exc.msg} at line {exc.lineno}")

    for rel in ("_assets/icon.png", "_assets/icon-dark.png"):
        path = root / rel
        if not path.exists():
            continue
        data = path.read_bytes()
        if not data.startswith(b"\x89PNG\r\n\x1a\n"):
            errors.append(f"AR-036 integrations/dify-plugin/{rel} must be a valid PNG asset")
        if len(data) < 1000:
            errors.append(f"AR-036 integrations/dify-plugin/{rel} is too small to be the real asset: {len(data)} bytes")

    if total_text_loc < 350:
        errors.append(f"AR-036 Dify plugin text LOC is too small: {total_text_loc} < 350")

    return errors


def _ar036_dify_plugin_file_count(workspace: Path) -> int:
    root = workspace / "integrations" / "dify-plugin"
    required = {
        "manifest.yaml",
        "main.py",
        "requirements.txt",
        ".difyignore",
        "README.md",
        "GUIDE.md",
        "PRIVACY.md",
        "provider/agentcube.yaml",
        "provider/agentcube.py",
        "tools/agentcube-code-interpreter.yaml",
        "tools/agentcube-code-interpreter.py",
        "_assets/icon.png",
        "_assets/icon-dark.png",
    }
    if not root.exists():
        return 0
    actual = {str(p.relative_to(root)) for p in root.rglob("*") if p.is_file()}
    return len(required) if required.issubset(actual) else 0


def _ar037_pcap_analyzer_file_count(workspace: Path) -> int:
    root = workspace / "example" / "pcap-analyzer"
    required = {"pcap_analyzer.py", "requirements.txt", "Dockerfile", "deployment.yaml", "README.md"}
    if not root.exists():
        return 0
    actual = {str(p.relative_to(root)) for p in root.rglob("*") if p.is_file()}
    return len(required) if required.issubset(actual) else 0


def _validate_ar037_pcap_analyzer(workspace: Path) -> list[str]:
    errors: list[str] = []
    root = workspace / "example" / "pcap-analyzer"
    required = {
        "pcap_analyzer.py": [
            "from fastapi import FastAPI, UploadFile, File, Form, HTTPException",
            "from pydantic import BaseModel",
            "from langchain_openai import ChatOpenAI",
            "from langgraph.prebuilt import create_react_agent",
            "from langchain_core.messages import HumanMessage, AIMessage",
            "from agentcube.code_interpreter import CodeInterpreterClient",
            "from agentcube.exceptions import CommandExecutionError",
            'API_BASE_URL = os.environ.get("OPENAI_API_BASE", "https://api.siliconflow.cn/v1")',
            'MODEL_NAME = os.environ.get("OPENAI_MODEL", "Qwen/QwQ-32B")',
            'CODEINTERPRETER_NAME = os.environ.get("CODEINTERPRETER_NAME", "my-interpreter")',
            'SANDBOX_NAMESPACE = os.environ.get("SANDBOX_NAMESPACE", "default")',
            'SANDBOX_WARMUP_SEC = int(os.environ.get("SANDBOX_WARMUP_SEC", "5"))',
            'SERVER_HOST = "0.0.0.0"',
            "SERVER_PORT = 8000",
            "PLANNER_SYSTEM = r",
            "PLANNER_REPAIR_USER = r",
            "REPORTER_SYSTEM = r",
            "class SandboxRunner:",
            "def upload_file(self, local_path: str, remote_path: str) -> bool:",
            "def upload_bytes(self, data: bytes, remote_path: str) -> bool:",
            "def run(self, command: str) -> Dict[str, Any]:",
            "def build_react_agent(llm, system_prompt: str):",
            "def invoke_react_agent(agent, user_text: str) -> str:",
            "def _extract_script(text: str) -> str:",
            "def _normalize_script(script: str) -> str:",
            "def _plan_script(agent, pcap_local_path: str) -> str:",
            "def _repair_script(agent, prev_script: str, results: List[Dict[str, Any]]) -> str:",
            "def _execute_once_in_runner(runner: SandboxRunner, pcap_local_path: str, script: str) -> List[Dict[str, Any]]:",
            "def _analyze_with_retries(",
            "def _report(agent, results: List[Dict[str, Any]]) -> str:",
            "class AnalyzeResponse(BaseModel):",
            'app = FastAPI(title="PCAP Analyzer',
            '@app.on_event("startup")',
            "def on_startup():",
            '@app.post("/analyze", response_model=AnalyzeResponse)',
            "async def analyze_endpoint(",
            'max_retries=int(os.environ.get("PLANNER_MAX_RETRIES", "2"))',
            "return AnalyzeResponse(script=out[\"final_script\"], results=results, report=report)",
            'uvicorn.run(',
        ],
        "requirements.txt": [
            "fastapi==0.120.0",
            "uvicorn==0.38.0",
            "langchain==1.0.2",
            "langchain-openai==1.0.1",
            "langgraph==1.0.1",
            "langgraph-prebuilt==1.0.1",
            "langsmith==0.4.38",
            "paramiko==4.0.0",
            "python-multipart==0.0.20",
        ],
        "Dockerfile": [
            "FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim",
            "WORKDIR /app",
            "COPY example/pcap-analyzer/requirements.txt ./",
            "RUN uv venv",
            "RUN uv pip install -r requirements.txt",
            "COPY sdk-python/agentcube ./agentcube/",
            "COPY example/pcap-analyzer/pcap_analyzer.py ./",
            'ENV PYTHONPATH="/app"',
            "EXPOSE 8000",
            'CMD ["uv", "run", "pcap_analyzer.py"]',
        ],
        "deployment.yaml": [
            "apiVersion: apps/v1",
            "kind: Deployment",
            "name: pcap-analyzer",
            "image: pcap-analyzer:latest",
            "imagePullPolicy: IfNotPresent",
            "containerPort: 8000",
            "cpu: 200m",
            "memory: 100Mi",
            "memory: 1Gi",
            "name: OPENAI_API_KEY",
            "secretKeyRef:",
            "name: pcap-analyzer-secrets",
            "key: openai-api-key",
            "name: OPENAI_API_BASE",
            "https://api.siliconflow.cn/v1",
            "name: OPENAI_MODEL",
            "Qwen/QwQ-32B",
            "name: WORKLOAD_MANAGER_URL",
            "name: ROUTER_URL",
            "name: CODEINTERPRETER_NAME",
            "name: SANDBOX_NAMESPACE",
            "name: SANDBOX_WARMUP_SEC",
            'command: ["uv"]',
            'args: ["run", "pcap_analyzer.py"]',
        ],
        "README.md": [
            "PCAP Analyzer",
            "FastAPI",
            "POST /analyze",
            "Planner Agent",
            "SandboxRunner",
            "Reporter Agent",
            "PLANNER_MAX_RETRIES",
            "docker build",
            "kubectl",
        ],
    }

    if not root.exists():
        return ["AR-037 must create example/pcap-analyzer"]

    expected_paths = set(required)
    actual_paths = {str(p.relative_to(root)) for p in root.rglob("*") if p.is_file()}
    missing = sorted(expected_paths - actual_paths)
    for rel in missing:
        errors.append(f"AR-037 must create example/pcap-analyzer/{rel}")
    unexpected = sorted(actual_paths - expected_paths)
    if unexpected:
        errors.append("AR-037 must not create unexpected files under example/pcap-analyzer: " + ", ".join(unexpected[:12]))

    total_loc = 0
    pcap_py_loc = 0
    for rel, tokens in required.items():
        path = root / rel
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        loc = len(text.splitlines())
        total_loc += loc
        if rel == "pcap_analyzer.py":
            pcap_py_loc = loc
        lower = text.lower()
        for token in ["notimplementederror", "placeholder", "stub implementation", "mock implementation", "todo"]:
            if token in lower:
                errors.append(f"AR-037 example/pcap-analyzer/{rel} must not contain placeholder marker: {token}")
        for token in tokens:
            if token not in text:
                errors.append(f"AR-037 example/pcap-analyzer/{rel} missing token: {token}")

    pcap_py = root / "pcap_analyzer.py"
    if pcap_py.exists():
        try:
            compile(pcap_py.read_text(encoding="utf-8", errors="replace"), str(pcap_py), "exec")
        except SyntaxError as exc:
            errors.append(f"AR-037 example/pcap-analyzer/pcap_analyzer.py has Python syntax error: {exc.msg} at line {exc.lineno}")

    if pcap_py_loc < 500:
        errors.append(f"AR-037 pcap_analyzer.py is too small for the real analyzer: {pcap_py_loc} < 500 LOC")
    if total_loc < 800:
        errors.append(f"AR-037 PCAP analyzer total LOC is too small: {total_loc} < 800")

    return errors


def _validate_ar038_workloadmanager_tests(workspace: Path) -> list[str]:
    errors: list[str] = _validate_workloadmanager_production_complete(
        workspace,
        "AR-038 prerequisite",
    )
    root = workspace / "pkg" / "workloadmanager"
    required = {
        "auth_test.go": [
            "func setupTestServerWithAuth(enableAuth bool) *Server",
            "func TestAuthMiddleware_AuthDisabled(t *testing.T)",
            "func TestAuthMiddleware_InvalidHeaderFormat(t *testing.T)",
            "func TestAuthMiddleware_InvalidServiceAccountFormat(t *testing.T)",
            "func TestValidateServiceAccountToken_CacheHit(t *testing.T)",
            "func TestAuthMiddleware_ServiceAccountParsing(t *testing.T)",
            "func TestValidateServiceAccountToken_CacheBehavior(t *testing.T)",
            "httptest.NewRecorder()",
            "NewTokenCache(100, 5*time.Minute)",
        ],
        "client_cache_test.go": [
            "func createTestJWT(exp int64) string",
            "func TestParseJWTExpiry(t *testing.T)",
            "func TestClientCache_SetAndGet(t *testing.T)",
            "func TestClientCache_Get_ExpiredToken(t *testing.T)",
            "func TestClientCache_Eviction(t *testing.T)",
            "func TestClientCache_LRUBehavior(t *testing.T)",
            "func TestTokenCache_SetAndGet(t *testing.T)",
            "func TestTokenCache_Eviction(t *testing.T)",
            "func TestClientCache_ConcurrentAccess(t *testing.T)",
            "func TestTokenCache_ConcurrentAccess(t *testing.T)",
            "dynamicfake.NewSimpleDynamicClient(scheme)",
        ],
        "codeinterpreter_controller_test.go": [
            "func TestConvertToPodTemplate_RuntimeClassName_TableDriven(t *testing.T)",
            "func TestConvertToPodTemplate_AuthMode(t *testing.T)",
            "fake.NewClientBuilder().WithScheme(scheme).Build()",
            "PICOD_AUTH_PUBLIC_KEY",
            "RuntimeClassName",
        ],
        "handlers_test.go": [
            "type fakeStore struct",
            "func TestServerCreateSandbox(t *testing.T)",
            "func TestHandleSandboxCreate(t *testing.T)",
            "gomonkey.NewPatches()",
            "ApplyPrivateMethod",
            "createSandbox",
            "createSandboxClaim",
            "deleteSandbox",
            "httptest.NewRecorder()",
        ],
        "k8s_client_test.go": [
            "func createPodWithOwner(name, namespace, sandboxName string, phase corev1.PodPhase, podIP string) *corev1.Pod",
            "type mockPodNamespaceLister struct",
            "type mockPodLister struct",
            "func TestGetSandboxPodIP_Success(t *testing.T)",
            "func TestGetSandboxPodIP_PodNotFound(t *testing.T)",
            "func TestGetSandboxPodIP_InvalidPodStatus(t *testing.T)",
            "SandboxNameLabelKey",
        ],
        "runtimeclassname_test.go": [
            "func TestConvertToPodTemplate_RuntimeClassName(t *testing.T)",
            "runtimeClassName",
            "assert.Equal(t, tt.expected, result.Spec.RuntimeClassName",
        ],
        "sandbox_helper_test.go": [
            "const sandboxHelperTestPodIP",
            "func TestBuildSandboxInfo_TableDriven(t *testing.T)",
            "func TestGetSandboxStatus_TableDriven(t *testing.T)",
            "buildSandboxInfo",
            "getSandboxStatus",
            "SandboxConditionReady",
        ],
        "utils_test.go": [
            "func TestRandString(t *testing.T)",
            "RandString(8)",
            "RandString(32)",
        ],
    }

    if not root.exists():
        return ["AR-038 must create pkg/workloadmanager workloadmanager test package"]

    expected_paths = set(required)
    go_files = sorted(p for p in root.glob("*.go") if p.is_file())
    actual_tests = {p.name for p in go_files if p.name.endswith("_test.go")}
    missing = sorted(expected_paths - actual_tests)
    for rel in missing:
        errors.append(f"AR-038 must create pkg/workloadmanager/{rel}")

    unexpected_tests = sorted(actual_tests - expected_paths)
    if unexpected_tests:
        errors.append("AR-038 must not create unexpected workloadmanager test files: " + ", ".join(unexpected_tests[:12]))

    total_loc = 0
    for rel, tokens in required.items():
        path = root / rel
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        total_loc += len(text.splitlines())
        lower = text.lower()
        for token in ["notimplementederror", "stub implementation"]:
            if token in lower:
                errors.append(f"AR-038 pkg/workloadmanager/{rel} must not contain placeholder marker: {token}")
        for token in [
            "type Server struct",
            "type CodeInterpreterReconciler struct",
            "type K8sClient struct",
            "type ClientCache struct",
            "type TokenCache struct",
            "func buildSandboxInfo(",
            "func getSandboxStatus(",
            "func RandString(",
            "func buildSandboxByAgentRuntime(",
            "func buildSandboxByCodeInterpreter(",
            "func (s *Server) handleSandboxCreate(",
            "func (s *Server) createSandbox(",
            "func createSandbox(",
            "func deleteSandbox(",
            "func createSandboxClaim(",
            "func deleteSandboxClaim(",
        ]:
            if token in text:
                errors.append(
                    f"AR-038 pkg/workloadmanager/{rel} must not declare production shim: {token}"
                )
        for token in tokens:
            if token not in text:
                errors.append(f"AR-038 pkg/workloadmanager/{rel} missing token: {token}")

    if total_loc < 1800:
        errors.append(f"AR-038 workloadmanager test LOC is too small: {total_loc} < 1800")

    return errors


def _validate_ar043_docs(workspace: Path, docs_root: Path) -> list[str]:
    errors: list[str] = []
    content_markdown: list[str] = []
    localized_markdown: list[str] = []
    source_markdown: list[str] = []
    overlong: list[str] = []
    misplaced: list[str] = []

    for dirpath, dirnames, filenames in os.walk(docs_root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_SCAN_DIRS]
        for filename in filenames:
            path = Path(dirpath) / filename
            if path.suffix.lower() not in {".md", ".mdx"}:
                continue
            rel = str(path.relative_to(workspace))
            try:
                line_count = len(path.read_text(encoding="utf-8", errors="replace").splitlines())
            except OSError:
                line_count = 0
            if rel.startswith("docs/docs/"):
                content_markdown.append(rel)
            if rel.startswith("docs/i18n/"):
                localized_markdown.append(rel)
            if rel.startswith("docs/src/"):
                source_markdown.append(rel)
            if rel.startswith("docs/guide/") or rel.startswith("docs/api/"):
                misplaced.append(rel)
            if rel.startswith("docs/docs/") and line_count > 180:
                overlong.append(f"{rel}:{line_count}")

    allowed_markdown = AR_042_DOC_MARKDOWN | AR_043_DOC_MARKDOWN
    unexpected_markdown = sorted(set(content_markdown) - allowed_markdown)
    missing_markdown = sorted(AR_043_DOC_MARKDOWN - set(content_markdown))
    if unexpected_markdown:
        errors.append(
            "AR-043 docs pages must stay within the fixed manifest; unexpected: "
            + ", ".join(unexpected_markdown[:10])
        )
    if missing_markdown:
        errors.append(
            "AR-043 missing required docs markdown pages: "
            + ", ".join(missing_markdown[:8])
        )
    if source_markdown:
        errors.append(
            "AR-043 markdown/MDX docs must live under docs/docs/, not docs/src/: "
            + ", ".join(sorted(source_markdown)[:8])
        )
    if misplaced:
        errors.append(
            "AR-043 markdown must live under Docusaurus default content folder docs/docs/: "
            + ", ".join(sorted(misplaced)[:8])
        )
    if localized_markdown:
        errors.append(
            "AR-043 must not create localized markdown copies under docs/i18n/: "
            + ", ".join(sorted(localized_markdown)[:8])
        )
    if overlong:
        errors.append(
            "AR-043 docs pages exceed 180-line scope limit: "
            + ", ".join(overlong[:8])
        )

    sidebar = docs_root / "sidebars.ts"
    if not sidebar.exists():
        errors.append("AR-043 requires docs/sidebars.ts so new pages are navigable")
    else:
        sidebar_text = sidebar.read_text(encoding="utf-8", errors="replace")
        missing_sidebar = [
            rel.removeprefix("docs/docs/").removesuffix(".md").removesuffix(".mdx")
            for rel in sorted(AR_043_DOC_MARKDOWN)
            if rel.removeprefix("docs/docs/").removesuffix(".md").removesuffix(".mdx") not in sidebar_text
        ]
        if missing_sidebar:
            errors.append(
                "AR-043 docs/sidebars.ts must reference new docs pages: "
                + ", ".join(missing_sidebar[:8])
            )

    generated_files: list[str] = []
    for dirpath, dirnames, filenames in os.walk(workspace):
        dirnames[:] = [
            d for d in dirnames
            if d not in {".git", ".opencode"} | GENERATED_ARTIFACT_DIRS
        ]
        for filename in filenames:
            path = Path(dirpath) / filename
            if _is_generated_artifact_file(path, workspace):
                generated_files.append(str(path.relative_to(workspace)))
    generated = _find_generated_artifact_dirs(workspace) + sorted(generated_files)
    if generated:
        errors.append(
            "AR-043 must not leave generated dependency/build artifacts: "
            + ", ".join(sorted(generated)[:8])
        )

    return errors


def _scan_placeholder_hits(workspace: Path, rel_files: list[str]) -> list[str]:
    hits = []
    for rel in rel_files:
        path = workspace / rel
        is_test_file = rel.endswith("_test.go") or "/test/" in rel or rel.startswith("test/")
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            if "context.TODO()" in line:
                continue
            lower = line.lower()
            if any(snippet in lower for snippet in ALLOWED_PLACEHOLDER_LINE_SNIPPETS):
                continue
            marker_match = PLACEHOLDER_MARKER_RE.search(line)
            if marker_match:
                hits.append(f"{rel}:{lineno}:{marker_match.group(0)}")
                continue
            for pat in PLACEHOLDER_PATTERNS:
                if pat.lower() in lower:
                    if is_test_file and pat.lower() in {
                        "stub implementation",
                        "stubbed implementation",
                        "mock implementation",
                        "dummy implementation",
                    }:
                        continue
                    hits.append(f"{rel}:{lineno}:{pat}")
                    break
    return hits


def _scan_missing_local_go_imports(workspace: Path, rel_files: list[str]) -> list[str]:
    go_mod = workspace / "go.mod"
    if not go_mod.exists():
        return []
    module = ""
    for line in go_mod.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.startswith("module "):
            module = line.split(None, 1)[1].strip()
            break
    if not module:
        return []

    missing: list[str] = []
    for rel in rel_files:
        if not rel.endswith(".go"):
            continue
        path = workspace / rel
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for match in re.finditer(r'"(' + re.escape(module) + r'/[^"]+)"', text):
            import_path = match.group(1)
            suffix = import_path.removeprefix(module + "/")
            if not (workspace / suffix).is_dir():
                missing.append(f"{rel}: {import_path}")
    return sorted(set(missing))


def _run_local_checks(workspace: Path, ar: dict) -> list[dict]:
    """Run bounded, deterministic checks for the AR module."""
    checks: list[dict] = []

    def append_check(
        cmd: list[str],
        cwd: Path,
        timeout_seconds: int,
        env: Optional[dict[str, str]] = None,
        display_cmd: Optional[str] = None,
    ) -> None:
        start = time.time()
        try:
            result = subprocess.run(
                cmd,
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                env=env,
            )
            checks.append({
                "command": display_cmd or " ".join(cmd),
                "exit_code": result.returncode,
                "duration_seconds": round(time.time() - start, 2),
                "stdout": result.stdout[-4000:],
                "stderr": result.stderr[-4000:],
            })
        except subprocess.TimeoutExpired as e:
            out = e.output or ""
            err = e.stderr or ""
            if isinstance(out, bytes):
                out = out.decode("utf-8", errors="replace")
            if isinstance(err, bytes):
                err = err.decode("utf-8", errors="replace")
            checks.append({
                "command": display_cmd or " ".join(cmd),
                "exit_code": "timeout",
                "duration_seconds": timeout_seconds,
                "stdout": out[-4000:],
                "stderr": err[-4000:],
            })

    cmd: list[str] | None = None
    cwd = workspace
    timeout_seconds = 90
    module = ar["module"].strip("/")
    module_dir = workspace / module
    if module == "docs" and (module_dir / "package.json").exists() and ar["lang"] in {"TypeScript", "Markdown"}:
        cwd = module_dir
        try:
            timeout_seconds = int(os.getenv("SDD_LOCAL_CHECK_TIMEOUT_TS", "300"))
        except ValueError:
            timeout_seconds = 300
        cmd = [
            "bash",
            "-lc",
            (
                "trap 'rm -rf node_modules .docusaurus build dist coverage' EXIT; "
                "npm install --no-package-lock --ignore-scripts && npm run build"
            ),
        ]
    elif ar["lang"] == "Go":
        target = f"./{module}/..." if module else "./..."
        cmd = ["bash", "-lc", f"go test -mod=readonly {target}"]
    elif ar["lang"] == "Python":
        if (workspace / module).exists():
            cmd = [
                sys.executable,
                "-c",
                (
                    "import ast,pathlib,sys;"
                    f"root=pathlib.Path({module!r});"
                    "errors=[];"
                    "\nfor p in root.rglob('*.py'):\n"
                    "    try:\n"
                    "        ast.parse(p.read_text(encoding='utf-8'), filename=str(p))\n"
                    "    except SyntaxError as e:\n"
                    "        errors.append(f'{p}:{e.lineno}:{e.offset}: {e.msg}')\n"
                    "print('\\n'.join(errors));"
                    "sys.exit(1 if errors else 0)"
                ),
            ]
    elif ar["lang"] in {"YAML", "Dockerfile", "Makefile", "Markdown", "TypeScript"}:
        cmd = None

    if cmd:
        env = os.environ.copy()
        if ar["lang"] == "Python":
            env["PYTHONDONTWRITEBYTECODE"] = "1"
        append_check(cmd, cwd, timeout_seconds, env=env)

    if ar["lang"] == "Python" and module == "cmd/cli" and all(
        check.get("exit_code") in (0, "0") for check in checks
    ):
        tests_dir = workspace / module / "agentcube/tests"
        if tests_dir.exists() and any(tests_dir.rglob("test_*.py")):
            try:
                pytest_timeout = int(os.getenv("SDD_LOCAL_CHECK_TIMEOUT_PY", "240"))
            except ValueError:
                pytest_timeout = 240
            env = os.environ.copy()
            env["PYTHONDONTWRITEBYTECODE"] = "1"
            env["PYTHONPATH"] = module
            pytest_cmd = [
                sys.executable,
                "-m",
                "pytest",
                f"{module}/agentcube/tests",
                "-q",
                "-p",
                "no:cacheprovider",
                "-W",
                "error",
                "-W",
                "error::pytest.PytestUnraisableExceptionWarning",
            ]
            append_check(
                pytest_cmd,
                workspace,
                pytest_timeout,
                env=env,
                display_cmd=(
                    f"PYTHONDONTWRITEBYTECODE=1 PYTHONPATH={module} "
                    + " ".join(pytest_cmd)
                ),
            )

    if ar["lang"] == "Python" and module == "sdk-python" and all(
        check.get("exit_code") in (0, "0") for check in checks
    ):
        tests_dir = workspace / module / "tests"
        if tests_dir.exists() and any(tests_dir.rglob("test_*.py")):
            try:
                pytest_timeout = int(os.getenv("SDD_LOCAL_CHECK_TIMEOUT_PY", "240"))
            except ValueError:
                pytest_timeout = 240
            env = os.environ.copy()
            env["PYTHONDONTWRITEBYTECODE"] = "1"
            env["PYTHONPATH"] = module
            pytest_cmd = [
                sys.executable,
                "-m",
                "pytest",
                f"{module}/tests",
                "-q",
                "-p",
                "no:cacheprovider",
                "-W",
                "error",
                "-W",
                "error::pytest.PytestUnraisableExceptionWarning",
            ]
            append_check(
                pytest_cmd,
                workspace,
                pytest_timeout,
                env=env,
                display_cmd=(
                    f"PYTHONDONTWRITEBYTECODE=1 PYTHONPATH={module} "
                    + " ".join(pytest_cmd)
                ),
            )

    workloadmanager_validators = {
        "AR-004": ("internal:validate_ar004_workloadmanager_framework", _validate_ar004_workloadmanager_framework),
        "AR-005": ("internal:validate_ar005_workloadmanager_creation", _validate_ar005_workloadmanager_creation),
        "AR-006": ("internal:validate_ar006_workloadmanager_lifecycle", _validate_ar006_workloadmanager_lifecycle),
        "AR-007": ("internal:validate_ar007_workloadmanager_controllers", _validate_ar007_workloadmanager_controllers),
        "AR-008": ("internal:validate_ar008_workloadmanager_gc_complete", _validate_ar008_workloadmanager_gc_complete),
    }
    if ar.get("id") in workloadmanager_validators:
        command, validator = workloadmanager_validators[ar["id"]]
        start = time.time()
        validation_errors = validator(workspace)
        checks.append({
            "command": command,
            "exit_code": 1 if validation_errors else 0,
            "duration_seconds": round(time.time() - start, 2),
            "stdout": "\n".join(validation_errors[-40:]),
            "stderr": "",
        })

    router_validators = {
        "AR-009": ("internal:validate_ar009_router_core", _validate_ar009_router_core),
        "AR-010": ("internal:validate_ar010_router_session_manager", _validate_ar010_router_session_manager),
        "AR-011": ("internal:validate_ar011_router_jwt", _validate_ar011_router_jwt),
    }
    if ar.get("id") in router_validators:
        command, validator = router_validators[ar["id"]]
        start = time.time()
        validation_errors = validator(workspace)
        checks.append({
            "command": command,
            "exit_code": 1 if validation_errors else 0,
            "duration_seconds": round(time.time() - start, 2),
            "stdout": "\n".join(validation_errors[-40:]),
            "stderr": "",
        })

    store_validators = {
        "AR-012": ("internal:validate_ar012_store_contract", _validate_ar012_store_contract),
        "AR-013": ("internal:validate_ar013_redis_backend", _validate_ar013_redis_backend),
        "AR-014": ("internal:validate_ar014_valkey_backend", _validate_ar014_valkey_backend),
    }
    if ar.get("id") in store_validators:
        command, validator = store_validators[ar["id"]]
        start = time.time()
        validation_errors = validator(workspace)
        checks.append({
            "command": command,
            "exit_code": 1 if validation_errors else 0,
            "duration_seconds": round(time.time() - start, 2),
            "stdout": "\n".join(validation_errors[-40:]),
            "stderr": "",
        })

    picod_validators = {
        "AR-015": ("internal:validate_ar015_picod_execute_api", _validate_ar015_picod_execute_api),
        "AR-016": ("internal:validate_ar016_picod_file_api", _validate_ar016_picod_file_api),
        "AR-017": ("internal:validate_ar017_picod_auth_middleware", _validate_ar017_picod_auth_middleware),
    }
    if ar.get("id") in picod_validators:
        command, validator = picod_validators[ar["id"]]
        start = time.time()
        validation_errors = validator(workspace)
        checks.append({
            "command": command,
            "exit_code": 1 if validation_errors else 0,
            "duration_seconds": round(time.time() - start, 2),
            "stdout": "\n".join(validation_errors[-40:]),
            "stderr": "",
        })

    if ar.get("id") == "AR-030":
        start = time.time()
        validation_errors = _validate_ar030_helm_chart(workspace)
        checks.append({
            "command": "internal:validate_ar030_helm_chart",
            "exit_code": 1 if validation_errors else 0,
            "duration_seconds": round(time.time() - start, 2),
            "stdout": "\n".join(validation_errors[-40:]),
            "stderr": "",
        })

    if ar.get("id") == "AR-031":
        start = time.time()
        validation_errors = _validate_ar031_helm_rbac(workspace)
        checks.append({
            "command": "internal:validate_ar031_helm_rbac",
            "exit_code": 1 if validation_errors else 0,
            "duration_seconds": round(time.time() - start, 2),
            "stdout": "\n".join(validation_errors[-40:]),
            "stderr": "",
        })

    if ar.get("id") == "AR-032":
        start = time.time()
        validation_errors = _validate_ar032_dockerfiles(workspace)
        checks.append({
            "command": "internal:validate_ar032_dockerfiles",
            "exit_code": 1 if validation_errors else 0,
            "duration_seconds": round(time.time() - start, 2),
            "stdout": "\n".join(validation_errors[-40:]),
            "stderr": "",
        })

    if ar.get("id") == "AR-033":
        start = time.time()
        validation_errors = _validate_ar033_makefile(workspace)
        checks.append({
            "command": "internal:validate_ar033_makefile",
            "exit_code": 1 if validation_errors else 0,
            "duration_seconds": round(time.time() - start, 2),
            "stdout": "\n".join(validation_errors[-40:]),
            "stderr": "",
        })

    if ar.get("id") == "AR-034":
        start = time.time()
        validation_errors = _validate_ar034_github_workflows(workspace)
        checks.append({
            "command": "internal:validate_ar034_github_workflows",
            "exit_code": 1 if validation_errors else 0,
            "duration_seconds": round(time.time() - start, 2),
            "stdout": "\n".join(validation_errors[-40:]),
            "stderr": "",
        })

    if ar.get("id") == "AR-035":
        start = time.time()
        validation_errors = _validate_ar035_client_go(workspace)
        checks.append({
            "command": "internal:validate_ar035_client_go",
            "exit_code": 1 if validation_errors else 0,
            "duration_seconds": round(time.time() - start, 2),
            "stdout": "\n".join(validation_errors[-40:]),
            "stderr": "",
        })

    if ar.get("id") == "AR-036":
        start = time.time()
        validation_errors = _validate_ar036_dify_plugin(workspace)
        checks.append({
            "command": "internal:validate_ar036_dify_plugin",
            "exit_code": 1 if validation_errors else 0,
            "duration_seconds": round(time.time() - start, 2),
            "stdout": "\n".join(validation_errors[-40:]),
            "stderr": "",
        })

    if ar.get("id") == "AR-037":
        start = time.time()
        validation_errors = _validate_ar037_pcap_analyzer(workspace)
        checks.append({
            "command": "internal:validate_ar037_pcap_analyzer",
            "exit_code": 1 if validation_errors else 0,
            "duration_seconds": round(time.time() - start, 2),
            "stdout": "\n".join(validation_errors[-40:]),
            "stderr": "",
        })

    if ar.get("id") == "AR-038":
        start = time.time()
        validation_errors = _validate_ar038_workloadmanager_tests(workspace)
        checks.append({
            "command": "internal:validate_ar038_workloadmanager_tests",
            "exit_code": 1 if validation_errors else 0,
            "duration_seconds": round(time.time() - start, 2),
            "stdout": "\n".join(validation_errors[-40:]),
            "stderr": "",
        })

    return checks


def _write_programmatic_verification(
    workspace: Path,
    ar: dict,
    reasons: list[str],
    checks: list[dict] | None = None,
) -> list[dict]:
    """Write an honest fallback verification artifact."""
    change_dir = workspace / "changes" / ar["id"]
    change_dir.mkdir(parents=True, exist_ok=True)
    if checks is None:
        checks = _run_local_checks(workspace, ar)

    lines = [
        f"# Verification Report — {ar['id']}",
        "",
        "Generated by the benchmark harness because model-driven ST-6 verification did not produce a valid artifact.",
        "",
        "## Model Verification Failure",
    ]
    for reason in reasons:
        lines.append(f"- {reason}")
    lines.extend(["", "## Local Checks"])
    if checks:
        for check in checks:
            lines.append(f"- Command: `{check['command']}`")
            lines.append(f"  - Exit code: `{check['exit_code']}`")
            lines.append(f"  - Duration: `{check['duration_seconds']}s`")
            if check.get("stdout"):
                lines.extend(["", "```text", check["stdout"].rstrip(), "```"])
            if check.get("stderr"):
                lines.extend(["", "```text", check["stderr"].rstrip(), "```"])
    else:
        lines.append("- No bounded local check is configured for this AR language/module.")

    lines.extend([
        "",
        "## Result",
        "This report is a fallback verification artifact. It must not be treated as a model-authored pass.",
        "",
    ])
    (change_dir / "verification.md").write_text("\n".join(lines), encoding="utf-8")
    return checks


def _failed_local_checks(checks: list[dict]) -> list[str]:
    failed: list[str] = []
    for check in checks:
        exit_code = check.get("exit_code")
        if exit_code not in (0, "0"):
            failed.append(f"{check.get('command', '<unknown>')} exit={exit_code}")
    return failed


def _failed_local_check_details(checks: list[dict]) -> list[str]:
    failed: list[str] = []
    for check in checks:
        exit_code = check.get("exit_code")
        if exit_code in (0, "0"):
            continue
        msg = f"{check.get('command', '<unknown>')} exit={exit_code}"
        output = "\n".join(
            part.strip()
            for part in (check.get("stdout", ""), check.get("stderr", ""))
            if part and part.strip()
        )
        if output:
            compact = " ".join(output.split())
            if len(compact) > 1800:
                compact = compact[:900] + " ... " + compact[-900:]
            msg += f" output={compact}"
        failed.append(msg)
    return failed


def _write_programmatic_archive(workspace: Path, ar: dict, reasons: list[str]) -> None:
    change_dir = workspace / "changes" / ar["id"]
    changelog = change_dir / "changelog" / "entries.md"
    readme = change_dir / "README.md"
    changelog.parent.mkdir(parents=True, exist_ok=True)
    note = [
        "",
        "## Harness Archive Fallback",
        "",
        "Model-driven archive did not complete cleanly. The benchmark harness recorded this fallback instead.",
        "",
        "Reasons:",
    ]
    note.extend(f"- {reason}" for reason in reasons)
    note.extend([
        "",
        f"AR: {ar['id']} — {ar['name']}",
        f"Module: {ar['module']}",
        "",
    ])
    with changelog.open("a", encoding="utf-8") as f:
        f.write("\n".join(note))
    if readme.exists():
        with readme.open("a", encoding="utf-8") as f:
            f.write("\n".join(note))
    else:
        readme.write_text("\n".join([f"# {ar['id']} {ar['name']}"] + note), encoding="utf-8")


def _merge_stage_record(total: StageRecord, part: StageRecord) -> StageRecord:
    total.input_tokens += part.input_tokens
    total.output_tokens += part.output_tokens
    total.cache_read_tokens += part.cache_read_tokens
    total.cache_write_tokens += part.cache_write_tokens
    total.iterations += part.iterations
    total.api_calls += part.api_calls
    total.cost_usd += part.cost_usd
    total.duration_seconds += part.duration_seconds
    total.attempts += max(0, part.attempts)
    if part.error:
        total.error = part.error if not total.error else f"{total.error}; {part.error}"
    if part.data_source != "none":
        total.data_source = part.data_source
    if part.exit_code is not None:
        total.exit_code = part.exit_code
    return total


def _stage_timeout(stage_id: str) -> int:
    defaults = {
        "ST-5": 900,
        "ST-6": 300,
        "ST-7": 300,
    }
    default = defaults.get(stage_id, 420)
    env_key = f"SDD_STAGE_TIMEOUT_{stage_id.replace('-', '')}"
    raw = os.getenv(env_key)
    if raw:
        try:
            value = int(raw)
            if value > 0:
                return value
        except ValueError:
            pass
    return default


def _max_stage_attempts(stage_id: str) -> int:
    defaults = {
        "ST-5": 4,
        "ST-6": 1,
    }
    default = defaults.get(stage_id, 2)
    env_keys = [
        f"SDD_STAGE_ATTEMPTS_{stage_id.replace('-', '')}",
        "SDD_STAGE_ATTEMPTS",
    ]
    for env_key in env_keys:
        raw = os.getenv(env_key)
        if not raw:
            continue
        try:
            value = int(raw)
            if value > 0:
                return value
        except ValueError:
            continue
    return default


def _repair_prompt(ar: dict, stage_id: str, original_prompt: str, errors: list[str]) -> str:
    allowed_prefixes = _allowed_implementation_prefixes(ar)
    if allowed_prefixes == ["root"]:
        allowed_paths = "project root files (for this AR, `Makefile`)"
    else:
        allowed_paths = ", ".join(
            f"`{prefix}/...`" for prefix in allowed_prefixes
        ) or "the project root target paths"
    package_manager_policy = ""
    if ar.get("id") == "AR-042":
        package_manager_policy = (
            " For this Docusaurus docs AR, do not execute npm, npx, yarn, or pnpm commands, "
            "and do not create package-lock.json, pnpm-lock.yaml, yarn.lock, node_modules, "
            ".docusaurus, build, dist, or coverage. The benchmark harness runs install/build "
            "checks separately. Import `themes as prismThemes` from `prism-react-renderer` and configure "
            "`themeConfig.prism` as `{ theme: prismThemes.github, darkTheme: prismThemes.dracula, "
            "additionalLanguages: [...] }`; do not use light/dark/plain string fields. Put markdown content "
            "under the site's default `docs/` folder, using project paths like `docs/docs/guide/...` and "
            "`docs/docs/api/...`; do not add a second content-docs plugin. Use `src/pages/index.tsx` for "
            "React/TSX home pages and do not include MDX front matter in `.tsx`; do not place TypeScript "
            "annotations in `.mdx` files. Links to API docs must use `/docs/api/...`, not `/api/...`. "
            "Do not create `i18n/en/...` or docs `current.json` translation files; static img assets must be "
            "non-empty files under `docs/static/img/...`; prefer `logo.svg` and avoid empty `.ico`/`.jpg` files. "
            "Avoid cross-folder `../*.md` markdown links; use `/docs/...` routes. "
            "Write at most 8 markdown pages under `docs/docs/` and no localized markdown copies. The React home "
            "page must have exactly one default export. Use "
            "Docusaurus package versions `^3.10.1` or `3.10.1`, not 3.5.x."
        )
    missing_implementation_note_only = (
        stage_id == "ST-5"
        and errors
        and all(
            "missing required artifact" in err
            and f"changes/{ar['id']}/implementation.md" in err
            for err in errors
        )
    )
    test_repair_policy = ""
    if ar.get("type") == "测试" and ar.get("lang") == "Go":
        module_path = ar.get("module", "").strip("/")
        if module_path == "test" or module_path.startswith("test/"):
            test_repair_policy = (
                f" For this Go E2E test AR, create or modify only test and test helper `.go` files "
                f"under `{module_path}/...`; do not modify production Go packages."
            )
        else:
            test_repair_policy = (
                " For this Go test AR, create or modify only files ending in `_test.go`; "
                "do not modify production `.go` implementation files."
            )
    ar_repair_policy = ""
    if ar.get("id") == "AR-030" and stage_id == "ST-5":
        ar_repair_policy = (
            " For AR-030, the minimum complete Helm chart file set is "
            "`manifests/charts/base/Chart.yaml`, `manifests/charts/base/values.yaml`, "
            "`manifests/charts/base/templates/workloadmanager.yaml`, "
            "`manifests/charts/base/templates/agentcube-router.yaml`, "
            "`manifests/charts/base/crds/agentruntimes.runtime.agentcube.volcano.sh.yaml`, and "
            "`manifests/charts/base/crds/codeinterpreters.runtime.agentcube.volcano.sh.yaml`. "
            "If any CRD validation error appears, write both CRD YAML files before returning."
        )
    if ar.get("id") == "AR-031" and stage_id == "ST-5":
        ar_repair_policy = (
            " For AR-031, the minimum complete RBAC file set is "
            "`manifests/charts/base/templates/rbac/workloadmanager.yaml`, "
            "`manifests/charts/base/templates/rbac-router.yaml`, and "
            "`manifests/charts/base/templates/volcano-agent-scheduler-development.yaml`. "
            "If any Workload Manager, Router, or Volcano RBAC validation error appears, repair the matching "
            "template file before returning."
        )
    if ar.get("id") == "AR-032" and stage_id == "ST-5":
        ar_repair_policy = (
            " For AR-032, the minimum complete Dockerfile set is `docker/Dockerfile`, "
            "`docker/Dockerfile.router`, and `docker/Dockerfile.picod`. If any Dockerfile validation error appears, "
            "repair the matching file before returning; do not create Makefile, Helm, CI, source, or rendered files."
        )
    if ar.get("id") == "AR-033" and stage_id == "ST-5":
        ar_repair_policy = (
            " For AR-033, the only implementation file is the repository-root `Makefile`. Do not create "
            "`root/Makefile`; repair the root `Makefile` before returning, and do not create Docker, Helm, CI, "
            "source, hack script, binary, or build-output files."
        )
    if ar.get("id") == "AR-034" and stage_id == "ST-5":
        ar_repair_policy = (
            " For AR-034, the minimum complete GitHub Actions file set is "
            "`.github/workflows/main.yml`, `.github/workflows/e2e.yml`, `.github/workflows/lint.yml`, "
            "`.github/workflows/python-sdk-tests.yml`, `.github/workflows/python-lint.yml`, "
            "`.github/workflows/test-coverage.yml`, `.github/workflows/codegen-check.yml`, "
            "`.github/workflows/copyright-check.yml`, `.github/workflows/codespell.yml`, "
            "`.github/workflows/build-push-release.yml`, `.github/workflows/dify-plugin-publish.yml`, and "
            "`.github/workflows/workflows-approve.yml`. Repair missing or invalid workflow YAML under "
            "`.github/workflows/` only; do not create Makefile, Docker, Helm, source, test, docs, or generated files."
        )
    if ar.get("id") in {"AR-004", "AR-005", "AR-006", "AR-007"} and stage_id == "ST-5":
        ar_repair_policy = (
            f" For {ar['id']}, repair only real WorkloadManager production files from the original reference. "
            "Delete non-original files such as `pkg/workloadmanager/cache.go`, `pkg/workloadmanager/defaults.go`, "
            "`pkg/workloadmanager/memory_store.go`, `pkg/workloadmanager/middleware.go`, "
            "`pkg/workloadmanager/sandbox_creator.go`, `pkg/workloadmanager/store.go`, and "
            "`pkg/workloadmanager/token_cache.go`. Delete any `pkg/workloadmanager/*_test.go` and "
            "`pkg/common/types/*_test.go`; tests belong to later testing ARs. Shared types must be exactly under "
            "`pkg/common/types/types.go` and `pkg/common/types/sandbox.go`, not `pkg/common/types.go`, and "
            "workloadmanager must import `github.com/volcano-sh/agentcube/pkg/common/types`. `SandboxInfo.EntryPoints` "
            "and `CreateSandboxResponse.EntryPoints` must use `[]SandboxEntryPoint`, and `SandboxEntryPoint` must have "
            "`Path`, `Protocol`, and `Endpoint` fields; do not create a non-original `EntryPoint` type. The early "
            "`pkg/store/store.go` contract must include `UpdateSessionLastActivity(ctx context.Context, sessionID string, "
            "at time.Time) error` and the expired/inactive list methods with `limit int64`. Do not create concrete "
            "store backends such as `pkg/store/memory_store.go`, Redis, or Valkey implementations in WorkloadManager "
            "production ARs; only the shared `pkg/store/store.go` interface is allowed before the dedicated store ARs. "
            "Do not create service entrypoints such as `cmd/workload-manager/main.go`; those belong to AR-019. "
            "Keep `go.mod` on the "
            "original AgentCube baseline (`go 1.24.4`, `toolchain go1.24.9`, Kubernetes modules v0.34.1, "
            "`sigs.k8s.io/agent-sandbox v0.1.1`, controller-runtime v0.22.2). "
            "For AR-004 specifically, the minimum required production files are `server.go`, `utils.go`, "
            "`client_cache.go`, `k8s_client.go`, and the two `pkg/common/types` files. The exact AR-004 "
            "`pkg/workloadmanager/` production file set is only `server.go`, `utils.go`, `client_cache.go`, and "
            "`k8s_client.go`; delete later-AR files such as `auth.go`, `handlers.go`, `informers.go`, "
            "`garbage_collection.go`, controller files, and `cmd/workload-manager/main.go`."
        )
        if ar.get("id") == "AR-005":
            ar_repair_policy += (
                " For AR-005 specifically, the required production files are `handlers.go`, "
                "`workload_builder.go`, `sandbox_helper.go`, and `k8s_client.go`; repair them from the original "
                "reference instead of inventing alternate workload lookup helpers. `workload_builder.go` must contain "
                "`buildSandboxObject`, `buildSandboxClaimObject`, `buildSandboxByAgentRuntime`, "
                "`buildSandboxByCodeInterpreter`, `PICOD_AUTH_PUBLIC_KEY`, and `RuntimeClassName`. "
                "`sandbox_helper.go` must keep the real `buildSandboxPlaceHolder` and `buildSandboxInfo` helpers."
            )
    if ar.get("id") == "AR-008" and stage_id == "ST-5":
        ar_repair_policy = (
            " For AR-008, the WorkloadManager production package must be complete and real after repair. "
            "The exact production Go file set under `pkg/workloadmanager/` is `auth.go`, `client_cache.go`, "
            "`codeinterpreter_controller.go`, `garbage_collection.go`, `handlers.go`, `informers.go`, "
            "`k8s_client.go`, `sandbox_controller.go`, `sandbox_helper.go`, `server.go`, `utils.go`, and "
            "`workload_builder.go`. Remove non-original shim files such as `defaults.go`, `memory_store.go`, "
            "`middleware.go`, `sandbox_creator.go`, `store.go`, and `token_cache.go`. Use the original reference "
            "instead of patching individual missing tokens with dummy wrappers. Keep shared types under "
            "`pkg/common/types/`: `SandboxEntryPoint` must have `Path`, `Protocol`, and `Endpoint`, and sandbox "
            "responses must use `[]SandboxEntryPoint`, not a local `EntryPoint` type. Keep `pkg/store/store.go` aligned "
            "with the original Store interface, including `UpdateSessionLastActivity` and int64 list limits. Keep "
            "`go.mod` on the original AgentCube dependency baseline; do not import "
            "`github.com/volcano-sh/agentcube/pkg/common` from workloadmanager. Do not create workloadmanager or "
            "common/types tests in AR-008; tests belong to later testing ARs."
        )
    if ar.get("id") == "AR-009" and stage_id == "ST-5":
        ar_repair_policy = (
            " For AR-009, reset the implementation to exactly three Router core production files: "
            "`pkg/router/config.go`, `pkg/router/server.go`, and `pkg/router/handlers.go`. Delete or avoid "
            "`pkg/router/*_test.go`, `pkg/router/jwt.go`, `pkg/router/jwt_manager.go`, `pkg/router/session.go`, "
            "`pkg/router/session_manager.go`, `cmd/router`, and any edits to `pkg/api`, `pkg/store`, `pkg/common`, "
            "`go.mod`, or `go.sum`. Implement the real Config/LastActivityAnnotationKey, Server/NewServer/Start, "
            "Gin health and invocation routes, concurrency middleware, `handleInvoke`, `determineUpstreamURL`, "
            "`handleAgentInvoke`, `handleCodeInterpreterInvoke`, `forwardToSandbox`, `httputil.NewSingleHostReverseProxy`, "
            "forwarding headers, response `x-agentcube-session-id`, and `s.storeClient.UpdateSessionLastActivity`. "
            "Use `*types.SandboxInfo` and `types.SandboxEntryPoint` directly; do not define local `SandboxInfo`, "
            "`SandboxEntryPoint`, `convertToTypesEntryPoints`, or a wrapper `UpdateSessionLastActivity` function. "
            "Because AR-010 and AR-011 are deferred, define only narrow package-local interfaces inside the allowed "
            "files for session lookup and optional JWT signing; use an unexported JWT signer interface such as "
            "`tokenSigner`, not `type JWTManager interface` or `*JWTManager`."
        )
    if ar.get("id") == "AR-010" and stage_id == "ST-5":
        ar_repair_policy = (
            " For AR-010, reset the Router package to exactly four production files for this split: "
            "`pkg/router/config.go`, `pkg/router/server.go`, `pkg/router/handlers.go`, and "
            "`pkg/router/session_manager.go`. Delete or avoid `pkg/router/jwt.go`, `pkg/router/jwt_manager.go`, "
            "`pkg/router/*_test.go`, `cmd/router`, and any edits to `pkg/store`, `pkg/common`, `go.mod`, "
            "or `go.sum`. The only allowed non-router source edit is `pkg/api/errors.go`, and only to add the "
            "original `NewSessionNotFoundError` and `NewSandboxTemplateNotFoundError` helpers. Implement the real "
            "`SessionManager` interface, `manager`, "
            "`NewSessionManager(store.Store)`, `GetSandboxBySession`, workload manager create calls, auth token "
            "loading from `/var/run/secrets/kubernetes.io/serviceaccount/token`, HTTP/2 transport settings, "
            "store lookup with `store.ErrNotFound`, and `types.CreateSandboxResponse` to `types.SandboxInfo` mapping. "
            "Wire `NewServer` to `NewSessionManager(store.Storage())` while preserving the AR-009 reverse-proxy "
            "routes and handlers. JWT key management is AR-011; keep only the existing narrow `tokenSigner` "
            "interface and do not define `JWTManager`, `NewJWTManager`, or `TryStoreOrLoadJWTKeySecret` in AR-010."
        )
    if ar.get("id") == "AR-011" and stage_id == "ST-5":
        ar_repair_policy = (
            " For AR-011, reset the Router package to the cumulative five production files: "
            "`pkg/router/config.go`, `pkg/router/server.go`, `pkg/router/handlers.go`, "
            "`pkg/router/session_manager.go`, and `pkg/router/jwt.go`. Delete router tests, `cmd/router`, "
            "alternate JWT interfaces, and any rewrites outside `pkg/router` except dependency metadata. "
            "Implement the original `JWTManager` in `jwt.go`: RS256 RSA key generation with `rand.Reader`, "
            "`rsaKeySize`, `jwtExpiration`, `IdentitySecretName`, `PrivateKeyDataKey`, `PublicKeyDataKey`, "
            "`IdentityNamespace` from `AGENTCUBE_NAMESPACE`, `GenerateToken`, PEM helpers, "
            "`TryStoreOrLoadJWTKeySecret`, Kubernetes Secret create/load, and `loadPrivateKeyPEM`. Wire "
            "`Server` to hold `jwtManager *JWTManager`, call `NewJWTManager`, call "
            "`TryStoreOrLoadJWTKeySecret(context.Background())`, and set `server.jwtManager`. Wire "
            "`forwardToSandbox` to call `s.jwtManager.GenerateToken(claims)` for `Sandbox`/`SandboxClaim` kinds "
            "and set `Authorization: Bearer <token>`. Remove the earlier AR-009 `tokenSigner` shim. Ensure "
            "`go.mod` includes `github.com/golang-jwt/jwt/v5 v5.2.2`."
        )
    if ar.get("id") == "AR-012" and stage_id == "ST-5":
        ar_repair_policy = (
            " For AR-012, reset `pkg/store` to only the store contract files for this split: "
            "`pkg/store/interface.go`, `pkg/store/error.go`, and `pkg/store/singleton.go`. Remove the earlier "
            "temporary `pkg/store/store.go` empty implementation and do not create `store_redis.go`, "
            "`store_valkey.go`, tests, mocks, no-op Store method implementations, or dependency metadata changes. "
            "`interface.go` must contain the real `Store` interface using `*types.SandboxInfo` and int64 limits. "
            "`error.go` must define `ErrNotFound = errors.New(\"store: not found\")`. `singleton.go` must expose "
            "`Storage()` with `sync.Once`, `STORE_TYPE` selection for redis/valkey, and explicit deferred-provider "
            "errors until AR-013/AR-014; it must not call absent `initRedisStore` or `initValkeyStore` functions."
        )
    if ar.get("id") == "AR-013" and stage_id == "ST-5":
        ar_repair_policy = (
            " For AR-013, implement the Redis backend only. Create or repair `pkg/store/store_redis.go`, "
            "`pkg/store/store_redis_test.go`, and the Redis branch in `pkg/store/singleton.go`. The singleton "
            "must call `initRedisStore()`, assign `provider = redisProvider`, and may keep the Valkey branch as an "
            "explicit unsupported/deferred provider until AR-014; do not call `initValkeyStore` or create Valkey "
            "files. Use `redisv9 \"github.com/redis/go-redis/v9\"` at v9.17.1 and real miniredis/redismock-backed "
            "tests covering StoreSandbox, GetSandboxBySessionID, expiry/inactive lists, UpdateSessionLastActivity, "
            "and ErrNotFound. If using miniredis, keep `github.com/alicebob/miniredis/v2` at the original v2.35.0. "
            "Keep the original Go baseline in go.mod: `go 1.24.4` and `toolchain go1.24.9`."
        )
    if ar.get("id") == "AR-014" and stage_id == "ST-5":
        ar_repair_policy = (
            " For AR-014, implement the Valkey backend only. Create or repair `pkg/store/store_valkey.go`, "
            "`pkg/store/store_valkey_test.go`, and the Valkey branch in `pkg/store/singleton.go`. Do not modify "
            "Redis backend files except as required by shared interfaces, and do not leave an unsupported or "
            "not-implemented Valkey branch. The singleton must call `initValkeyStore()`, assign "
            "`provider = valkeyProvider`, and log successful Valkey init. Use `github.com/valkey-io/valkey-go` "
            "at v1.0.69 and miniredis v2.35.0; tests must cover makeValkeyOptions, StoreSandbox, "
            "GetSandboxBySessionID, expiry/inactive lists, UpdateSessionLastActivity, ErrNotFound, "
            "VALKEY_DISABLE_CACHE, and VALKEY_FORCE_SINGLE. Do not use `v0.0.0`, pseudo-version replaces, "
            "or a newer Go directive; keep `go 1.24.4` and `toolchain go1.24.9`."
        )
    if ar.get("id") == "AR-035" and stage_id == "ST-5":
        ar_repair_policy = (
            " For AR-035, the minimum complete generated client-go file set is the real 25-file tree under "
            "`client-go/`: versioned clientset/scheme/fake, typed runtime/v1alpha1 clients and fakes, "
            "externalversions informer factory/generic/runtime/v1alpha1 informers/internalinterfaces, and "
        "runtime/v1alpha1 listers. Repair missing or invalid Go generated-code files under `client-go/` only. "
        "Do not patch around individual token errors with ad hoc wrappers; replace each invalid file with the "
        "real Kubernetes code-generator v0.34.1 generated structure from the original reference in the original "
        "instructions. Typed clients must use `gentype.ClientWithList`, typed fakes must use "
        "`gentype.FakeClientWithList`, listers must use `listers.ResourceIndexer`, informers must include "
        "`ListWithContextFunc` and `WatchFuncWithContext`, and generic routing must switch on "
            "`v1alpha1.SchemeGroupVersion.WithResource(...)`. Ensure `go.mod` uses `k8s.io/api`, "
            "`k8s.io/apimachinery`, and `k8s.io/client-go` v0.34.1 so `k8s.io/client-go/gentype` resolves. "
            "It may modify `go.mod` and `go.sum` for this dependency alignment, and should keep `go 1.24.4` "
            "with `toolchain go1.24.9` to match the original project. "
            "Import `k8s.io/client-go/gentype` and "
            "`k8s.io/client-go/listers` from dependencies; never vendor or fake external dependency packages such "
            "as `client-go/k8s.io/...` or `pkg/gentype`. Do not create or modify pkg/apis, hack scripts, Makefile, "
            "CI, Helm, Docker, docs, tests, or applyconfiguration files."
        )
    if ar.get("id") == "AR-036" and stage_id == "ST-5":
        ar_repair_policy = (
            " For AR-036, the minimum complete output is the real Dify plugin package under "
            "`integrations/dify-plugin/`: `manifest.yaml`, `main.py`, `requirements.txt`, `.difyignore`, "
            "`README.md`, `GUIDE.md`, `PRIVACY.md`, `provider/agentcube.yaml`, `provider/agentcube.py`, "
            "`tools/agentcube-code-interpreter.yaml`, `tools/agentcube-code-interpreter.py`, and valid PNG assets "
            "`_assets/icon.png` and `_assets/icon-dark.png`. Repair only this plugin package. The manifest must "
            "register `provider/agentcube.yaml`, the provider descriptor must register "
            "`tools/agentcube-code-interpreter.yaml`, the tool descriptor must expose router/workload manager URLs, "
            "language options python/javascript/typescript, code/command/session parameters, and the Python tool must "
            "delegate to `agentcube.CodeInterpreterClient`. Do not create PCAP analyzer files, FastAPI examples, "
            "Dockerfiles, Kubernetes deployment manifests, tests, source outside `integrations/dify-plugin/`, or "
            "`integrations/dify-plugin/examples/`."
        )
    if ar.get("id") == "AR-037" and stage_id == "ST-5":
        ar_repair_policy = (
            " For AR-037, the minimum complete output is the real PCAP analyzer example under "
            "`example/pcap-analyzer/`: `pcap_analyzer.py`, `requirements.txt`, `Dockerfile`, `deployment.yaml`, "
            "and `README.md`. Repair only this example. The Python app must define FastAPI app/startup, "
            "`AnalyzeResponse`, `/analyze`, `SandboxRunner`, planner/reporter prompts, `_plan_script`, "
            "`_repair_script`, `_execute_once_in_runner`, `_analyze_with_retries`, `_report`, and `uvicorn.run`; "
            "dependencies must be pinned as in the original, Dockerfile must use the `ghcr.io/astral-sh/uv` Python "
            "base and copy `sdk-python/agentcube`, and deployment must wire `OPENAI_API_KEY`, model, AgentCube URLs, "
            "resources, command, and args. Do not modify `integrations/dify-plugin` or create unrelated examples."
        )
    if ar.get("id") == "AR-038" and stage_id == "ST-5":
        ar_repair_policy = (
            " For AR-038, the minimum complete output is the real workloadmanager Go unit test set under "
            "`pkg/workloadmanager/`: `auth_test.go`, `client_cache_test.go`, `codeinterpreter_controller_test.go`, "
            "`handlers_test.go`, `k8s_client_test.go`, `runtimeclassname_test.go`, `sandbox_helper_test.go`, and "
            "`utils_test.go`. Repair only these `_test.go` files. Include the real table-driven auth/cache/client/"
            "controller/handler/Kubernetes pod/sandbox helper/random string tests from the original reference. The "
            "existing WorkloadManager production package must already be the real AR-008-complete production surface; "
            "do not add production shims inside tests or rewrite tests to fit a simplified implementation. Do not "
            "modify production Go files, go.mod/go.sum, other packages, E2E tests, Python tests, docs, or generated files."
        )
    if stage_id != "ST-5":
        repair_policy = (
            f"Fix only the requested SDD artifact(s) for {stage_id} under `changes/{ar['id']}/`. "
            "Do not create, modify, or delete project implementation/source files outside the change directory; "
            "implementation source is allowed only in ST-5."
        )
    else:
        if missing_implementation_note_only:
            repair_policy = (
                f"Only create or update `changes/{ar['id']}/implementation.md` by summarizing the source files "
                "already present in the workspace. Do not modify project source, install dependencies, run build tools, "
                "or add new docs/source files in this repair."
                f"{package_manager_policy}"
            )
        else:
            repair_policy = (
                f"Implementation source belongs under these allowed project paths: {allowed_paths}.{test_repair_policy} "
                "Repair only the validation errors listed above; do not expand scope or add unrelated files."
                f"{ar_repair_policy}{package_manager_policy}"
            )
    return (
        f"The previous attempt for {ar['id']} {stage_id} failed benchmark validation.\n"
        f"Validation errors:\n- " + "\n- ".join(errors) + "\n\n"
        f"Fix the workspace now. You must write the missing or incomplete files to disk. "
        f"Do not provide a narrative-only answer.\n\n"
        f"Important: `changes/{ar['id']}/` is only for SDD markdown/yaml artifacts. "
        f"Do not write any .go/.py/source implementation files under `changes/{ar['id']}/`. "
        f"{repair_policy}\n\n"
        "Use the original instructions below only as context; the repair policy above is narrower and takes precedence.\n\n"
        f"Original instructions:\n{original_prompt}"
    )


def _blocking_validation_errors(errors: list[str]) -> list[str]:
    return [
        err for err in errors
        if not any(err.startswith(prefix) for prefix in NON_BLOCKING_VALIDATION_PREFIXES)
    ]


def _dedupe_validation_errors(errors: list[str]) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for err in errors:
        if not err or err in seen:
            continue
        seen.add(err)
        deduped.append(err)
    return deduped


# ─── Engine ───────────────────────────────────────────────────────────────

def run_benchmark(
    tool: str,
    model: str,
    specs_dir: str,
    api_base: Optional[str] = None,
    ar_limit: Optional[int] = None,
    ar_offset: int = 0,
    dry_run_prompts: bool = False,
    original_repo: Optional[str] = None,
    checkpoint_each_ar: bool = False,
    stop_on_data_issue: bool = False,
    stop_on_validation_issue: bool = False,
    stage_model_map: Optional[dict[str, str]] = None,
    resume_from_checkpoint: Optional[str] = None,
    resume_workspace: Optional[str] = None,
) -> dict:
    """Execute the SDD-TEE benchmark.

    Args:
        tool: CLI tool name (claude-code, gemini-cli, cursor-cli, opencode-cli).
        model: Model identifier.
        specs_dir: Path to specs directory.
        api_base: LiteLLM Proxy URL (e.g. http://localhost:4000).
        ar_limit: Only run N ARs (for testing).
        ar_offset: Skip the first N ARs before applying ar_limit.
        dry_run_prompts: Print prompts without executing (testing only).
        original_repo: Path or URL to original agentcube source for equivalence verification.
        checkpoint_each_ar: Write an incremental JSON checkpoint after every AR.
        stop_on_data_issue: Stop after an AR if measurement/integrity audit fails.
        stage_model_map: Optional stage -> model override for mixed-model runs.

    Returns:
        Complete results dict matching SDD-TEE schema.
    """
    # Setup
    resume_data: Optional[dict] = None
    initial_ar_results: list[dict] = []
    resumed_duration = 0.0
    if resume_from_checkpoint:
        with open(resume_from_checkpoint, "r", encoding="utf-8") as f:
            resume_data = json.load(f)
        initial_ar_results = list(resume_data.get("ar_results", []))
        resumed_duration = float(
            resume_data.get("grand_totals", {}).get("total_duration_seconds", 0.0) or 0.0
        )
        if ar_offset == 0:
            ar_offset = len(initial_ar_results)

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_id = (
        resume_data.get("meta", {}).get("run_id")
        if resume_data
        else f"{tool}_{model.replace('/', '-')}_{ts}"
    )
    workspace = Path(resume_workspace).resolve() if resume_workspace else _workspace_root() / "v5.1" / run_id
    log_dir = BASE / "results" / "runs" / "v5.1" / f"{run_id}_logs"
    workspace.mkdir(parents=True, exist_ok=True)
    log_dir.mkdir(parents=True, exist_ok=True)
    _ensure_workspace_git_root(workspace)
    if resume_data and initial_ar_results:
        last_checkpoint_ar = initial_ar_results[-1].get("ar_id")
        if last_checkpoint_ar and _restore_workspace_checkpoint(workspace, run_id, last_checkpoint_ar):
            print(f"[OK] Restored workspace checkpoint: {run_id}_{last_checkpoint_ar}")

    # Always try to use the original agentcube source as the verification baseline.
    # This benchmark is meant to reconstruct that project, so running without a
    # baseline silently produces weak quality data.
    if not original_repo:
        original_repo = os.environ.get("SDD_TEE_ORIGINAL_REPO", DEFAULT_ORIGINAL_REPO)

    # Clone original repo if specified
    original_repo_path: Optional[Path] = None
    if original_repo:
        original_repo_path = _ensure_original_repo(original_repo, workspace)
        if original_repo_path:
            print(f"[OK] Original code reference: {original_repo_path}")

    # Copy specs to workspace
    specs_src = Path(specs_dir)
    if specs_src.exists():
        for item in specs_src.iterdir():
            if item.is_dir():
                dst = workspace / item.name
                if not dst.exists():
                    shutil.copytree(item, dst)
            else:
                shutil.copy2(item, workspace / item.name)

    # Limit ARs
    if ar_offset < 0:
        raise ValueError("--ar-offset must be >= 0")
    ars = AR_CATALOG[ar_offset:]
    if ar_limit:
        ars = ars[:ar_limit]

    print(f"\n{'='*70}")
    print(f"SDD-TEE v5.1 Benchmark: {tool} / {model}")
    print(f"Run ID:   {run_id}")
    print(f"Workspace: {workspace}")
    print(f"AR count: {len(ars)}")
    print(f"AR offset: {ar_offset}")
    if resume_data:
        print(f"Resume:   {len(initial_ar_results)} prior ARs from {resume_from_checkpoint}")
    print(f"Proxy:    {api_base or 'none (native only)'}")
    print(f"Dry run:  {dry_run_prompts}")
    print(f"Original: {original_repo or 'not specified'}")
    print(f"{'='*70}")

    # Init adapter + auditor
    adapter = create_adapter(tool, model, api_base)
    adapters_by_model = {model: adapter}
    specs_content = load_specs(specs_dir)
    print(f"Loaded {len(specs_content)} spec files")

    # LiteLLM proxy log path
    litellm_log = BASE / "results" / "litellm_requests.jsonl"
    auditor = TokenAuditor(str(litellm_log)) if api_base else None

    run_start = time.time()
    if initial_ar_results and not dry_run_prompts:
        _repair_partial_timeout_telemetry(initial_ar_results, adapter, log_dir)
    ar_results = initial_ar_results
    _eq_result = EquivalenceResult()  # default

    for i, ar in enumerate(ars):
        print(f"\n  [{i+1}/{len(ars)}] {ar['id']} {ar['name']} ({ar['size']})")
        ar_start = time.time()
        prev_outputs = {}
        stage_records = {}

        # Gather original code snippets for this AR's module (for ST-5 prompt)
        original_snippets = ""
        if original_repo_path:
            original_snippets = _gather_original_snippets(
                original_repo_path,
                ar["module"],
                ar["lang"],
                ar.get("id", ""),
            )

        for stage_id in STAGES:
            # ST-6.5 is programmatic verification, not a CLI stage
            if stage_id == "ST-6.5":
                stage_name = STAGE_NAMES_MAP[stage_id]
                if original_repo_path and not dry_run_prompts:
                    print(f"    {stage_id}: running equivalence check...")
                    eq_start = time.time()
                    checker = EquivalenceChecker(
                        str(original_repo_path), str(workspace), ar["lang"]
                    )
                    module_filter = None if ar["module"].strip("/") == "root" else ar["module"].split("/")[-1]
                    if ar["id"] == "AR-036":
                        module_filter = "integrations/dify-plugin"
                    elif ar["id"] == "AR-037":
                        module_filter = "example/pcap-analyzer"
                    eq_result = checker.verify(
                        ar_id=ar["id"],
                        ar_module=ar["module"],
                        module_filter=module_filter,
                    )
                    eq_end = time.time()
                    rec = StageRecord(stage=stage_id, stage_name=stage_name)
                    rec.duration_seconds = eq_end - eq_start
                    rec.data_source = "equivalence_check"
                    if eq_result.notes:
                        rec.validation_errors = [eq_result.notes]
                        rec.error = eq_result.notes
                    # Store equivalence result for quality metrics
                    _eq_result = eq_result
                    print(
                        f"      Coverage: {eq_result.file_coverage_pct}% | "
                        f"API: {eq_result.api_compliance_pct}% | "
                        f"Similarity: {eq_result.line_similarity_pct}% | "
                        f"Score: {eq_result.overall_score}"
                    )
                else:
                    rec = StageRecord(stage=stage_id, stage_name=STAGE_NAMES_MAP[stage_id])
                    rec.data_source = "none" if not original_repo_path else "dry_run"
                    _eq_result = EquivalenceResult()
                    if dry_run_prompts:
                        print(f"    [DRY] {stage_id}: skipped (no original repo in dry-run)")
                stage_records[stage_id] = rec
                prev_outputs[stage_id] = f"[Stage {stage_id} completed]"
                continue

            prompt = build_stage_prompt(ar, stage_id, specs_content, prev_outputs, original_snippets)
            log_file = log_dir / f"{ar['id']}_{stage_id}.log"
            stage_name = STAGE_NAMES_MAP[stage_id]
            stage_model = (stage_model_map or {}).get(stage_id, model)
            if stage_model not in adapters_by_model:
                adapters_by_model[stage_model] = create_adapter(tool, stage_model, api_base)
            stage_adapter = adapters_by_model[stage_model]

            if dry_run_prompts:
                suffix = f" model={stage_model}" if stage_model != model else ""
                print(f"    [DRY] {stage_id}: prompt length={len(prompt)}{suffix}")
                rec = StageRecord(stage=stage_id, stage_name=stage_name)
                rec.data_source = "dry_run"
                rec.model = stage_model
            else:
                suffix = f" [{stage_model}]" if stage_model != model else ""
                print(f"    {stage_id}: executing{suffix}...")
                stage_start = time.time()
                before_stage = _snapshot_workspace(workspace, ar["lang"])
                rec = StageRecord(stage=stage_id, stage_name=stage_name)
                rec.model = stage_model
                rec.attempts = 0
                validation_errors: list[str] = []
                stage_restored_files = 0
                stage_out_of_scope_files: set[str] = set()
                stage_reserved_files: set[str] = set()
                stage_forbidden_dependency_files: set[str] = set()

                # Run CLI tool with a small bounded repair window when required
                # artifacts, validators, or local checks fail. This keeps hollow
                # runs visible while still counting all repair tokens.
                current_prompt = prompt
                max_stage_attempts = _max_stage_attempts(stage_id)
                for attempt in range(1, max_stage_attempts + 1):
                    attempt_log = log_file if attempt == 1 else log_dir / f"{ar['id']}_{stage_id}.attempt{attempt}.log"
                    part = stage_adapter.run(
                        prompt=current_prompt,
                        workspace=str(workspace),
                        log_path=str(attempt_log),
                        stage=stage_id,
                        stage_name=stage_name,
                        timeout=_stage_timeout(stage_id),
                        max_retries=1,
                    )
                    part.attempts = 1
                    _merge_stage_record(rec, part)
                    attempt_execution_error = part.error or ""

                    after_attempt = _snapshot_workspace(workspace, ar["lang"])
                    delta = _snapshot_delta(before_stage, after_attempt)
                    forbidden_change_sources = _forbidden_change_source_files(
                        ar, delta["source_changed"]
                    )
                    forbidden_error = ""
                    if forbidden_change_sources:
                        _restore_workspace_files(workspace, before_stage, forbidden_change_sources)
                        after_attempt = _snapshot_workspace(workspace, ar["lang"])
                        delta = _snapshot_delta(before_stage, after_attempt)
                        forbidden_error = (
                            "source files written under changes/ and restored: "
                            + ", ".join(forbidden_change_sources[:10])
                        )
                    dependency_error = ""
                    if stage_id == "ST-5":
                        dependency_files = _forbidden_dependency_metadata_files(ar, delta["changed"])
                        if dependency_files:
                            stage_forbidden_dependency_files.update(dependency_files)
                            stage_restored_files += _restore_workspace_files(
                                workspace, before_stage, dependency_files
                            )
                            after_attempt = _snapshot_workspace(workspace, ar["lang"])
                            delta = _snapshot_delta(before_stage, after_attempt)
                            dependency_error = (
                                "dependency metadata modified outside AR scope and restored: "
                                + ", ".join(dependency_files[:10])
                            )
                    in_scope_impl, out_scope_impl = _in_scope_implementation_files(
                        ar, delta["implementation_changed"]
                    )
                    reserved_error = ""
                    if stage_id == "ST-5" and out_scope_impl:
                        stage_out_of_scope_files.update(out_scope_impl)
                        stage_restored_files += _restore_workspace_files(
                            workspace, before_stage, out_scope_impl
                        )
                        after_attempt = _snapshot_workspace(workspace, ar["lang"])
                        delta = _snapshot_delta(before_stage, after_attempt)
                        in_scope_impl, _ = _in_scope_implementation_files(
                            ar, delta["implementation_changed"]
                        )
                    if stage_id == "ST-5":
                        reserved_impl = _reserved_implementation_files(
                            ar, in_scope_impl + out_scope_impl
                        )
                        if reserved_impl:
                            stage_reserved_files.update(reserved_impl)
                            stage_restored_files += _restore_workspace_files(
                                workspace, before_stage, reserved_impl
                            )
                            after_attempt = _snapshot_workspace(workspace, ar["lang"])
                            delta = _snapshot_delta(before_stage, after_attempt)
                            in_scope_impl, out_scope_impl = _in_scope_implementation_files(
                                ar, delta["implementation_changed"]
                            )
                            reserved_error = (
                                "implementation modified files reserved for another AR and restored: "
                                + ", ".join(reserved_impl[:10])
                            )
                    scoped_loc_delta = _loc_delta_for_files(
                        before_stage, after_attempt, in_scope_impl
                    )
                    validation_errors = _validate_stage_output(
                        workspace, ar, stage_id, delta,
                        in_scope_impl=in_scope_impl,
                        out_scope_impl=out_scope_impl,
                        scoped_loc_delta=scoped_loc_delta,
                    )
                    if forbidden_error:
                        validation_errors.append(forbidden_error)
                    if dependency_error:
                        validation_errors.append(dependency_error)
                    if reserved_error:
                        validation_errors.append(reserved_error)
                    if attempt_execution_error:
                        validation_errors.append(
                            "stage execution error: " + attempt_execution_error
                        )
                    if stage_id == "ST-5":
                        rec.local_checks = _run_local_checks(workspace, ar)
                        local_failures = _failed_local_check_details(rec.local_checks)
                        if local_failures:
                            validation_errors.append(
                                "local checks failed: " + "; ".join(local_failures[:3])
                            )
                        generated_dirs, generated_files = _cleanup_generated_artifacts(workspace, before_stage)
                        if generated_dirs or generated_files:
                            after_attempt = _snapshot_workspace(workspace, ar["lang"])
                            delta = _snapshot_delta(before_stage, after_attempt)
                            in_scope_impl, out_scope_impl = _in_scope_implementation_files(
                                ar, delta["implementation_changed"]
                            )
                            scoped_loc_delta = _loc_delta_for_files(
                                before_stage, after_attempt, in_scope_impl
                            )
                            blocking_artifacts = _blocking_generated_artifacts(generated_dirs, generated_files)
                            if blocking_artifacts:
                                validation_errors.append(
                                    "generated dependency/build artifacts created and removed: "
                                    + ", ".join(blocking_artifacts[:8])
                                )
                    validation_errors = _dedupe_validation_errors(validation_errors)
                    if not validation_errors:
                        break
                    if attempt >= max_stage_attempts:
                        break
                    print(f"      validation failed; repair attempt {attempt}: {'; '.join(validation_errors[:3])}")
                    current_prompt = _repair_prompt(ar, stage_id, prompt, validation_errors)

                stage_end = time.time()
                rec.duration_seconds = stage_end - stage_start
                after_stage = _snapshot_workspace(workspace, ar["lang"])
                delta = _snapshot_delta(before_stage, after_stage)
                forbidden_change_sources = _forbidden_change_source_files(
                    ar, delta["source_changed"]
                )
                forbidden_error = ""
                forbidden_restored = 0
                if forbidden_change_sources:
                    forbidden_restored = _restore_workspace_files(workspace, before_stage, forbidden_change_sources)
                    after_stage = _snapshot_workspace(workspace, ar["lang"])
                    delta = _snapshot_delta(before_stage, after_stage)
                    forbidden_error = (
                        "source files written under changes/ and restored: "
                        + ", ".join(forbidden_change_sources[:10])
                    )
                dependency_error = ""
                if stage_id == "ST-5":
                    dependency_files = _forbidden_dependency_metadata_files(ar, delta["changed"])
                    if dependency_files:
                        stage_forbidden_dependency_files.update(dependency_files)
                        stage_restored_files += _restore_workspace_files(
                            workspace, before_stage, dependency_files
                        )
                        after_stage = _snapshot_workspace(workspace, ar["lang"])
                        delta = _snapshot_delta(before_stage, after_stage)
                        dependency_error = (
                            "dependency metadata modified outside AR scope and restored: "
                            + ", ".join(dependency_files[:10])
                        )
                in_scope_impl, out_scope_impl = _in_scope_implementation_files(
                    ar, delta["implementation_changed"]
                )
                reserved_error = ""
                if stage_id == "ST-5" and out_scope_impl:
                    stage_out_of_scope_files.update(out_scope_impl)
                    stage_restored_files += _restore_workspace_files(
                        workspace, before_stage, out_scope_impl
                    )
                    after_stage = _snapshot_workspace(workspace, ar["lang"])
                    delta = _snapshot_delta(before_stage, after_stage)
                    in_scope_impl, out_scope_impl = _in_scope_implementation_files(
                        ar, delta["implementation_changed"]
                    )
                if stage_id == "ST-5":
                    reserved_impl = _reserved_implementation_files(
                        ar, in_scope_impl + out_scope_impl
                    )
                    if reserved_impl:
                        stage_reserved_files.update(reserved_impl)
                        stage_restored_files += _restore_workspace_files(
                            workspace, before_stage, reserved_impl
                        )
                        after_stage = _snapshot_workspace(workspace, ar["lang"])
                        delta = _snapshot_delta(before_stage, after_stage)
                        in_scope_impl, out_scope_impl = _in_scope_implementation_files(
                            ar, delta["implementation_changed"]
                        )
                        reserved_error = (
                            "implementation modified files reserved for another AR and restored: "
                            + ", ".join(reserved_impl[:10])
                        )
                scoped_loc_delta = _loc_delta_for_files(before_stage, after_stage, in_scope_impl)
                non_impl_source_changes: list[str] = []
                if stage_id != "ST-5" and delta["implementation_changed"]:
                    non_impl_source_changes = delta["implementation_changed"]
                    rec.restored_files = _restore_workspace_files(
                        workspace, before_stage, non_impl_source_changes
                    )
                    after_stage = _snapshot_workspace(workspace, ar["lang"])
                    delta = _snapshot_delta(before_stage, after_stage)
                    in_scope_impl, out_scope_impl = _in_scope_implementation_files(
                        ar, delta["implementation_changed"]
                    )
                    scoped_loc_delta = _loc_delta_for_files(before_stage, after_stage, in_scope_impl)
                rec.changed_files = len(delta["changed"])
                rec.source_changed_files = len(in_scope_impl)
                rec.out_of_scope_files = max(
                    len(out_scope_impl),
                    len(stage_out_of_scope_files)
                    + len(stage_reserved_files)
                    + len(stage_forbidden_dependency_files),
                )
                rec.added_files = len(delta["added"])
                rec.restored_files += forbidden_restored + stage_restored_files
                rec.loc_delta = scoped_loc_delta
                if non_impl_source_changes:
                    validation_errors.append(
                        "project source modified outside ST-5 and restored: "
                        + ", ".join(non_impl_source_changes[:8])
                    )
                if forbidden_error:
                    validation_errors.append(forbidden_error)
                if dependency_error:
                    validation_errors.append(dependency_error)
                if reserved_error:
                    validation_errors.append(reserved_error)
                if stage_id == "ST-5":
                    if not rec.local_checks:
                        rec.local_checks = _run_local_checks(workspace, ar)
                    local_failures = _failed_local_check_details(rec.local_checks)
                    if local_failures:
                        validation_errors.append(
                            "local checks failed: " + "; ".join(local_failures[:3])
                        )
                    generated_dirs, generated_files = _cleanup_generated_artifacts(workspace, before_stage)
                    if generated_dirs or generated_files:
                        after_stage = _snapshot_workspace(workspace, ar["lang"])
                        delta = _snapshot_delta(before_stage, after_stage)
                        in_scope_impl, out_scope_impl = _in_scope_implementation_files(
                            ar, delta["implementation_changed"]
                        )
                        scoped_loc_delta = _loc_delta_for_files(before_stage, after_stage, in_scope_impl)
                        rec.changed_files = len(delta["changed"])
                        rec.source_changed_files = len(in_scope_impl)
                        rec.out_of_scope_files = max(
                            len(out_scope_impl),
                            len(stage_out_of_scope_files)
                            + len(stage_reserved_files)
                            + len(stage_forbidden_dependency_files),
                        )
                        rec.added_files = len(delta["added"])
                        rec.loc_delta = scoped_loc_delta
                    blocking_artifacts = _blocking_generated_artifacts(generated_dirs, generated_files)
                    if blocking_artifacts:
                        validation_errors.append(
                            "generated dependency/build artifacts created and removed: "
                            + ", ".join(blocking_artifacts[:8])
                            )
                if stage_id == "ST-6" and any("verification.md" in e for e in validation_errors):
                    checks = _run_local_checks(workspace, ar)
                    checks = _write_programmatic_verification(workspace, ar, validation_errors, checks)
                    rec.local_checks = checks
                    after_stage = _snapshot_workspace(workspace, ar["lang"])
                    delta = _snapshot_delta(before_stage, after_stage)
                    validation_errors = [
                        "model verification failed; harness generated verification.md"
                    ]
                if stage_id == "ST-6":
                    if not rec.local_checks:
                        rec.local_checks = _run_local_checks(workspace, ar)
                    local_failures = _failed_local_checks(rec.local_checks)
                    if local_failures:
                        validation_errors.append(
                            "local checks failed: " + "; ".join(local_failures[:3])
                        )
                if stage_id == "ST-7" and validation_errors:
                    _write_programmatic_archive(workspace, ar, validation_errors)
                    after_stage = _snapshot_workspace(workspace, ar["lang"])
                    delta = _snapshot_delta(before_stage, after_stage)
                    validation_errors = [
                        "model archive failed; harness generated archive notes"
                    ]
                in_scope_impl, out_scope_impl = _in_scope_implementation_files(
                    ar, delta["implementation_changed"]
                )
                validation_errors = _dedupe_validation_errors(validation_errors)
                rec.changed_files = len(delta["changed"])
                rec.source_changed_files = len(in_scope_impl)
                rec.out_of_scope_files = max(
                    len(out_scope_impl),
                    len(stage_out_of_scope_files)
                    + len(stage_reserved_files)
                    + len(stage_forbidden_dependency_files),
                )
                rec.added_files = len(delta["added"])
                rec.loc_delta = _loc_delta_for_files(before_stage, after_stage, in_scope_impl)
                rec.validation_errors = validation_errors
                if validation_errors:
                    msg = "validation failed: " + "; ".join(validation_errors)
                    rec.error = msg if not rec.error else f"{rec.error}; {msg}"
                elif rec.error and rec.attempts > 1 and rec.exit_code in (0, "0"):
                    # A later repair attempt completed successfully and passed
                    # validation/local checks; do not let a stale earlier
                    # timeout or CLI error poison the final AR quality data.
                    rec.error = None

                # ─── Authoritative: audit LiteLLM proxy log ───
                if auditor and api_base:
                    proxy_audit = auditor.get_tokens(stage_model, stage_start, stage_end)
                    if proxy_audit.api_calls > 0:
                        # Overwrite native data with proxy data (authoritative)
                        rec.input_tokens = proxy_audit.input_tokens
                        rec.output_tokens = proxy_audit.output_tokens
                        rec.cache_read_tokens = proxy_audit.cache_read_tokens
                        rec.cache_write_tokens = proxy_audit.cache_write_tokens
                        rec.cost_usd = proxy_audit.compute_cost(model)
                        rec.api_calls = proxy_audit.api_calls
                        rec.iterations = proxy_audit.api_calls
                        rec.data_source = "litellm_proxy"
                        print(
                            f"      [Proxy] in={proxy_audit.input_tokens:,} "
                            f"out={proxy_audit.output_tokens:,} "
                            f"cache={proxy_audit.cache_read_tokens:,} "
                            f"calls={proxy_audit.api_calls}"
                        )

                if rec.error:
                    print(f"      WARNING: {rec.error}")
                print(
                    f"      changed={rec.changed_files} added={rec.added_files} "
                    f"loc_delta={rec.loc_delta} attempts={rec.attempts}"
                )

            stage_records[stage_id] = rec
            blocking_validation_errors = _blocking_validation_errors(rec.validation_errors or [])
            if (
                stop_on_validation_issue
                and not dry_run_prompts
                and blocking_validation_errors
            ):
                print(f"  VALIDATION GATE: FAIL at {stage_id}")
                for issue in blocking_validation_errors[:12]:
                    print(f"    - {issue}")
                raise RuntimeError(
                    f"Validation gate failed during {ar['id']} {stage_id}; rerun this AR after fixing the issue."
                )
            artifacts = _read_stage_artifacts(workspace, ar["id"])
            prev_outputs = artifacts or prev_outputs

        ar_end = time.time()

        # ─── Reconcile: re-parse logs to correct api_calls ────────────────
        if not dry_run_prompts:
            reconcile_stage_records(adapter, str(log_dir), stage_records, ar["id"])

        # ─── Compute AR totals ────────────────────────────────────────────
        totals = {
            "input_tokens": sum(r.input_tokens for r in stage_records.values()),
            "output_tokens": sum(r.output_tokens for r in stage_records.values()),
            "cache_read_tokens": sum(r.cache_read_tokens for r in stage_records.values()),
            "cache_write_tokens": sum(r.cache_write_tokens for r in stage_records.values()),
            "total_tokens": sum(
                r.input_tokens + r.output_tokens + r.cache_read_tokens + r.cache_write_tokens
                for r in stage_records.values()
            ),
            "human_input_tokens": 0,
            "spec_context_tokens": 0,
            "iterations": sum(r.iterations for r in stage_records.values()),
            "duration_seconds": round(ar_end - ar_start, 2),
            "api_calls": sum(r.api_calls for r in stage_records.values()),
            "cost_usd": 0.0,
        }

        # Compute cost from real pricing
        if any(r.cost_usd for r in stage_records.values()):
            totals["cost_usd"] = round(sum(r.cost_usd for r in stage_records.values()), 4)
        else:
            totals["cost_usd"] = round(
                compute_token_cost(
                    model,
                    totals["input_tokens"],
                    totals["output_tokens"],
                    totals["cache_read_tokens"],
                    totals["cache_write_tokens"],
                ),
                4,
            )

        # Physical LOC scan. Per-AR output is the implementation-stage delta,
        # not cumulative workspace LOC, to avoid counting earlier ARs again.
        workspace_loc, workspace_files = _scan_loc(workspace, ar["lang"])
        st5_record = stage_records.get("ST-5", StageRecord())
        actual_loc = st5_record.loc_delta
        actual_files = st5_record.source_changed_files
        if ar.get("id") == "AR-036":
            actual_files = _ar036_dify_plugin_file_count(workspace) or actual_files
        if ar.get("id") == "AR-037":
            actual_files = _ar037_pcap_analyzer_file_count(workspace) or actual_files

        # Quality metrics from equivalence check, adjusted by benchmark
        # validation failures. Equivalence is cumulative within a workspace, so
        # a nearly-empty AR can appear equivalent because earlier ARs already
        # generated files in the same module. Implementation-stage validation
        # must therefore cap the per-AR quality score.
        eq_data = _eq_result if '_eq_result' in dir() else EquivalenceResult()
        st5_errors = stage_records.get("ST-5", StageRecord()).validation_errors or []
        st6_errors = stage_records.get("ST-6", StageRecord()).validation_errors or []
        all_validation_errors = [
            err
            for record in stage_records.values()
            for err in (record.validation_errors or [])
        ]
        stage_execution_errors = [
            f"{sid}: {record.error}"
            for sid, record in stage_records.items()
            if sid != "ST-6.5" and record.error and not (record.validation_errors or [])
        ]
        local_check_failed = any(
            "local checks failed" in e
            for e in (st5_errors + st6_errors + all_validation_errors)
        )
        implementation_failed = bool(st5_errors)
        model_verification_failed = any("model verification failed" in e for e in st6_errors)
        consistency_score = eq_data.overall_score / 100 if eq_data.overall_score > 0 else 0
        code_usability = eq_data.api_compliance_pct / 100 if eq_data.api_compliance_pct > 0 else 0
        if implementation_failed:
            consistency_score = min(consistency_score, 0.25)
            code_usability = min(code_usability, 0.25)
        if local_check_failed:
            consistency_score = min(consistency_score, 0.2)
            code_usability = 0
        elif model_verification_failed:
            consistency_score = min(consistency_score, 0.8)
        equivalence_notes = getattr(eq_data, "notes", "")
        docs_build_validated = (
            ar.get("module") == "docs"
            and ar.get("lang") in {"TypeScript", "Markdown"}
            and not implementation_failed
            and not local_check_failed
            and not model_verification_failed
        )
        if docs_build_validated:
            # Documentation ARs are validated by manifest/path checks and a real
            # Docusaurus build. API-symbol equivalence is not meaningful here.
            consistency_score = max(consistency_score, 0.8)
            code_usability = max(code_usability, 0.85)
            equivalence_notes = (
                "Documentation AR validated by AR-specific manifest checks and Docusaurus build; "
                "API contract compliance metric is not applicable."
            )
        quality = {
            "consistency_score": consistency_score,
            "consistency_pct": round(consistency_score * 100, 2),
            "code_usability": code_usability,
            "test_coverage": 0,  # Requires running actual tests
            "bugs_found": 0,
            "implementation_valid": not implementation_failed,
            "local_checks_passed": not local_check_failed,
            "validation_error_count": len(all_validation_errors) + len(stage_execution_errors),
            "critical_validation_errors": st5_errors + [
                e for e in st6_errors if "local checks failed" in e or "model verification failed" in e
            ] + stage_execution_errors,
            "original_code_coverage": eq_data.file_coverage_pct,
            "api_contract_compliance": eq_data.api_compliance_pct,
            "line_similarity": eq_data.line_similarity_pct,
            "matched_files": len(eq_data.matched_files),
            "unmatched_original": len(eq_data.unmatched_original),
            "module_path_match": getattr(eq_data, "module_path_match", True),
            "original_module_path": getattr(eq_data, "original_module_path", ""),
            "generated_module_path": getattr(eq_data, "generated_module_path", ""),
            "equivalence_notes": equivalence_notes,
        }

        ar_result = {
            "ar_id": ar["id"],
            "ar_name": ar["name"],
            "module": ar["module"],
            "lang": ar["lang"],
            "type": ar["type"],
            "size": ar["size"],
            "stages": {
                k: {
                    "input_tokens": v.input_tokens,
                    "output_tokens": v.output_tokens,
                    "cache_read_tokens": v.cache_read_tokens,
                    "cache_write_tokens": v.cache_write_tokens,
                    "total_tokens": (
                        v.input_tokens + v.output_tokens
                        + v.cache_read_tokens + v.cache_write_tokens
                    ),
                    "human_input_tokens": 0,
                    "spec_context_tokens": 0,
                    "iterations": v.iterations,
                    "duration_seconds": round(v.duration_seconds, 2),
                    "api_calls": v.api_calls,
                    "cost_usd": round(v.cost_usd, 6),
                    "model": getattr(v, "model", model),
                    "data_source": v.data_source,
                    "exit_code": v.exit_code,
                    "attempts": v.attempts,
                    "changed_files": v.changed_files,
                    "source_changed_files": v.source_changed_files,
                    "added_files": v.added_files,
                    "restored_files": v.restored_files,
                    "out_of_scope_files": v.out_of_scope_files,
                    "loc_delta": v.loc_delta,
                    "validation_errors": v.validation_errors,
                    "local_checks": v.local_checks,
                    "error": v.error,
                }
                for k, v in stage_records.items()
            },
            "totals": totals,
            "output": {
                "actual_loc": actual_loc,
                "actual_files": actual_files,
                "workspace_loc": workspace_loc,
                "workspace_files": workspace_files,
                "tasks_count": ar.get("est_tasks", 0),
            },
            "quality": quality,
            "metrics": {},
        }
        ar_result["metrics"] = _compute_ar_metrics(ar_result)
        ar_results.append(ar_result)

        print(
            f"  AR totals: {totals['total_tokens']:,} tokens, "
            f"{actual_loc} LOC, {actual_files} files"
        )
        if checkpoint_each_ar or stop_on_data_issue:
            partial = _build_run_data(
                tool=tool,
                model=model,
                run_id=run_id,
                ar_offset=ar_offset,
                api_base=api_base,
                dry_run_prompts=dry_run_prompts,
                ar_results=ar_results,
                total_duration=resumed_duration + (time.time() - run_start),
                stage_model_map=stage_model_map,
            )
            checkpoint_dir = BASE / "results" / "runs" / "v5.1" / "checkpoints"
            checkpoint_dir.mkdir(parents=True, exist_ok=True)
            checkpoint_path = checkpoint_dir / f"{run_id}_{ar['id']}_checkpoint.json"
            _save_run_data(partial, checkpoint_path)
            issues = _audit_incremental_data(partial, ar_result, dry_run_prompts)
            validation_issues = _audit_critical_validation_data(ar_result, dry_run_prompts)
            if issues:
                failed_path = checkpoint_dir / f"{run_id}_{ar['id']}_failed.json"
                _save_run_data(partial, failed_path)
                print(f"  DATA AUDIT: FAIL ({len(issues)} issue(s))")
                for issue in issues[:12]:
                    print(f"    - {issue}")
                print(f"  Checkpoint: {failed_path}")
                if stop_on_data_issue:
                    raise RuntimeError(
                        f"Data audit failed after {ar['id']}; fix current issue and rerun this AR before continuing."
                    )
            elif validation_issues:
                failed_path = checkpoint_dir / f"{run_id}_{ar['id']}_failed.json"
                _save_run_data(partial, failed_path)
                print(f"  DATA AUDIT: PASS → {checkpoint_path}")
                print(f"  VALIDATION GATE: FAIL ({len(validation_issues)} issue(s))")
                for issue in validation_issues[:12]:
                    print(f"    - {issue}")
                print(f"  Checkpoint: {failed_path}")
                if stop_on_validation_issue:
                    raise RuntimeError(
                        f"Validation gate failed after {ar['id']}; fix current issue and rerun this AR before continuing."
                    )
            else:
                workspace_checkpoint = _save_workspace_checkpoint(workspace, run_id, ar["id"])
                if workspace_checkpoint:
                    print(f"  WORKSPACE CHECKPOINT: {workspace_checkpoint}")
                print(f"  DATA AUDIT: PASS → {checkpoint_path}")

    total_duration = resumed_duration + (time.time() - run_start)
    data = _build_run_data(
        tool=tool,
        model=model,
        run_id=run_id,
        ar_offset=ar_offset,
        api_base=api_base,
        dry_run_prompts=dry_run_prompts,
        ar_results=ar_results,
        total_duration=total_duration,
        stage_model_map=stage_model_map,
    )

    # Save
    output_dir = BASE / "results" / "runs" / "v5.1"
    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / f"{run_id}_full.json"
    _save_run_data(data, out_path)

    print(f"\n{'='*70}")
    print(f"Run complete: {run_id}")
    print(f"  Total tokens: {data['grand_totals']['total_tokens']:,}")
    print(f"  Total cost:   ${data['grand_totals']['total_cost_usd']:.4f}")
    print(f"  Total LOC:    {data['grand_totals']['total_loc']:,}")
    print(f"  Duration:     {total_duration/60:.1f}m")
    print(f"  Saved → {out_path}")
    print(f"{'='*70}")

    return data


def _build_run_data(
    *,
    tool: str,
    model: str,
    run_id: str,
    ar_offset: int,
    api_base: Optional[str],
    dry_run_prompts: bool,
    ar_results: list[dict],
    total_duration: float,
    stage_model_map: Optional[dict[str, str]] = None,
) -> dict:
    """Build a schema-compatible run document for full or partial runs."""
    grand = {
        "ar_count": len(ar_results),
        "input_tokens": sum(r["totals"]["input_tokens"] for r in ar_results),
        "output_tokens": sum(r["totals"]["output_tokens"] for r in ar_results),
        "cache_read_tokens": sum(r["totals"]["cache_read_tokens"] for r in ar_results),
        "cache_write_tokens": sum(r["totals"]["cache_write_tokens"] for r in ar_results),
        "total_tokens": sum(r["totals"]["total_tokens"] for r in ar_results),
        "human_input_tokens": sum(r["totals"]["human_input_tokens"] for r in ar_results),
        "spec_context_tokens": sum(r["totals"]["spec_context_tokens"] for r in ar_results),
        "total_duration_seconds": round(total_duration, 2),
        "total_cost_usd": round(sum(r["totals"]["cost_usd"] for r in ar_results), 4),
        "total_cost_cny": round(sum(r["totals"]["cost_usd"] for r in ar_results) * 7.2, 4),
        "total_loc": sum(r["output"]["actual_loc"] for r in ar_results),
        "total_files": sum(r["output"]["actual_files"] for r in ar_results),
        "total_tasks": sum(r["output"]["tasks_count"] for r in ar_results),
        "total_iterations": sum(r["totals"]["iterations"] for r in ar_results),
        "total_api_calls": sum(r["totals"]["api_calls"] for r in ar_results),
    }

    stage_agg = {}
    for sid in STAGES:
        stage_agg[sid] = {
            "name": STAGE_NAMES_MAP[sid],
            "total_tokens": sum(r["stages"][sid]["total_tokens"] for r in ar_results),
            "input_tokens": sum(r["stages"][sid]["input_tokens"] for r in ar_results),
            "output_tokens": sum(r["stages"][sid]["output_tokens"] for r in ar_results),
            "cache_read_tokens": sum(r["stages"][sid]["cache_read_tokens"] for r in ar_results),
            "cache_write_tokens": sum(r["stages"][sid]["cache_write_tokens"] for r in ar_results),
            "duration_seconds": round(sum(r["stages"][sid]["duration_seconds"] for r in ar_results), 2),
            "iterations": sum(r["stages"][sid]["iterations"] for r in ar_results),
            "api_calls": sum(r["stages"][sid]["api_calls"] for r in ar_results),
            "cost_usd": round(sum(r["stages"][sid].get("cost_usd", 0.0) for r in ar_results), 4),
        }

    return {
        "meta": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "is_mock": dry_run_prompts,
            "framework": "SDD-TEE v5.1",
            "methodology": "CodeSpec 7-Stage + OpenSpec OPSX + LiteLLM Proxy",
            "target_project": "agentcube",
            "tool": tool,
            "model": model,
            "run_id": run_id,
            "ar_offset": ar_offset,
            "stage_model_map": stage_model_map or {},
            "token_tracking": "LiteLLM Proxy per-request audit (authoritative) + native CLI parsing (fallback)",
            "litellm_proxy": api_base is not None,
            "api_base": api_base,
            "data_integrity": "All token data from real API responses. No fabrication.",
        },
        "ar_catalog": AR_CATALOG,
        "ar_results": ar_results,
        "grand_totals": grand,
        "stage_aggregates": stage_agg,
        "baselines": _compute_baselines(ar_results),
    }


def _save_run_data(data: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _cache_hit_rate(values: dict) -> float:
    return values.get("cache_read_tokens", 0) / max(
        values.get("input_tokens", 0) + values.get("cache_read_tokens", 0),
        1,
    )


def _audit_incremental_data(data: dict, latest_ar: dict, dry_run_prompts: bool) -> list[str]:
    """Gate after every AR. This audits measurement integrity, not model success."""
    issues: list[str] = []
    try:
        from schema import SchemaError, validate_report_data
        validate_report_data(data)
    except SchemaError as exc:
        issues.extend(str(exc).splitlines())

    totals = latest_ar.get("totals", {})
    if not dry_run_prompts:
        if totals.get("total_tokens", 0) <= 0:
            issues.append(f"{latest_ar['ar_id']}: total_tokens is zero")
        if totals.get("api_calls", 0) <= 0:
            issues.append(f"{latest_ar['ar_id']}: api_calls is zero")
        if get_pricing(data["meta"].get("model", "")) and totals.get("cost_usd", 0) <= 0:
            issues.append(f"{latest_ar['ar_id']}: cost_usd is zero despite known model pricing")

    if not 0 <= _cache_hit_rate(totals) <= 1:
        issues.append(f"{latest_ar['ar_id']}: cache_hit_rate is outside [0, 1]")

    stage_sum = {
        "input_tokens": 0,
        "output_tokens": 0,
        "cache_read_tokens": 0,
        "cache_write_tokens": 0,
        "total_tokens": 0,
        "api_calls": 0,
    }
    for sid, stage in latest_ar.get("stages", {}).items():
        expected_total = (
            stage.get("input_tokens", 0)
            + stage.get("output_tokens", 0)
            + stage.get("cache_read_tokens", 0)
            + stage.get("cache_write_tokens", 0)
        )
        if stage.get("total_tokens", expected_total) != expected_total:
            issues.append(f"{latest_ar['ar_id']} {sid}: token components do not sum to total_tokens")
        if sid != "ST-6.5" and not dry_run_prompts and stage.get("api_calls", 0) <= 0:
            issues.append(f"{latest_ar['ar_id']} {sid}: missing API calls/token telemetry")
        for key in stage_sum:
            stage_sum[key] += stage.get(key, 0)

    for key, expected in stage_sum.items():
        if totals.get(key, expected) != expected:
            issues.append(f"{latest_ar['ar_id']}: totals.{key} != stage sum ({totals.get(key)} != {expected})")

    quality = latest_ar.get("quality", {})
    st5_errors = latest_ar.get("stages", {}).get("ST-5", {}).get("validation_errors") or []
    st6_errors = latest_ar.get("stages", {}).get("ST-6", {}).get("validation_errors") or []
    all_validation_errors = [
        err
        for stage in latest_ar.get("stages", {}).values()
        for err in (stage.get("validation_errors") or [])
    ]
    execution_errors = [
        stage.get("error")
        for sid, stage in latest_ar.get("stages", {}).items()
        if sid != "ST-6.5" and stage.get("error") and not (stage.get("validation_errors") or [])
    ]
    if not dry_run_prompts:
        if latest_ar.get("output", {}).get("actual_loc", 0) == 0 and quality.get("implementation_valid") is True:
            issues.append(f"{latest_ar['ar_id']}: zero-LOC implementation marked valid")
        if st5_errors and quality.get("implementation_valid") is True:
            issues.append(f"{latest_ar['ar_id']}: ST-5 errors not reflected in implementation_valid")
        if st5_errors and quality.get("consistency_score", 0) > 0.25:
            issues.append(f"{latest_ar['ar_id']}: implementation failure did not cap consistency_score")
        if any("local checks failed" in e for e in all_validation_errors):
            if quality.get("local_checks_passed") is True:
                issues.append(f"{latest_ar['ar_id']}: local check failure not reflected in quality")
            if quality.get("code_usability", 0) != 0:
                issues.append(f"{latest_ar['ar_id']}: local check failure did not set code_usability=0")
    all_stage_errors = all_validation_errors + [e for e in execution_errors if e]
    if all_stage_errors and quality.get("validation_error_count", 0) == 0:
        issues.append(f"{latest_ar['ar_id']}: stage validation errors not counted in quality")
    return issues


def _audit_critical_validation_data(latest_ar: dict, dry_run_prompts: bool) -> list[str]:
    """Gate model-output failures separately from token/cost telemetry issues."""
    if dry_run_prompts:
        return []

    issues: list[str] = []
    ar_id = latest_ar.get("ar_id", "AR")
    stages = latest_ar.get("stages", {})
    st5 = stages.get("ST-5", {})
    st5_errors = st5.get("validation_errors") or []
    output = latest_ar.get("output", {})
    quality = latest_ar.get("quality", {})

    for sid, stage in stages.items():
        if sid == "ST-6.5":
            continue
        for err in stage.get("validation_errors") or []:
            issues.append(f"{ar_id} {sid}: validation error: {err}")
        stage_error = stage.get("error") or ""
        if stage_error and not (stage.get("validation_errors") or []):
            issues.append(f"{ar_id} {sid}: stage execution error: {stage_error[:240]}")
    if st5_errors:
        preview = "; ".join(st5_errors[:3])
        issues.append(f"{ar_id}: ST-5 implementation failed validation: {preview}")
    if quality.get("implementation_valid") is False:
        issues.append(f"{ar_id}: implementation_valid=false")
    if output.get("actual_files", 0) <= 0:
        issues.append(f"{ar_id}: implementation changed zero in-scope source files")
    if output.get("actual_loc", 0) <= 0:
        issues.append(f"{ar_id}: implementation LOC delta is zero")

    return issues


def _scan_loc(workspace: Path, lang: str) -> tuple[int, int]:
    """Scan workspace for generated code files (exclude vendor, cache, agentcube-src)."""
    loc = 0
    files = 0

    for dirpath, dirnames, filenames in os.walk(workspace):
        # Prune skip dirs
        dirnames[:] = [d for d in dirnames if d not in SKIP_SCAN_DIRS and d != "changes"]
        for fn in filenames:
            if fn in LOCKFILE_NAMES:
                continue
            fpath = Path(dirpath) / fn
            if not _is_source_like(fpath, lang):
                continue
            try:
                with open(fpath, errors="replace") as f:
                    loc += sum(1 for _ in f)
                files += 1
            except (OSError, UnicodeDecodeError):
                pass
    return loc, files


def _compute_ar_metrics(ar: dict) -> dict:
    """Compute 5-dimension metrics for one AR."""
    stages = ar["stages"]
    totals = ar["totals"]
    out = ar["output"]
    quality = ar.get("quality", {})

    st5 = stages.get("ST-5", {}).get("total_tokens", 0)
    total = totals["total_tokens"]
    cache_hit_rate = totals.get("cache_read_tokens", 0) / max(
        totals.get("input_tokens", 0) + totals.get("cache_read_tokens", 0),
        1,
    )
    loc = max(out["actual_loc"], 1)
    nf = max(out["actual_files"], 1)
    tasks = max(out["tasks_count"], 1)
    dur_h = max(totals["duration_seconds"] / 3600, 0.001)

    # Quality metrics: derive from quality dict, not from raw token counts
    # When no equivalence check ran, all quality fields are 0 → set metrics to 0 (unmeasured)
    has_quality = quality.get("consistency_score", 0) > 0 or quality.get("test_coverage", 0) > 0
    if has_quality:
        qt_cov = round(quality.get("test_coverage", 0) * 100, 2)
        qt_consist = round(quality.get("consistency_score", 0) * 100, 2)
        qt_avail = round(quality.get("code_usability", 0) * 100, 2)
        qt_bug = round(max(0, 100 - quality.get("consistency_score", 0) * 100), 2)
    else:
        qt_cov = 0
        qt_consist = 0
        qt_avail = 0
        qt_bug = 0  # Not measured, not "100 bugs found"

    return {
        "ET_LOC": round(st5 / loc, 2),
        "ET_FILE": round(st5 / nf, 2),
        "ET_TASK": round(st5 / tasks, 2),
        "ET_AR": round(total, 2),
        "ET_TIME": round(total / dur_h, 2),
        "ET_COST_LOC": round(totals["cost_usd"] / (loc / 1000), 2) if loc > 0 else 0,
        "RT_RATIO": 0,  # Requires human input tracking
        "RT_ITER": round(totals["iterations"], 2),
        "QT_COV": qt_cov,
        "QT_CONSIST": qt_consist,
        "QT_AVAIL": qt_avail,
        "QT_BUG": qt_bug,
        "PT_DESIGN": round(
            sum(stages.get(s, {}).get("total_tokens", 0) for s in ["ST-1", "ST-2", "ST-3"])
            / max(total, 1), 4
        ),
        "PT_PLAN": round(
            sum(stages.get(s, {}).get("total_tokens", 0) for s in ["ST-0", "ST-4"])
            / max(total, 1), 4
        ),
        "PT_DEV": round(st5 / max(total, 1), 4),
        "PT_VERIFY": round(
            sum(stages.get(s, {}).get("total_tokens", 0) for s in ["ST-6", "ST-6.5", "ST-7"])
            / max(total, 1), 4
        ),
        "PT_CACHE": round(cache_hit_rate, 4),
    }


def _compute_baselines(ar_results: list) -> dict:
    """Compute size-stratified baselines."""
    groups = {"S": [], "M": [], "L": []}
    for ar in ar_results:
        size = ar["size"]
        if size in groups:
            groups[size].append(ar.get("metrics", {}))

    result = {}
    for size, metrics_list in groups.items():
        if not metrics_list:
            result[size] = {"count": 0}
            continue
        result[size] = {"count": len(metrics_list)}
        for key in metrics_list[0]:
            vals = [m[key] for m in metrics_list if isinstance(m.get(key), (int, float))]
            if vals:
                result[size][f"{key}_mean"] = round(sum(vals) / len(vals), 2)
                result[size][f"{key}_min"] = round(min(vals), 2)
                result[size][f"{key}_max"] = round(max(vals), 2)
    return result


# ─── Original code helpers ─────────────────────────────────────────────

def _ensure_original_repo(original_repo: str, workspace: Path) -> Optional[Path]:
    """Ensure original agentcube source is available outside the generated workspace.

    Supports:
    - Local path: returns the path directly
    - Git URL: clones/updates a cache under .cache/original/agentcube

    Returns path to original source, or None if unavailable.
    """
    # Local path
    local = Path(original_repo)
    if local.exists() and local.is_dir():
        return local.resolve()

    # Git URL — try to clone
    if original_repo.startswith(("http://", "https://", "git@")):
        cache_root = BASE / ".cache" / "original"
        target = cache_root / "agentcube"
        if target.exists():
            return target
        try:
            cache_root.mkdir(parents=True, exist_ok=True)
            subprocess.run(
                ["git", "clone", "--depth", "1", original_repo, str(target)],
                check=True, timeout=120, capture_output=True,
            )
            return target
        except Exception as e:
            print(f"[WARN] Could not clone original repo: {e}")
            return None

    print(f"[WARN] Original repo path/URL not found: {original_repo}")
    return None


def _gather_original_snippets(original_path: Path, module: str, lang: str, ar_id: str = "") -> str:
    """Extract relevant code snippets from original source for a given module.

    Returns formatted text with file paths and content.
    """
    if module.strip("/") == "integrations":
        plugin_root = original_path / "integrations" / "dify-plugin"
        snippets = []
        if plugin_root.exists():
            for fpath in sorted(plugin_root.rglob("*")):
                if not fpath.is_file():
                    continue
                rel = fpath.relative_to(original_path)
                try:
                    if fpath.suffix.lower() == ".png":
                        data = fpath.read_bytes()
                        snippets.append(
                            f"--- {rel} ---\n<PNG asset: {len(data)} bytes; create a valid non-empty PNG asset at this path>"
                        )
                    else:
                        snippets.append(f"--- {rel} ---\n{fpath.read_text(encoding='utf-8', errors='replace')}")
                except OSError:
                    pass
        return "\n\n".join(snippets) if snippets else ""

    if module.strip("/") == "example":
        example_root = original_path / "example" / "pcap-analyzer"
        snippets = []
        if example_root.exists():
            for fpath in sorted(example_root.rglob("*")):
                if not fpath.is_file():
                    continue
                try:
                    rel = fpath.relative_to(original_path)
                    snippets.append(f"--- {rel} ---\n{fpath.read_text(encoding='utf-8', errors='replace')}")
                except OSError:
                    pass
        return "\n\n".join(snippets) if snippets else ""

    if module.strip("/") == "pkg/workloadmanager":
        workload_root = original_path / "pkg" / "workloadmanager"
        snippets = []
        if workload_root.exists():
            if ar_id == "AR-038":
                paths = sorted(workload_root.glob("*_test.go"))
            else:
                production_paths = {
                    fpath.name: fpath
                    for fpath in workload_root.glob("*.go")
                    if not fpath.name.endswith("_test.go")
                }
                ordered_names = [
                    name for name in WORKLOADMANAGER_REFERENCE_ORDER_BY_AR.get(ar_id, [])
                    if name in production_paths
                ]
                if ar_id == "AR-008" or not ordered_names:
                    ordered_names.extend(
                        sorted(name for name in production_paths if name not in set(ordered_names))
                    )
                paths = [production_paths[name] for name in ordered_names]
            for fpath in paths:
                try:
                    rel = fpath.relative_to(original_path)
                    snippets.append(f"--- {rel} ---\n{fpath.read_text(encoding='utf-8', errors='replace')}")
                except OSError:
                    pass
            if ar_id != "AR-038":
                for rel_name in [
                    "pkg/common/types/types.go",
                    "pkg/common/types/sandbox.go",
                    "go.mod",
                ]:
                    fpath = original_path / rel_name
                    if not fpath.is_file():
                        continue
                    try:
                        rel = fpath.relative_to(original_path)
                        snippets.append(f"--- {rel} ---\n{fpath.read_text(encoding='utf-8', errors='replace')}")
                    except OSError:
                        pass
        return "\n\n".join(snippets) if snippets else ""

    if module.strip("/") == "pkg/router":
        router_root = original_path / "pkg" / "router"
        snippets = []
        if router_root.exists():
            production_paths = {
                fpath.name: fpath
                for fpath in router_root.glob("*.go")
                if not fpath.name.endswith("_test.go")
            }
            ordered_names = [
                name for name in ROUTER_REFERENCE_ORDER_BY_AR.get(ar_id, [])
                if name in production_paths
            ]
            if not ordered_names:
                ordered_names = sorted(production_paths)
            paths = [production_paths[name] for name in ordered_names]
            for fpath in paths:
                try:
                    rel = fpath.relative_to(original_path)
                    snippets.append(f"--- {rel} ---\n{fpath.read_text(encoding='utf-8', errors='replace')}")
                except OSError:
                    pass
            if ar_id == "AR-010":
                api_errors = original_path / "pkg" / "api" / "errors.go"
                if api_errors.is_file():
                    try:
                        rel = api_errors.relative_to(original_path)
                        snippets.append(f"--- {rel} ---\n{api_errors.read_text(encoding='utf-8', errors='replace')}")
                    except OSError:
                        pass
            if ar_id == "AR-011":
                go_mod = original_path / "go.mod"
                if go_mod.is_file():
                    try:
                        rel = go_mod.relative_to(original_path)
                        snippets.append(f"--- {rel} ---\n{go_mod.read_text(encoding='utf-8', errors='replace')}")
                    except OSError:
                        pass
        return "\n\n".join(snippets) if snippets else ""

    if module.strip("/") == "pkg/store":
        store_root = original_path / "pkg" / "store"
        snippets = []
        if store_root.exists():
            production_paths = {
                fpath.name: fpath
                for fpath in store_root.glob("*.go")
                if not fpath.name.endswith("_test.go")
            }
            test_paths = {
                fpath.name: fpath
                for fpath in store_root.glob("*_test.go")
            }
            ordered_names = [
                name for name in STORE_REFERENCE_ORDER_BY_AR.get(ar_id, [])
                if name in production_paths or name in test_paths
            ]
            if not ordered_names:
                ordered_names = sorted(production_paths)
            for name in ordered_names:
                fpath = production_paths.get(name) or test_paths.get(name)
                if not fpath:
                    continue
                try:
                    rel = fpath.relative_to(original_path)
                    snippets.append(f"--- {rel} ---\n{fpath.read_text(encoding='utf-8', errors='replace')}")
                except OSError:
                    pass
            if ar_id in {"AR-013", "AR-014"}:
                go_mod = original_path / "go.mod"
                if go_mod.is_file():
                    try:
                        rel = go_mod.relative_to(original_path)
                        snippets.append(f"--- {rel} ---\n{go_mod.read_text(encoding='utf-8', errors='replace')}")
                    except OSError:
                        pass
        return "\n\n".join(snippets) if snippets else ""

    if module.strip("/") == "client-go":
        client_go_root = original_path / "client-go"
        snippets = []
        if client_go_root.exists():
            for fpath in sorted(client_go_root.rglob("*.go")):
                try:
                    content = fpath.read_text(encoding="utf-8", errors="replace")
                    rel = fpath.relative_to(original_path)
                    snippets.append(f"--- {rel} ---\n{content}")
                except OSError:
                    pass
        return "\n\n".join(snippets) if snippets else ""

    module_kw = module.lower().split("/")[-1]
    if lang == "Go":
        exts = {".go"}
    elif lang == "Python":
        exts = {".py"}
    elif lang == "Markdown":
        exts = {".md", ".mdx"}
    elif lang == "TypeScript":
        exts = {".ts", ".tsx", ".js", ".jsx", ".json", ".md", ".mdx", ".css"}
    else:
        exts = SOURCE_EXTS_BY_LANG.get(lang, {".go", ".py", ".md"})

    def include_original_source(filename: str) -> bool:
        ext = os.path.splitext(filename)[1]
        if lang == "Dockerfile":
            return filename == "Dockerfile" or filename.startswith("Dockerfile.") or ext == ".dockerfile"
        if lang == "Makefile":
            return filename == "Makefile" or ext == ".mk"
        return ext in exts

    snippets = []
    for dirpath, dirnames, filenames in os.walk(original_path):
        dirnames[:] = sorted(d for d in dirnames if d not in {
            ".git", "__pycache__", "vendor", "node_modules", ".pytest_cache",
        })
        rel_dir = str(Path(dirpath).relative_to(original_path)).lower()

        # Only grab files related to the module
        if module_kw not in rel_dir and module_kw not in dirpath.lower():
            # Still check filenames
            pass

        for fn in sorted(filenames):
            if not include_original_source(fn):
                continue
            if module_kw not in fn.lower() and module_kw not in rel_dir:
                continue

            fpath = Path(dirpath) / fn
            try:
                content = fpath.read_text(encoding="utf-8", errors="replace")
                rel = fpath.relative_to(original_path)
                # Limit per-file size
                if len(content) > 3000:
                    content = content[:3000] + "\n... (truncated)"
                snippets.append(f"--- {rel} ---\n{content}")
            except OSError:
                pass

    if not snippets:
        # Fallback: grab all source files (up to 10)
        all_files = []
        for dirpath, dirnames, filenames in os.walk(original_path):
            dirnames[:] = sorted(d for d in dirnames if d not in {
                ".git", "__pycache__", "vendor", "node_modules",
            })
            for fn in sorted(filenames):
                if include_original_source(fn):
                    all_files.append(Path(dirpath) / fn)

        for fpath in sorted(all_files)[:10]:
            try:
                content = fpath.read_text(encoding="utf-8", errors="replace")[:3000]
                rel = fpath.relative_to(original_path)
                snippets.append(f"--- {rel} ---\n{content}")
            except OSError:
                pass

    return "\n\n".join(snippets) if snippets else ""


# ─── Main ─────────────────────────────────────────────────────────────────

def _model_studio_model(model_name: str) -> str:
    if "/" in model_name:
        return model_name
    return f"bailian-coding-plan/{model_name}"


def _mixed_stage_model_map(preset: str) -> dict[str, str]:
    if preset != "omo-best-practice":
        raise ValueError(f"Unknown mixed preset: {preset}")
    return {
        # High-context and reasoning-heavy stages.
        "ST-1": _model_studio_model("kimi-k2.5"),
        "ST-2": _model_studio_model("qwen3.6-plus"),
        "ST-3": _model_studio_model("qwen3.6-plus"),
        "ST-6": _model_studio_model("kimi-k2.5"),
        # Implementation and routine workflow stages.
        "ST-0": _model_studio_model("glm-4.7"),
        "ST-4": _model_studio_model("glm-4.7"),
        "ST-5": _model_studio_model("glm-5"),
        "ST-7": _model_studio_model("glm-4.7"),
    }


def _load_stage_model_map(raw: Optional[str]) -> dict[str, str]:
    if not raw:
        return {}
    path = Path(raw)
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return json.loads(raw)


def main():
    parser = argparse.ArgumentParser(description="SDD-TEE v5.1 Benchmark Engine")
    parser.add_argument("--tool", required=True,
                        choices=["claude-code", "gemini-cli", "cursor-cli", "opencode-cli"],
                        help="CLI tool to benchmark")
    parser.add_argument("--model", required=True, help="Model identifier")
    parser.add_argument("--api-base", default=None,
                        help="LiteLLM Proxy URL (e.g. http://localhost:4000)")
    parser.add_argument("--specs-dir", default=str(BASE / "specs"),
                        help="Directory containing SDD spec files")
    parser.add_argument("--ar-limit", type=int, default=None,
                        help="Only run first N ARs (for testing)")
    parser.add_argument("--ar-offset", type=int, default=0,
                        help="Skip the first N ARs before applying --ar-limit")
    parser.add_argument("--dry-run-prompts", action="store_true",
                        help="Print prompts without executing CLI tools (testing)")
    parser.add_argument("--original-repo", default=None,
                        help="Path or URL to original agentcube source for equivalence verification")
    parser.add_argument("--checkpoint-each-ar", action="store_true",
                        help="Write an incremental checkpoint JSON after every AR")
    parser.add_argument("--stop-on-data-issue", action="store_true",
                        help="Stop after an AR if token/cost/cache/quality accounting is inconsistent")
    parser.add_argument("--stop-on-validation-issue", action="store_true",
                        help="Stop after an AR if critical implementation validation fails")
    parser.add_argument("--stage-model-map", default=None,
                        help="JSON string or file path mapping ST-0..ST-7 to provider/model")
    parser.add_argument("--mixed-preset", choices=["omo-best-practice"], default=None,
                        help="Use a built-in mixed-model stage mapping")
    parser.add_argument("--resume-from-checkpoint", default=None,
                        help="Continue a stopped run from an existing checkpoint JSON")
    parser.add_argument("--resume-workspace", default=None,
                        help="Existing workspace to continue when using --resume-from-checkpoint")
    args = parser.parse_args()

    stage_model_map = {}
    if args.mixed_preset:
        stage_model_map.update(_mixed_stage_model_map(args.mixed_preset))
    stage_model_map.update(_load_stage_model_map(args.stage_model_map))

    run_benchmark(
        tool=args.tool,
        model=args.model,
        specs_dir=args.specs_dir,
        api_base=args.api_base,
        ar_limit=args.ar_limit,
        ar_offset=args.ar_offset,
        dry_run_prompts=args.dry_run_prompts,
        original_repo=args.original_repo,
        checkpoint_each_ar=args.checkpoint_each_ar,
        stop_on_data_issue=args.stop_on_data_issue,
        stop_on_validation_issue=args.stop_on_validation_issue,
        stage_model_map=stage_model_map,
        resume_from_checkpoint=args.resume_from_checkpoint,
        resume_workspace=args.resume_workspace,
    )


if __name__ == "__main__":
    main()
