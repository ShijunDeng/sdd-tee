# Idle Cleanup — Design

## Module

- `github.com/volcano-sh/agentcube` (see root `go.mod` in sandbox-orchestration design).

## Package `github.com/volcano-sh/agentcube/pkg/agentd`

### Time threshold

```go
var SessionExpirationTimeout = 15 * time.Minute
```

Idle expiration: `expirationTime := lastActivity.Add(SessionExpirationTimeout)`; delete when `time.Now().After(expirationTime)`.

### Annotation key

The reconciler uses the same key as workload manager pod annotation for idle timeout tracking on the **Sandbox** object:

- Import: `github.com/volcano-sh/agentcube/pkg/workloadmanager`
- Key: `workloadmanager.LastActivityAnnotationKey` = **`"last-activity-time"`**

(Workload manager also sets `runtime.agentcube.io/idle-timeout` on Sandbox metadata for template-driven idle configuration; **agentd** only reads `last-activity-time`.)

### Reconciler

```go
package agentd

type Reconciler struct {
    client.Client
    Scheme *runtime.Scheme
}

func (r *Reconciler) Reconcile(ctx context.Context, req ctrl.Request) (ctrl.Result, error)
```

**Algorithm (exact behavior):**

1. `sandbox := &sandboxv1alpha1.Sandbox{}`; `Get(ctx, req.NamespacedName, sandbox)`.
2. If `errors.IsNotFound(err)` → `return ctrl.Result{}, nil`.
3. If other get error → return `ctrl.Result{}, err`.
4. `lastActivityStr, exists := sandbox.Annotations[workloadmanager.LastActivityAnnotationKey]`.
5. If `exists && lastActivityStr != ""`:
   - `lastActivity, err := time.Parse(time.RFC3339, lastActivityStr)`
   - If parse err → `return ctrl.Result{RequeueAfter: 30 * time.Second}, err`
   - `expirationTime := lastActivity.Add(SessionExpirationTimeout)`
   - If `time.Now().After(expirationTime)`:
     - `r.Delete(ctx, sandbox)`; if err and not `IsNotFound` → `return ctrl.Result{}, err`
   - Else:
     - `return ctrl.Result{RequeueAfter: time.Until(expirationTime)}, nil`
6. `return ctrl.Result{}, nil`

### SetupWithManager

```go
func (r *Reconciler) SetupWithManager(mgr ctrl.Manager) error {
    return ctrl.NewControllerManagedBy(mgr).
        For(&sandboxv1alpha1.Sandbox{}).
        Complete(r)
}
```

## Binary `cmd/agentd/main.go`

### Scheme registration

```go
var schemeBuilder = runtime.NewScheme()

func init() {
    utilruntime.Must(scheme.AddToScheme(schemeBuilder))
    utilruntime.Must(sandboxv1alpha1.AddToScheme(schemeBuilder))
}
```

### Controller-runtime manager

```go
mgr, err := ctrl.NewManager(ctrl.GetConfigOrDie(), ctrl.Options{
    Scheme:                 schemeBuilder,
    Metrics:                metricsserver.Options{BindAddress: "0"},
    HealthProbeBindAddress:   "0",
})
```

### Controller registration (duplicate of SetupWithManager pattern)

```go
err = ctrl.NewControllerManagedBy(mgr).
    For(&sandboxv1alpha1.Sandbox{}).
    Complete(&agentd.Reconciler{
        Client: mgr.GetClient(),
        Scheme: mgr.GetScheme(),
    })
```

### Run

```go
mgr.Start(ctrl.SetupSignalHandler())
```

## Watched resources

| API group | Version | Kind | Trigger |
|-----------|---------|------|---------|
| `agents.x-k8s.io` | `v1alpha1` | `Sandbox` | Default `For()` watch — creates, updates, deletes (per controller-runtime) |

No explicit `Owns` or `Watches` — single primary resource `Sandbox`.

## Related workload-manager constants (context)

From `pkg/workloadmanager` (not used by agentd reconcile logic but set when sandboxes are created):

- `IdleTimeoutAnnotationKey = "runtime.agentcube.io/idle-timeout"` — duration string on Sandbox CR.
- `LastActivityAnnotationKey = "last-activity-time"` — **read by agentd** for idle cleanup.

## Dependencies

- `k8s.io/apimachinery/pkg/api/errors`
- `k8s.io/apimachinery/pkg/runtime`
- `sigs.k8s.io/agent-sandbox/api/v1alpha1`
- `sigs.k8s.io/controller-runtime`
- `github.com/volcano-sh/agentcube/pkg/workloadmanager` (annotation key only)
