# Idle Cleanup Specification

## Purpose
Run a controller that deletes `Sandbox` custom resources when an idle-timeout annotation indicates the sandbox has been inactive beyond a fixed grace period.

## Requirements

### Requirement: Reconciliation trigger
The system SHALL register a controller-runtime reconciler for resource kind `Sandbox` API version `agents.x-k8s.io/v1alpha1`, using the manager’s API reader/writer client for get/delete operations.

#### Scenario: Sandbox watch drives reconcile
- **GIVEN** a `Sandbox` object is created or updated in the cluster
- **WHEN** the manager is running
- **THEN** the reconciler `Reconcile` function is invoked with the object’s namespace and name

### Requirement: Idle detection input
The system SHALL read annotation key `last-activity-time` (constant `workloadmanager.LastActivityAnnotationKey`) from the `Sandbox` metadata. When the annotation is missing or empty, the system SHALL take no delete action and SHALL return without requeue (unless other logic applies—none in this controller).

#### Scenario: No annotation means no deletion
- **GIVEN** a `Sandbox` without `last-activity-time`
- **WHEN** reconciliation completes
- **THEN** the sandbox is not deleted and result has zero `RequeueAfter`

### Requirement: Idle detection parsing
When the annotation is non-empty, the system SHALL parse it with `time.RFC3339`. On parse error, the system SHALL return `RequeueAfter: 30 seconds` and the parse error.

#### Scenario: Invalid timestamp requeues
- **GIVEN** annotation value is not RFC3339
- **WHEN** `time.Parse` fails
- **THEN** reconcile returns `(Result{RequeueAfter: 30s}, err)`

### Requirement: Expiration threshold
The system SHALL define `SessionExpirationTimeout = 15 * time.Minute`. The system SHALL compute `expirationTime = lastActivity.Add(SessionExpirationTimeout)`. When `time.Now().After(expirationTime)`, the system SHALL delete the `Sandbox` resource.

#### Scenario: Idle beyond 15 minutes triggers delete
- **GIVEN** `last-activity-time` parses to a time more than 15 minutes in the past
- **WHEN** reconciliation runs
- **THEN** the controller calls delete on the `Sandbox` client object

#### Scenario: Not yet expired requeues until expiration
- **GIVEN** `last-activity-time` is recent enough that expiration is in the future
- **WHEN** reconciliation runs
- **THEN** the result is `RequeueAfter: time.Until(expirationTime)` and no delete occurs

### Requirement: Delete idempotency
When delete returns `NotFound`, the system SHALL treat it as success and SHALL return empty result with nil error. Other delete errors SHALL be returned to trigger retry.

#### Scenario: Already deleted sandbox
- **GIVEN** the API server returns not found on delete
- **WHEN** the reconciler handles the error
- **THEN** reconcile returns `(ctrl.Result{}, nil)`

### Requirement: Get not found
When get returns `NotFound`, the system SHALL return empty result and nil error.

#### Scenario: Sandbox removed before reconcile
- **GIVEN** the sandbox no longer exists
- **WHEN** `Get` fails with not found
- **THEN** reconcile returns without error

## Requirements (binary / operator)

### Requirement: Manager options
The `agentd` binary SHALL construct controller-runtime `Manager` with scheme containing core Kubernetes types and `sandboxv1alpha1` from `sigs.k8s.io/agent-sandbox/api/v1alpha1`, SHALL disable metrics server (`BindAddress: "0"`), and SHALL disable health probe server (`HealthProbeBindAddress: "0"`).

#### Scenario: Signal-driven shutdown
- **GIVEN** the process runs `mgr.Start(ctrl.SetupSignalHandler())`
- **WHEN** SIGTERM/SIGINT is received
- **THEN** the manager stops gracefully per controller-runtime defaults
