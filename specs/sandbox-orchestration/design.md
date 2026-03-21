# Sandbox Orchestration — Design

## Module and dependencies

| Item | Value |
|------|--------|
| Go module | `github.com/volcano-sh/agentcube` |
| Go version (go.mod) | `1.24.4` |
| Toolchain | `go1.24.9` |

**Direct `require` (from go.mod):**  
`github.com/agiledragon/gomonkey/v2 v2.13.0`, `github.com/alicebob/miniredis/v2 v2.35.0`, `github.com/gin-gonic/gin v1.10.0`, `github.com/golang-jwt/jwt/v5 v5.2.2`, `github.com/google/uuid v1.6.0`, `github.com/redis/go-redis/v9 v9.17.1`, `github.com/stretchr/testify v1.11.1`, `github.com/valkey-io/valkey-go v1.0.69`, `golang.org/x/net v0.47.0`, `k8s.io/api v0.34.1`, `k8s.io/apimachinery v0.34.1`, `k8s.io/client-go v0.34.1`, `k8s.io/klog/v2 v2.130.1`, `k8s.io/utils v0.0.0-20251002143259-bc988d571ff4`, `sigs.k8s.io/agent-sandbox v0.1.1`, `sigs.k8s.io/controller-runtime v0.22.2`

## Package `github.com/volcano-sh/agentcube/pkg/apis/runtime/v1alpha1`

### groupversion_info.go — package and scheme

```go
// +groupName=runtime.agentcube.volcano.sh
package v1alpha1

var (
    GroupVersion = schema.GroupVersion{Group: "runtime.agentcube.volcano.sh", Version: "v1alpha1"}
    SchemeBuilder = &scheme.Builder{GroupVersion: GroupVersion}
    AddToScheme = SchemeBuilder.AddToScheme
)
```

### register.go — kind metadata

```go
var (
    CodeInterpreterKind             = "CodeInterpreter"
    CodeInterpreterGroupKind        = GroupVersion.WithKind("CodeInterpreter")
    CodeInterpreterListKind         = "CodeInterpreterList"
    CodeInterpreterGroupVersionKind = GroupVersion.WithKind("CodeInterpreter")
)

var (
    AgentRuntimeKind             = "AgentRuntime"
    AgentRuntimeListKind         = "AgentRuntimeList"
    AgentRuntimeGroupVersionKind = GroupVersion.WithKind("AgentRuntime")
)

var SchemeGroupVersion = GroupVersion

func Resource(resource string) schema.GroupVersionResource {
    return GroupVersion.WithResource(resource)
}
```

### agent_type.go — AgentRuntime types

```go
// +genclient
// +k8s:deepcopy-gen:interfaces=k8s.io/apimachinery/pkg/runtime.Object
// +kubebuilder:object:root=true
// +kubebuilder:subresource:status
// +kubebuilder:resource:scope=Namespaced
// +kubebuilder:printcolumn:name="Age",type="date",JSONPath=".metadata.creationTimestamp"
type AgentRuntime struct {
    metav1.TypeMeta   `json:",inline"`
    metav1.ObjectMeta `json:"metadata,omitempty"`
    Spec   AgentRuntimeSpec   `json:"spec"`
    Status AgentRuntimeStatus `json:"status,omitempty"`
}

type AgentRuntimeSpec struct {
    Ports []TargetPort `json:"targetPort"`
    // +kubebuilder:validation:Required
    Template *SandboxTemplate `json:"podTemplate" protobuf:"bytes,1,opt,name=podTemplate"`
    // +kubebuilder:validation:Required
    // +kubebuilder:default="15m"
    SessionTimeout *metav1.Duration `json:"sessionTimeout,omitempty" protobuf:"bytes,2,opt,name=sessionTimeout"`
    // +kubebuilder:validation:Required
    // +kubebuilder:default="8h"
    MaxSessionDuration *metav1.Duration `json:"maxSessionDuration,omitempty" protobuf:"bytes,3,opt,name=maxSessionDuration"`
}

type AgentRuntimeStatus struct {
    // +optional
    Conditions []metav1.Condition `json:"conditions,omitempty"`
}

type SandboxTemplate struct {
    // +optional
    Labels map[string]string `json:"labels,omitempty" protobuf:"bytes,1,rep,name=labels"`
    // +optional
    Annotations map[string]string `json:"annotations,omitempty" protobuf:"bytes,2,rep,name=annotations"`
    // +kubebuilder:validation:Required
    Spec corev1.PodSpec `json:"spec" protobuf:"bytes,3,opt,name=spec"`
}

// +k8s:deepcopy-gen:interfaces=k8s.io/apimachinery/pkg/runtime.Object
// +kubebuilder:object:root=true
type AgentRuntimeList struct {
    metav1.TypeMeta `json:",inline"`
    metav1.ListMeta `json:"metadata,omitempty"`
    Items           []AgentRuntime `json:"items"`
}
```

### codeinterpreter_types.go — CodeInterpreter and shared types

```go
// +genclient
// +k8s:deepcopy-gen:interfaces=k8s.io/apimachinery/pkg/runtime.Object
// +kubebuilder:object:root=true
// +kubebuilder:subresource:status
// +kubebuilder:resource:scope=Namespaced
// +kubebuilder:printcolumn:name="Age",type="date",JSONPath=".metadata.creationTimestamp"
type CodeInterpreter struct {
    metav1.TypeMeta   `json:",inline"`
    metav1.ObjectMeta `json:"metadata,omitempty"`
    Spec   CodeInterpreterSpec   `json:"spec"`
    Status CodeInterpreterStatus `json:"status,omitempty"`
}

type CodeInterpreterSpec struct {
    // +optional
    Ports []TargetPort `json:"ports,omitempty"`
    // +kubebuilder:validation:Required
    Template *CodeInterpreterSandboxTemplate `json:"template"`
    // +kubebuilder:default="15m"
    SessionTimeout *metav1.Duration `json:"sessionTimeout,omitempty"`
    // +kubebuilder:default="8h"
    MaxSessionDuration *metav1.Duration `json:"maxSessionDuration,omitempty"`
    // +optional
    WarmPoolSize *int32 `json:"warmPoolSize,omitempty"`
    // +kubebuilder:default="picod"
    // +kubebuilder:validation:Enum=picod;none
    // +optional
    AuthMode AuthModeType `json:"authMode,omitempty"`
}

type CodeInterpreterStatus struct {
    // +optional
    Conditions []metav1.Condition `json:"conditions,omitempty"`
    // +optional
    Ready bool `json:"ready,omitempty"`
}

type CodeInterpreterSandboxTemplate struct {
    // +optional
    Labels map[string]string `json:"labels,omitempty"`
    // +optional
    Annotations map[string]string `json:"annotations,omitempty"`
    // +optional
    RuntimeClassName *string `json:"runtimeClassName,omitempty"`
    Image string `json:"image,omitempty"`
    // +optional
    ImagePullPolicy corev1.PullPolicy `json:"imagePullPolicy,omitempty"`
    // +optional
    // +patchMergeKey=name
    // +patchStrategy=merge
    // +listType=map
    // +listMapKey=name
    ImagePullSecrets []corev1.LocalObjectReference `json:"imagePullSecrets,omitempty"`
    // +optional
    Environment []corev1.EnvVar `json:"environment,omitempty"`
    // +optional
    // +listType=atomic
    Command []string `json:"command,omitempty"`
    // +optional
    Args []string `json:"args,omitempty"`
    // +optional
    Resources corev1.ResourceRequirements `json:"resources,omitempty"`
}

type TargetPort struct {
    // +optional
    PathPrefix string `json:"pathPrefix,omitempty"`
    // +optional
    Name string `json:"name,omitempty"`
    Port uint32 `json:"port"`
    // +kubebuilder:default=HTTP
    // +kubebuilder:validation:Enum=HTTP;HTTPS;
    Protocol ProtocolType `json:"protocol"`
}

type AuthModeType string

const (
    AuthModePicoD AuthModeType = "picod"
    AuthModeNone  AuthModeType = "none"
)

type ProtocolType string

const (
    ProtocolTypeHTTP  ProtocolType = "HTTP"
    ProtocolTypeHTTPS ProtocolType = "HTTPS"
)

// +k8s:deepcopy-gen:interfaces=k8s.io/apimachinery/pkg/runtime.Object
// +kubebuilder:object:root=true
type CodeInterpreterList struct {
    metav1.TypeMeta `json:",inline"`
    metav1.ListMeta `json:"metadata,omitempty"`
    Items           []CodeInterpreter `json:"items"`
}
```

## Package `github.com/volcano-sh/agentcube/pkg/common/types`

```go
const (
    AgentRuntimeKind    = "AgentRuntime"
    CodeInterpreterKind = "CodeInterpreter"
    SandboxKind         = "Sandbox"
    SandboxClaimsKind   = "SandboxClaim"
)

type SandboxInfo struct {
    Kind             string              `json:"kind"`
    SandboxID        string              `json:"sandboxId"`
    SandboxNamespace string              `json:"sandboxNamespace"`
    Name             string              `json:"name"`
    EntryPoints      []SandboxEntryPoint `json:"entryPoints"`
    SessionID        string              `json:"sessionId"`
    CreatedAt        time.Time           `json:"createdAt"`
    ExpiresAt        time.Time           `json:"expiresAt"`
    Status string `json:"status"`
}

type SandboxEntryPoint struct {
    Path     string `json:"path"`
    Protocol string `json:"protocol"`
    Endpoint string `json:"endpoint"`
}

type CreateSandboxRequest struct {
    Kind      string `json:"kind"`
    Name      string `json:"name"`
    Namespace string `json:"namespace"`
}

type CreateSandboxResponse struct {
    SessionID   string              `json:"sessionId"`
    SandboxID   string              `json:"sandboxId"`
    SandboxName string              `json:"sandboxName"`
    EntryPoints []SandboxEntryPoint `json:"entryPoints"`
}

func (car *CreateSandboxRequest) Validate() error
```

## Package `github.com/volcano-sh/agentcube/pkg/api`

```go
const (
    resourceGroup               = "agentcube.volcano.sh"
    sessionResourceName         = "sessions"
    agentRuntimeResourceName    = "agentruntimes"
    codeInterpreterResourceName = "codeinterpreters"
)

var (
    ErrAgentRuntimeNotFound    = errors.New("agent runtime not found")
    ErrCodeInterpreterNotFound = errors.New("code interpreter not found")
    ErrTemplateMissing         = errors.New("resource has no pod template")
    ErrPublicKeyMissing        = errors.New("public key not yet loaded from Router Secret")
)

func NewSessionNotFoundError(sessionID string) error
func NewSandboxTemplateNotFoundError(namespace, name, kind string) error
func NewUpstreamUnavailableError(err error) error
func NewInternalError(err error) error
```

## Package `github.com/volcano-sh/agentcube/pkg/workloadmanager`

### Config and Server

```go
type Config struct {
    Port             string
    RuntimeClassName string
    EnableTLS        bool
    TLSCert          string
    TLSKey           string
    EnableAuth       bool
}

type Server struct {
    config            *Config
    router            *gin.Engine
    httpServer        *http.Server
    k8sClient         *K8sClient
    sandboxController *SandboxReconciler
    tokenCache        *TokenCache
    informers         *Informers
    storeClient       store.Store
    wg                sync.WaitGroup
}
```

### HTTP routes

| Method | Path | Auth middleware | Handler |
|--------|------|-----------------|---------|
| GET | `/health` | No | `handleHealth` |
| POST | `/v1/agent-runtime` | If `EnableAuth` | `handleAgentRuntimeCreate` |
| DELETE | `/v1/agent-runtime/sessions/:sessionId` | If `EnableAuth` | `handleDeleteSandbox` |
| POST | `/v1/code-interpreter` | If `EnableAuth` | `handleCodeInterpreterCreate` |
| DELETE | `/v1/code-interpreter/sessions/:sessionId` | If `EnableAuth` | `handleDeleteSandbox` |

### ErrorResponse

```go
type ErrorResponse struct {
    Message string `json:"message"`
}
```

### K8sClient and defaults

```go
const (
    DefaultSandboxTTL         = 8 * time.Hour
    DefaultSandboxIdleTimeout = 15 * time.Minute
)

var (
    SessionIdLabelKey         = "runtime.agentcube.io/session-id"
    WorkloadNameLabelKey      = "runtime.agentcube.io/workload-name"
    SandboxNameLabelKey       = "runtime.agentcube.io/sandbox-name"
    LastActivityAnnotationKey = "last-activity-time"
    IdleTimeoutAnnotationKey  = "runtime.agentcube.io/idle-timeout"
)

type K8sClient struct {
    clientset       *kubernetes.Clientset
    dynamicClient   dynamic.Interface
    scheme          *runtime.Scheme
    baseConfig      *rest.Config
    clientCache     *ClientCache
    dynamicInformer dynamicinformer.DynamicSharedInformerFactory
    informerFactory informers.SharedInformerFactory
    podInformer     cache.SharedIndexInformer
    podLister       listersv1.PodLister
}
```

- REST config: `QPS = 50`, `Burst = 100`; in-cluster config else kubeconfig loading rules.
- `NewClientCache(100)` for user dynamic clients.

### GVR variables (`informers.go`)

```go
var (
    AgentRuntimeGVR = schema.GroupVersionResource{
        Group: "runtime.agentcube.volcano.sh", Version: "v1alpha1", Resource: "agentruntimes",
    }
    CodeInterpreterGVR = schema.GroupVersionResource{
        Group: "runtime.agentcube.volcano.sh", Version: "v1alpha1", Resource: "codeinterpreters",
    }
    SandboxGVR = schema.GroupVersionResource{
        Group: "agents.x-k8s.io", Version: "v1alpha1", Resource: "sandboxes",
    }
    SandboxClaimGVR = schema.GroupVersionResource{
        Group: "extensions.agents.x-k8s.io", Version: "v1alpha1", Resource: "sandboxclaims",
    }
)
```

### Identity secret (workload_builder.go)

```go
const (
    IdentitySecretName = "picod-router-identity"
    PublicKeyDataKey   = "public.pem"
)

var IdentitySecretNamespace = "default" // overridden by env AGENTCUBE_NAMESPACE if set
```

### Sandbox reconciler

```go
type SandboxReconciler struct {
    client.Client
    Scheme *runtime.Scheme
    watchers map[types.NamespacedName]chan SandboxStatusUpdate
    mu       sync.RWMutex
}

type SandboxStatusUpdate struct {
    Sandbox *sandboxv1alpha1.Sandbox
}
```

- `Reconcile`: when `getSandboxStatus(sandbox) == "running"`, notify waiter channel (buffer 1), non-blocking send with `default` branch warning on full channel.
- `getSandboxStatus`: returns `"running"` if a condition has `Type == string(sandboxv1alpha1.SandboxConditionReady)` and `Status == metav1.ConditionTrue`, else `"unknown"`.

### Garbage collector

```go
const gcOnceTimeout = 2 * time.Minute

type garbageCollector struct {
    k8sClient   *K8sClient
    interval    time.Duration
    storeClient store.Store
}
```

- `newGarbageCollector(k8s, store, 15*time.Second)` — **GC interval: 15s**.
- Per tick: `ListInactiveSandboxes(ctx, time.Now().Add(-DefaultSandboxIdleTimeout), 16)` — **batch size 16**.
- `ListExpiredSandboxes(ctx, time.Now(), 16)` — **batch size 16**.
- Single tick context timeout: **2 minutes**.

### Token cache

- `NewTokenCache(1000, 5*time.Minute)` — max entries **1000**, TTL **5m** per entry (LRU + last-access expiry).

### Auth context keys

```go
type contextKey string

const (
    contextKeyUserToken          contextKey = "userToken"
    contextKeyServiceAccount     contextKey = "serviceAccount"
    contextKeyServiceAccountName contextKey = "serviceAccountName"
    contextKeyNamespace          contextKey = "namespace"
)
```

### CLI flags (`cmd/workload-manager/main.go`)

| Flag | Default | Meaning |
|------|---------|---------|
| `-port` | `8080` | API port |
| `-runtime-class-name` | `kuasar-vmm` | Stored on `Config.RuntimeClassName` (flag parsed in `main`; **not read** elsewhere in `pkg/workloadmanager` in current source) |
| `-enable-tls` | `false` | TLS |
| `-tls-cert` | `""` | Cert path |
| `-tls-key` | `""` | Key path |
| `-enable-auth` | `false` | TokenReview auth |

- Controller-runtime manager: metrics bind `0`, health probe `0`.
- Shutdown: HTTP shutdown timeout **15s**, then cancel ctx, `WaitForBackgroundWorkers`, `CloseStore`.

### Store dependency

```go
// github.com/volcano-sh/agentcube/pkg/store
type Store interface {
    Ping(ctx context.Context) error
    GetSandboxBySessionID(ctx context.Context, sessionID string) (*types.SandboxInfo, error)
    StoreSandbox(ctx context.Context, sandboxStore *types.SandboxInfo) error
    UpdateSandbox(ctx context.Context, sandboxStore *types.SandboxInfo) error
    DeleteSandboxBySessionID(ctx context.Context, sessionID string) error
    ListExpiredSandboxes(ctx context.Context, before time.Time, limit int64) ([]*types.SandboxInfo, error)
    ListInactiveSandboxes(ctx context.Context, before time.Time, limit int64) ([]*types.SandboxInfo, error)
    UpdateSessionLastActivity(ctx context.Context, sessionID string, at time.Time) error
    Close() error
}
```

Server uses `store.Storage()` singleton.

### Sandbox build notes

- AgentRuntime: sandbox name `{workloadName}-{RandString(8)}`, UUID session ID, ports from `spec.Ports`, TTL/idle from `MaxSessionDuration` / `SessionTimeout` when non-nil.
- CodeInterpreter: default ports if empty: single `TargetPort{Port:8080, Protocol:ProtocolTypeHTTP, PathPrefix:"/"}`; if `WarmPoolSize > 0`: creates `SandboxClaim` + minimal `Sandbox` metadata only, `sandboxEntry.Kind = SandboxClaimsKind`; else builds full `Sandbox` with container `code-interpreter` and optional `PICOD_AUTH_PUBLIC_KEY` when `AuthMode == picod`.
- `buildSandboxObject`: APIVersion `agents.x-k8s.io/v1alpha1`, Kind `Sandbox`, labels include `managed-by: agentcube-workload-manager`, annotation `IdleTimeoutAnnotationKey` = idle duration string, lifecycle `ShutdownTime` = now+TTL, `Replicas: ptr.To[int32](1)`.

### Pod name annotation

- Read from created sandbox: key from `sigs.k8s.io/agent-sandbox/controllers`.`SandboxPodNameAnnotation` (comment in source documents value `agents.x-k8s.io/sandbox-pod-name`).

## CodeInterpreter controller (supplementary)

- Reconciles `CodeInterpreter`; when `WarmPoolSize > 0` ensures `SandboxTemplate` (name = CI name) and `SandboxWarmPool` (name = CI name, replicas = WarmPoolSize, templateRef name = CI name); injects `PICOD_AUTH_PUBLIC_KEY` in template unless `AuthModeNone`; requeues 5s if public key not cached and auth not none.
