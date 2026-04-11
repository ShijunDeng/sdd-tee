# AR-030: Helm Chart 模板与 Values

**Module**: manifests  
**Language**: YAML  
**Size**: L  
**Status**: ST-3 completed

---

## Tasks

### T001: Chart metadata and directory structure
- [ ] Create `manifests/charts/agentcube/` directory structure
- [ ] Create `manifests/charts/agentcube/Chart.yaml` with metadata
- [ ] Verify `apiVersion: v2`, `type: application`, `version: 1.0.0`, `appVersion: "1.0.0"`
- [ ] Verify keywords: `agentcube`, `ai`, `code-interpreter`, `agent-runtime`, `kubernetes`
- [ ] Verify maintainers list with name and email fields
- [ ] Verify home URL: `https://github.com/volcano-sh/agentcube`

### T002: Default values.yaml - Global and common settings
- [ ] Create `manifests/charts/agentcube/values.yaml` file
- [ ] Define `global` section with `imageRegistry`, `imagePullSecrets`, `namespaceOverride`, `labels`, `annotations`
- [ ] Define top-level `imagePullPolicy: IfNotPresent`
- [ ] Define `rbac` section with `create: true` and `clusterRole` rules
- [ ] Define `priorityClassName` and `extraManifests` settings
- [ ] Verify default values match design specification

### T003: Values.yaml - Controller Manager configuration
- [ ] Add `controllerManager` section to `values.yaml`
- [ ] Configure `enabled: true`, `replicaCount: 2`
- [ ] Define image settings: repository `agentcube/controller-manager`, tag `v1.0.0`
- [ ] Define service settings: type `ClusterIP`, port `8080`, targetPort `8080`
- [ ] Define resource requests: cpu `100m`, memory `128Mi`
- [ ] Define resource limits: cpu `500m`, memory `512Mi`
- [ ] Configure security contexts: runAsNonRoot `true`, runAsUser `1000`, fsGroup `1000`
- [ ] Configure container security contexts: allowPrivilegeEscalation `false`, capabilities drop `ALL`
- [ ] Configure livenessProbe: httpGet path `/healthz`, port `8080`, initialDelaySeconds `30`
- [ ] Configure readinessProbe: httpGet path `/readyz`, port `8080`, initialDelaySeconds `10`
- [ ] Configure autoscaling: enabled `false`, minReplicas `2`, maxReplicas `5`, targetCPU `80%`
- [ ] Configure podDisruptionBudget: enabled `true`, minAvailable `1`
- [ ] Configure serviceAccount: create `true`, name `""`
- [ ] Configure rbac: create `true`, rules `[]`

### T004: Values.yaml - Workload Manager configuration
- [ ] Add `workloadManager` section to `values.yaml`
- [ ] Configure `enabled: true`, `replicaCount: 2`
- [ ] Define image settings: repository `agentcube/workload-manager`, tag `v1.0.0`
- [ ] Define service settings: type `ClusterIP`, port `8080`, targetPort `8080`
- [ ] Define resource requests: cpu `200m`, memory `256Mi`
- [ ] Define resource limits: cpu `1000m`, memory `1Gi`
- [ ] Configure security contexts matching Controller Manager
- [ ] Configure livenessProbe: httpGet path `/healthz`, port `8080`, initialDelaySeconds `30`
- [ ] Configure readinessProbe: httpGet path `/readyz`, port `8080`, initialDelaySeconds `10`
- [ ] Configure autoscaling: enabled `false`, minReplicas `2`, maxReplicas `10`, targetCPU `75%`
- [ ] Configure podDisruptionBudget: enabled `true`, minAvailable `1`
- [ ] Configure serviceAccount: create `true`, name `""`
- [ ] Configure rbac: create `true`, rules `[]`

### T005: Values.yaml - Router configuration
- [ ] Add `router` section to `values.yaml`
- [ ] Configure `enabled: true`, `replicaCount: 3`
- [ ] Define image settings: repository `agentcube/router`, tag `v1.0.0`
- [ ] Define service settings: type `ClusterIP`, port `8080`, targetPort `8080`
- [ ] Define resource requests: cpu `150m`, memory `192Mi`
- [ ] Define resource limits: cpu `750m`, memory `768Mi`
- [ ] Configure podAntiAffinity: requiredDuringSchedulingIgnoredDuringExecution
- [ ] Configure security contexts matching other components
- [ ] Configure livenessProbe: httpGet path `/healthz`, port `8080`, initialDelaySeconds `30`
- [ ] Configure readinessProbe: httpGet path `/readyz`, port `8080`, initialDelaySeconds `10`
- [ ] Configure autoscaling: enabled `false`, minReplicas `3`, maxReplicas `10`, targetCPU `70%`
- [ ] Configure podDisruptionBudget: enabled `true`, minAvailable `2`
- [ ] Configure ingress: enabled `false`, className `nginx`, hosts list
- [ ] Configure serviceAccount: create `true`, name `""`

### T006: Values.yaml - Monitoring and additional configurations
- [ ] Add `monitoring` section with `enabled: false`
- [ ] Configure `serviceMonitor`: enabled `false`, interval `30s`, scrapeTimeout `10s`
- [ ] Configure `prometheusRule`: enabled `false`
- [ ] Add `configMaps` section with `agentcubeConfig.create: true`
- [ ] Define config data: LOG_LEVEL `info`, LOG_FORMAT `json`, METRICS_ENABLED `true`, METRICS_PORT `9090`
- [ ] Add `secrets` section with `create: false`, name `agentcube-secrets`
- [ ] Add `networkPolicies` section with `enabled: false`, defaultDeny `false`
- [ ] Add `ingress` section with `enabled: false`, className `nginx`, tls settings
- [ ] Add `hooks` section with preInstall, postInstall, preUpgrade, postUpgrade

### T007: Environment-specific values files
- [ ] Create `manifests/charts/agentcube/values-dev.yaml`
- [ ] Set development-specific overrides (e.g., lower resource limits, debug enabled)
- [ ] Create `manifests/charts/agentcube/values-prod.yaml`
- [ ] Set production-specific overrides (e.g., higher resource limits, monitoring enabled)
- [ ] Create `manifests/charts/agentcube/values-test.yaml`
- [ ] Set test-specific overrides (e.g., single replica, minimal resources)

### T008: Template helpers (_helpers.tpl)
- [ ] Create `manifests/charts/agentcube/templates/_helpers.tpl`
- [ ] Define `agentcube.name` helper with truncation to 63 chars
- [ ] Define `agentcube.fullname` helper with release name handling
- [ ] Define `agentcube.chart` helper for chart labels
- [ ] Define `agentcube.labels` helper with common labels
- [ ] Define `agentcube.selectorLabels` helper for pod selectors
- [ ] Define `agentcube.controllerManager.serviceAccountName` helper
- [ ] Define `agentcube.workloadManager.serviceAccountName` helper
- [ ] Define `agentcube.router.serviceAccountName` helper
- [ ] Define `agentcube.imageRegistry` helper
- [ ] Define `agentcube.image` helper for full image reference
- [ ] Verify all helpers follow Helm best practices

### T009: CRD templates - AgentRuntime
- [ ] Create `manifests/charts/agentcube/templates/crds/` directory
- [ ] Create `agentruntime.yaml` CRD template
- [ ] Verify API version: `apiextensions.k8s.io/v1`
- [ ] Verify CRD name: `agentruntimes.runtime.agentcube.volcano.sh`
- [ ] Verify helm hook annotations: `crd-install`, hook-weight `-5`
- [ ] Verify group: `runtime.agentcube.volcano.sh`, kind: `AgentRuntime`, scope: `Namespaced`
- [ ] Verify version: `v1alpha1`, served `true`, storage `true`
- [ ] Verify spec schema with required fields: maxSessionDuration, sessionTimeout, podTemplate, targetPort
- [ ] Verify status schema with conditions subresource
- [ ] Verify additionalPrinterColumns for Age

### T010: CRD templates - CodeInterpreter
- [ ] Create `codeinterpreter.yaml` CRD template
- [ ] Verify API version: `apiextensions.k8s.io/v1`
- [ ] Verify CRD name: `codeinterpreters.runtime.agentcube.volcano.sh`
- [ ] Verify helm hook annotations: `crd-install`, hook-weight `-5`
- [ ] Verify group: `runtime.agentcube.volcano.sh`, kind: `CodeInterpreter`, scope: `Namespaced`
- [ ] Verify version: `v1alpha1`, served `true`, storage `true`
- [ ] Verify spec schema with all required fields
- [ ] Verify status schema with conditions subresource
- [ ] Verify additionalPrinterColumns for Age

### T011: Controller Manager deployment template
- [ ] Create `manifests/charts/agentcube/templates/controller-manager/deployment.yaml`
- [ ] Verify condition: `{{- if .Values.controllerManager.enabled }}`
- [ ] Verify Deployment API version: `apps/v1`
- [ ] Verify name uses `agentcube.fullname` helper
- [ ] Verify namespace uses `agentcube.namespace` helper
- [ ] Verify labels include component: `controller-manager`
- [ ] Verify replicas from `controllerManager.replicaCount`
- [ ] Verify selector matches component labels
- [ ] Verify serviceAccountName uses helper
- [ ] Verify image uses `agentcube.image` helper with correct parameters
- [ ] Verify container args: `--leader-elect`, `--health-probe-bind-address=:8080`, `--metrics-bind-address=:9090`
- [ ] Verify container ports: http `8080`, metrics `9090`
- [ ] Verify livenessProbe and readinessProbe from values
- [ ] Verify resources from values
- [ ] Verify security contexts from values
- [ ] Verify checksum/config annotation for ConfigMap changes

### T012: Controller Manager service template
- [ ] Create `manifests/charts/agentcube/templates/controller-manager/service.yaml`
- [ ] Verify condition: `{{- if .Values.controllerManager.enabled }}`
- [ ] Verify Service API version: `v1`
- [ ] Verify name uses `agentcube.fullname` helper
- [ ] Verify type from `controllerManager.service.type`
- [ ] Verify port from `controllerManager.service.port`
- [ ] Verify targetPort: `http`
- [ ] Verify selector matches component labels
- [ ] Verify annotations from values

### T013: Controller Manager ServiceAccount template
- [ ] Create `manifests/charts/agentcube/templates/controller-manager/serviceaccount.yaml`
- [ ] Verify condition: `{{- if and .Values.controllerManager.enabled .Values.controllerManager.serviceAccount.create }}`
- [ ] Verify ServiceAccount API version: `v1`
- [ ] Verify name uses `agentcube.controllerManager.serviceAccountName` helper
- [ ] Verify labels include component: `controller-manager`
- [ ] Verify annotations from values

### T014: Controller Manager RBAC template
- [ ] Create `manifests/charts/agentcube/templates/controller-manager/rbac.yaml`
- [ ] Verify condition: `{{- if and .Values.controllerManager.enabled .Values.controllerManager.rbac.create }}`
- [ ] Create Role resource with rules from `controllerManager.rbac.rules`
- [ ] Create RoleBinding resource
- [ ] Verify roleRef references the Role
- [ ] Verify subjects reference the ServiceAccount
- [ ] Verify labels include component: `controller-manager`

### T015: Workload Manager deployment template
- [ ] Create `manifests/charts/agentcube/templates/workload-manager/deployment.yaml`
- [ ] Verify condition: `{{- if .Values.workloadManager.enabled }}`
- [ ] Verify Deployment API version: `apps/v1`
- [ ] Verify name: `{{ printf "%s-workload-manager" (include "agentcube.fullname" .) }}`
- [ ] Verify replicas from `workloadManager.replicaCount`
- [ ] Verify selector matches component labels
- [ ] Verify serviceAccountName uses `agentcube.workloadManager.serviceAccountName` helper
- [ ] Verify image uses correct repository and tag
- [ ] Verify container args match Controller Manager pattern
- [ ] Verify livenessProbe and readinessProbe from values
- [ ] Verify resources from values
- [ ] Verify security contexts from values
- [ ] Verify checksum/config annotation

### T016: Workload Manager service template
- [ ] Create `manifests/charts/agentcube/templates/workload-manager/service.yaml`
- [ ] Verify condition: `{{- if .Values.workloadManager.enabled }}`
- [ ] Verify Service API version: `v1`
- [ ] Verify name: `{{ printf "%s-workload-manager" (include "agentcube.fullname" .) }}`
- [ ] Verify type from `workloadManager.service.type`
- [ ] Verify port from `workloadManager.service.port`
- [ ] Verify selector matches component labels

### T017: Workload Manager ServiceAccount template
- [ ] Create `manifests/charts/agentcube/templates/workload-manager/serviceaccount.yaml`
- [ ] Verify condition: `{{- if and .Values.workloadManager.enabled .Values.workloadManager.serviceAccount.create }}`
- [ ] Verify ServiceAccount API version: `v1`
- [ ] Verify name uses `agentcube.workloadManager.serviceAccountName` helper
- [ ] Verify labels include component: `workload-manager`

### T018: Workload Manager RBAC template
- [ ] Create `manifests/charts/agentcube/templates/workload-manager/rbac.yaml`
- [ ] Verify condition: `{{- if and .Values.workloadManager.enabled .Values.workloadManager.rbac.create }}`
- [ ] Create Role resource with rules from `workloadManager.rbac.rules`
- [ ] Create RoleBinding resource
- [ ] Verify roleRef and subjects are correctly configured

### T019: Router deployment template
- [ ] Create `manifests/charts/agentcube/templates/router/deployment.yaml`
- [ ] Verify condition: `{{- if .Values.router.enabled }}`
- [ ] Verify Deployment API version: `apps/v1`
- [ ] Verify name: `{{ printf "%s-router" (include "agentcube.fullname" .) }}`
- [ ] Verify replicas from `router.replicaCount`
- [ ] Verify selector matches component labels
- [ ] Verify serviceAccountName uses `agentcube.router.serviceAccountName` helper
- [ ] Verify image uses correct repository and tag
- [ ] Verify container args match pattern
- [ ] Verify livenessProbe and readinessProbe from values
- [ ] Verify resources from values
- [ ] Verify affinity configuration for podAntiAffinity
- [ ] Verify checksum/config annotation

### T020: Router service template
- [ ] Create `manifests/charts/agentcube/templates/router/service.yaml`
- [ ] Verify condition: `{{- if .Values.router.enabled }}`
- [ ] Verify Service API version: `v1`
- [ ] Verify name: `{{ printf "%s-router" (include "agentcube.fullname" .) }}`
- [ ] Verify type from `router.service.type`
- [ ] Verify port from `router.service.port`
- [ ] Verify selector matches component labels
- [ ] Verify annotations from values

### T021: Router ServiceAccount template
- [ ] Create `manifests/charts/agentcube/templates/router/serviceaccount.yaml`
- [ ] Verify condition: `{{- if and .Values.router.enabled .Values.router.serviceAccount.create }}`
- [ ] Verify ServiceAccount API version: `v1`
- [ ] Verify name uses `agentcube.router.serviceAccountName` helper
- [ ] Verify labels include component: `router`

### T022: Router RBAC template
- [ ] Create `manifests/charts/agentcube/templates/router/rbac.yaml`
- [ ] Verify condition: `{{- if and .Values.router.enabled .Values.router.rbac.create }}`
- [ ] Create Role resource with rules from `router.rbac.rules`
- [ ] Create RoleBinding resource
- [ ] Verify roleRef and subjects are correctly configured

### T023: Cluster RBAC templates
- [ ] Create `manifests/charts/agentcube/templates/rbac/` directory
- [ ] Create `clusterrole.yaml` template
- [ ] Verify condition: `{{- if .Values.rbac.create }}`
- [ ] Create ClusterRole with rules from `rbac.clusterRole.rules`
- [ ] Verify rules include runtime.agentcube.volcano.sh API groups
- [ ] Verify rules include core API groups for pods, services, configmaps, secrets
- [ ] Create `clusterrolebinding.yaml` template
- [ ] Verify ClusterRoleBinding references ClusterRole
- [ ] Verify subjects reference all three component ServiceAccounts

### T024: PodDisruptionBudget templates
- [ ] Create `manifests/charts/agentcube/templates/poddisruptionbudgets/` directory
- [ ] Create `controller-manager.yaml` PDB template
- [ ] Verify condition for component enabled and PDB enabled
- [ ] Verify minAvailable from `controllerManager.podDisruptionBudget.minAvailable`
- [ ] Create `workload-manager.yaml` PDB template
- [ ] Verify condition and minAvailable from values
- [ ] Create `router.yaml` PDB template
- [ ] Verify condition and minAvailable from values

### T025: ServiceMonitor template
- [ ] Create `manifests/charts/agentcube/templates/monitoring/servicemonitor.yaml`
- [ ] Verify condition: `{{- if and .Values.monitoring.enabled .Values.monitoring.serviceMonitor.enabled }}`
- [ ] Verify ServiceMonitor API version: `monitoring.coreos.com/v1`
- [ ] Verify selector uses `agentcube.selectorLabels`
- [ ] Verify namespaceSelector matches release namespace
- [ ] Verify endpoint configuration: port `metrics`, interval, scrapeTimeout from values
- [ ] Verify path: `/metrics`
- [ ] Verify labels from `monitoring.serviceMonitor.labels`

### T026: ConfigMap template
- [ ] Create `manifests/charts/agentcube/templates/configmaps/config.yaml`
- [ ] Verify condition: `{{- if .Values.configMaps.agentcubeConfig.create }}`
- [ ] Verify ConfigMap API version: `v1`
- [ ] Verify name: `{{ include "agentcube.fullname" . }}-config`
- [ ] Verify data from `configMaps.agentcubeConfig.data`
- [ ] Verify all required config keys are present

### T027: Secret template
- [ ] Create `manifests/charts/agentcube/templates/secrets/secret.yaml`
- [ ] Verify condition: `{{- if .Values.secrets.create }}`
- [ ] Verify Secret API version: `v1`
- [ ] Verify name from `secrets.name` or default
- [ ] Verify type: `Opaque`
- [ ] Verify data is base64 encoded using `| b64enc`

### T028: Ingress template
- [ ] Create `manifests/charts/agentcube/templates/ingress.yaml`
- [ ] Verify condition: `{{- if .Values.ingress.enabled }}`
- [ ] Verify Ingress API version: `networking.k8s.io/v1`
- [ ] Verify ingressClassName from values
- [ ] Verify TLS configuration from values
- [ ] Verify hosts and paths from values
- [ ] Verify backend service name defaults to router
- [ ] Verify backend service port defaults to 8080

### T029: NetworkPolicy template
- [ ] Create `manifests/charts/agentcube/templates/networkpolicies/networkpolicy.yaml`
- [ ] Verify condition: `{{- if .Values.networkPolicies.enabled }}`
- [ ] Verify NetworkPolicy API version: `networking.k8s.io/v1`
- [ ] Verify podSelector: `{}` for all pods
- [ ] Verify policyTypes include Ingress and Egress if defaultDeny
- [ ] Verify ingress rules from `networkPolicies.rules`
- [ ] Verify egress rules from `networkPolicies.rules`

### T030: NOTES.txt template
- [ ] Create `manifests/charts/agentcube/templates/NOTES.txt`
- [ ] Include release name and chart name
- [ ] Include instructions for accessing Router service
- [ ] Handle ClusterIP service type with port-forward instructions
- [ ] Handle NodePort service type with Node IP and port instructions
- [ ] Handle LoadBalancer service type with external IP instructions
- [ ] Handle Ingress with URL instructions
- [ ] Include monitoring verification instructions if enabled
- [ ] Include link to GitHub repository

### T031: Chart tests
- [ ] Create `manifests/charts/agentcube/tests/` directory
- [ ] Create `controller-manager_test.yaml` with deployment, service, and RBAC tests
- [ ] Test that deployment renders with correct replicas
- [ ] Test that service renders with correct port
- [ ] Test that deployment is disabled when `controllerManager.enabled: false`
- [ ] Create `workload-manager_test.yaml` with deployment and service tests
- [ ] Create `router_test.yaml` with deployment and service tests
- [ ] Test that router uses correct affinity rules
- [ ] Test that helper templates generate correct labels

### T032: Chart documentation
- [ ] Create `manifests/charts/agentcube/README.md`
- [ ] Include chart description and overview
- [ ] Include installation instructions
- [ ] Include configuration reference for all values
- [ ] Include examples for common use cases
- [ ] Include upgrade instructions
- [ ] Include uninstall instructions
- [ ] Include troubleshooting section

### T033: Chart validation and linting
- [ ] Run `helm lint ./manifests/charts/agentcube` and verify no errors
- [ ] Run `helm template agentcube ./manifests/charts/agentcube --debug` and verify rendering
- [ ] Run `helm dependency list ./manifests/charts/agentcube` (if dependencies exist)
- [ ] Verify all YAML syntax is valid
- [ ] Verify all template variables are defined
- [ ] Verify all helper functions work correctly
- [ ] Verify chart passes `helm show values` without errors

### T034: Chart package and repository preparation
- [ ] Run `helm package ./manifests/charts/agentcube` to create .tgz file
- [ ] Verify .tgz file is created with correct name
- [ ] Verify .tgz file contains all required files
- [ ] Update `manifests/charts/index.yaml` if maintaining a chart repository
- [ ] Verify chart version in Chart.yaml matches design specification

---

## Verification

- [ ] Chart.yaml is valid Helm v2 format with all required fields
- [ ] values.yaml contains all configuration sections with correct defaults
- [ ] All environment-specific values files exist and are valid
- [ ] All helper templates in _helpers.tpl are functional
- [ ] CRD templates are valid and install successfully
- [ ] All component deployment templates render correctly
- [ ] All service templates render with correct configuration
- [ ] All ServiceAccount templates create correctly
- [ ] All RBAC templates grant appropriate permissions
- [ ] PodDisruptionBudget templates protect pods appropriately
- [ ] ServiceMonitor template integrates with Prometheus
- [ ] ConfigMap and Secret templates handle sensitive data correctly
- [ ] Ingress template configures external access properly
- [ ] NetworkPolicy template enforces network policies when enabled
- [ ] NOTES.txt provides helpful post-installation instructions
- [ ] All tests pass with `helm unittest`
- [ ] README.md provides comprehensive documentation
- [ ] Chart passes `helm lint` without errors or warnings
- [ ] Chart template rendering completes without errors
- [ ] Chart package creates a valid .tgz file