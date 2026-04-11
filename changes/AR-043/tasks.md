# AR-043: 架构设计文档与 API 文档

**Module**: docs  
**Language**: Markdown (Docusaurus 3.x)  
**Size**: M  
**Status**: ST-3 completed  

---

## Tasks

### T001: API Reference — Control Plane (WorkloadManager REST API)
- [ ] Create `docs/docs/api-reference/control-plane.md`
- [ ] Document `POST /api/v1/sandboxes` endpoint:
  - [ ] Request body schema: `kind` ("AgentRuntime" | "CodeInterpreter"), `name`, `namespace`, `metadata`, `ttl`
  - [ ] Response body schema: `sessionId`, `sandboxId`, `sandboxName`, `entryPoints`
  - [ ] Success status code: 201
  - [ ] Error codes: 400 (validation), 404 (template not found), 500 (internal)
- [ ] Document `GET /api/v1/sandboxes/:sessionID` endpoint:
  - [ ] Path parameter `sessionID` description
  - [ ] Response body with sandbox status information
- [ ] Document `GET /api/v1/sandboxes` list endpoint:
  - [ ] Query parameters: `?namespace=`, `?status=`
- [ ] Document `DELETE /api/v1/sandboxes/:sessionID` endpoint:
  - [ ] Idempotent delete behavior (404 treated as success)
  - [ ] Status codes: 200, 404, 500
- [ ] Document `POST /api/v1/sandboxes/:sessionID/extend` endpoint:
  - [ ] Request body: `extensionDuration` field
  - [ ] Description of TTL extension impact on sandbox lifecycle
- [ ] Document health check endpoints:
  - [ ] `GET /health/live` (liveness probe) returning `{"status": "ok"}`
  - [ ] `GET /health/ready` (readiness probe) returning `{"status": "ok"}`
- [ ] Use `<ApiEndpoint>` MDX component for each endpoint with method, path, description props
- [ ] Include request/response examples in code blocks

### T002: API Reference — Data Plane (Router + PicoD)
- [ ] Create `docs/docs/api-reference/data-plane.md`
- [ ] Document Router proxy endpoints:
  - [ ] `GET/POST /v1/namespaces/:namespace/agent-runtimes/:name/invocations/*path`
  - [ ] `GET/POST /v1/namespaces/:namespace/code-interpreters/:name/invocations/*path`
  - [ ] Explain Router reverse proxy behavior
  - [ ] Explain `x-agentcube-session-id` response header purpose
  - [ ] Explain automatic session creation on first request
  - [ ] Document path parameters: `namespace`, `name`, wildcard `*path`
- [ ] Document Router health check endpoints:
  - [ ] `GET /health/live` returning `{"status": "alive"}`
  - [ ] `GET /health/ready` (checks session manager availability)
- [ ] Document PicoD API endpoints:
  - [ ] `POST /api/execute` with request schema: `command` (array), `timeout` (string like "30s"), `working_dir`, `env`
  - [ ] Response body: execution output, exit code, error message
  - [ ] JWT public-key authentication mechanism
  - [ ] `POST /api/files` (upload, supports multipart/form-data and JSON base64)
  - [ ] `GET /api/files` (directory listing, query param `?path=...`)
  - [ ] `GET /api/files/*path` (file download/streaming)
  - [ ] `GET /health` (returns service name, version, uptime)
- [ ] Use `<ApiEndpoint>` MDX component for each endpoint

### T003: API Reference — CRDs (Kubernetes Custom Resource Definitions)
- [ ] Create `docs/docs/api-reference/crds.md`
- [ ] Document AgentRuntime CRD:
  - [ ] API group: `runtime.agentcube.volcano.sh/v1alpha1`
  - [ ] Kind: `AgentRuntime`
  - [ ] Spec fields table: `targetPort[]` (name, port, protocol, pathPrefix), `podTemplate` (SandboxTemplate), `sessionTimeout`, `maxSessionDuration` (default 8h)
  - [ ] Status fields: `conditions[]` (metav1.Condition array)
  - [ ] Include YAML example
- [ ] Document CodeInterpreter CRD:
  - [ ] Kind: `CodeInterpreter`
  - [ ] Spec fields table: `ports[]`, `template` (CodeInterpreterSandboxTemplate with all sub-fields), `sessionTimeout`, `maxSessionDuration`, `warmPoolSize`, `authMode` ("picod" | "none")
  - [ ] Status fields: `conditions[]`, `ready` (boolean)
  - [ ] Explain warm pool mechanism
  - [ ] Include YAML example
- [ ] Document Sandbox CRD:
  - [ ] API group: `agents.x-k8s.io/v1alpha1`
  - [ ] Kind: `Sandbox` spec fields (`image`, `command`) and status (`phase`)
- [ ] Document SandboxClaim CRD:
  - [ ] API group: `extensions.agents.x-k8s.io/v1alpha1`
  - [ ] Explain relationship with warm pool
- [ ] Use `<K8sResource>` MDX component for CRD metadata (group, version, kind, scope)
- [ ] Use tables for field definitions

### T004: Architecture — Session Routing Documentation
- [ ] Create `docs/docs/architecture/session-routing.md`
- [ ] Document complete session flow: creation → lookup → forwarding
- [ ] Document Redis/Valkey session data structures
- [ ] Document session caching strategy
- [ ] Document JWT authentication injection in routing
- [ ] Include Mermaid diagram of session routing flow
- [ ] Add cross-references to related docs (data-flow, security)

### T005: Architecture — Sandbox Lifecycle Documentation
- [ ] Create `docs/docs/architecture/sandbox-lifecycle.md`
- [ ] Document sandbox state machine: creation → running → idle → cleanup
- [ ] Document Agentd idle cleanup mechanism:
  - [ ] Default 30-minute timeout
  - [ ] 5-minute check interval
- [ ] Document graceful shutdown and drain period
- [ ] Document warm pool lifecycle differences
- [ ] Include Mermaid state diagram
- [ ] Add cross-references to CRD docs and operations docs

### T006: Integrations — Dify Plugin Documentation
- [ ] Create `docs/docs/integrations/dify-plugin.md`
- [ ] Document Dify plugin installation steps
- [ ] Document Dify-AgentCube configuration
- [ ] Include configuration examples
- [ ] Document `integrations/` directory plugin code structure
- [ ] Include troubleshooting tips for Dify integration

### T007: Integrations — LangChain Documentation
- [ ] Create `docs/docs/integrations/langchain.md`
- [ ] Document LangChain tool/agent integration with AgentCube
- [ ] Include Python code examples
- [ ] Document `AgentRuntimeClient` usage in LangChain context
- [ ] Include complete workflow example (setup → invoke → handle response)

### T008: Operations — Deployment Documentation
- [ ] Create `docs/docs/operations/deployment.md`
- [ ] Document Helm chart deployment method
- [ ] Document `deployment/` directory manifests structure
- [ ] Document Docker multi-stage build process
- [ ] Document GitHub Actions CI/CD workflow
- [ ] Document multi-namespace deployment guide
- [ ] Include deployment checklist

### T009: Operations — Monitoring Documentation
- [ ] Create `docs/docs/operations/monitoring.md`
- [ ] Document available metrics (WorkloadManager reconciler metrics, etc.)
- [ ] Document log collection method
- [ ] Include alerting rule recommendations
- [ ] Document Grafana dashboard setup (if applicable)
- [ ] Include monitoring verification commands

### T010: Operations — Troubleshooting Documentation
- [ ] Create `docs/docs/operations/troubleshooting.md`
- [ ] Document common problems and solutions list
- [ ] Document log viewing methods
- [ ] Document session state diagnosis methods
- [ ] Include error code reference table
- [ ] Include escalation procedures

### T011: Operations — Security Documentation
- [ ] Create `docs/docs/operations/security.md`
- [ ] Document JWT RS256 authentication mechanism
- [ ] Document K8s TokenReview integration
- [ ] Document sandbox isolation mechanisms (cgroups, namespaces)
- [ ] Document PicoD JWT public-key authentication
- [ ] Document network security policy recommendations
- [ ] Include security checklist

### T012: Contributing — Development Guide
- [ ] Create `docs/docs/contributing/development.md`
- [ ] Document local development environment setup
- [ ] Document Go and Python development environment requirements
- [ ] Document Makefile common commands
- [ ] Document code generation workflow (`hack/` directory)
- [ ] Include quick start for new contributors

### T013: Contributing — Testing Guide
- [ ] Create `docs/docs/contributing/testing.md`
- [ ] Document Go unit test execution
- [ ] Document Python test execution
- [ ] Document TDD workflow and `test_spec.md` conventions
- [ ] Document test coverage requirements
- [ ] Include example test cases

### T014: Contributing — Release Process
- [ ] Create `docs/docs/contributing/release-process.md`
- [ ] Document semantic versioning (semver) strategy
- [ ] Document CI/CD release workflow
- [ ] Document Helm chart release process
- [ ] Document documentation site release process
- [ ] Include release checklist

### T015: User Guide — Python SDK
- [ ] Create `docs/docs/user-guide/python-sdk.md`
- [ ] Document `CodeInterpreterClient` usage with examples
- [ ] Document `AgentRuntimeClient` usage with examples
- [ ] Document context manager pattern
- [ ] Document error handling
- [ ] Include complete workflow examples

### T016: i18n — Chinese Translation Framework
- [ ] Create `docs/i18n/zh/` directory structure
- [ ] Create `docs/i18n/zh/docusaurus-plugin-content-docs/current/` directory
- [ ] Create translation skeleton files matching English docs structure
- [ ] Ensure translation files have correct frontmatter (Chinese title and description)
- [ ] Update `docusaurus.config.js` to include `locales: ['en', 'zh']`
- [ ] Configure `localeDropdown` in navbar for language switching
- [ ] Verify fallback to English for untranslated pages

### T017: Documentation Quality — Frontmatter Standards
- [ ] Add YAML frontmatter to all new documents:
  - [ ] `sidebar_position` (number)
  - [ ] `title` (string)
  - [ ] `description` (string, for SEO)
  - [ ] `keywords` (string array)
- [ ] Verify frontmatter consistency across all docs
- [ ] Update existing docs with missing frontmatter fields

### T018: MDX Components — ApiEndpoint and K8sResource
- [ ] Verify `docs/src/components/ApiEndpoint/` component exists and renders correctly
- [ ] Verify `docs/src/components/K8sResource/` component exists and renders correctly
- [ ] Test ApiEndpoint component with method color labels and endpoint paths
- [ ] Test K8sResource component with CRD metadata display
- [ ] Create component usage examples in docs

### T019: Sidebar Navigation Updates
- [ ] Update `docs/sidebars.js` to include new documentation sections:
  - [ ] Add `api-reference` category with control-plane, data-plane, crds
  - [ ] Add `integrations` category with dify-plugin, langchain
  - [ ] Add `user-guide` category with python-sdk
  - [ ] Add `contributing` category with development, testing, release-process
  - [ ] Update `operations` category with deployment, monitoring, troubleshooting, security
  - [ ] Update `architecture` category with session-routing, sandbox-lifecycle
- [ ] Verify sidebar order matches user journey
- [ ] Test sidebar navigation in Docusaurus dev server

### T020: Documentation Build and Link Validation
- [ ] Run Docusaurus build: `cd docs && npm run build`
- [ ] Verify no broken links (config `onBrokenLinks: 'throw'`)
- [ ] Verify all internal relative links point to existing files
- [ ] Verify all sidebar doc IDs exist
- [ ] Verify code blocks have correct language tags (go, python, yaml, json, bash, kubernetes)
- [ ] Verify Mermaid diagrams render correctly
- [ ] Test documentation site locally: `cd docs && npm start`

---

## Verification

- [ ] All 20 tasks completed
- [ ] All 15 new documentation files created per File Structure table
- [ ] `docs/sidebars.js` updated with new sections
- [ ] `docs/docusaurus.config.js` updated with i18n support (en, zh)
- [ ] Docusaurus build completes without errors: `npm run build`
- [ ] No broken links in documentation
- [ ] All API endpoints documented with request/response schemas
- [ ] All CRDs documented with field tables and YAML examples
- [ ] MDX components (ApiEndpoint, K8sResource) render correctly
- [ ] All docs have proper frontmatter (sidebar_position, title, description, keywords)
- [ ] Code examples use correct language tags
- [ ] Mermaid diagrams render in both light and dark themes
- [ ] Chinese translation framework configured with locale dropdown
- [ ] Cross-references between docs are valid
- [ ] Documentation covers all 9 requirements (R-1 through R-9) from delta spec
