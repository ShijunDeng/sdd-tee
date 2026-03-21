# client-go library

Generated Kubernetes client code for API group **`runtime.agentcube.volcano.sh` / `v1alpha1`**, module path **`github.com/volcano-sh/agentcube/client-go`**. Source reference: `/tmp/agentcube-ref/client-go/`.

## Clientset

### `Interface` (`clientset/versioned/clientset.go`)

```go
type Interface interface {
	Discovery() discovery.DiscoveryInterface
	RuntimeV1alpha1() runtimev1alpha1.RuntimeV1alpha1Interface
}
```

### `Clientset` struct

Embeds `*discovery.DiscoveryClient` and holds `runtimeV1alpha1 *runtimev1alpha1.RuntimeV1alpha1Client`.

**Constructors**

- `NewForConfig(c *rest.Config) (*Clientset, error)`
- `NewForConfigAndClient(c *rest.Config, httpClient *http.Client) (*Clientset, error)`
- `NewForConfigOrDie(c *rest.Config) *Clientset`
- `New(c rest.Interface) *Clientset`

**Group accessor:** `RuntimeV1alpha1() runtimev1alpha1.RuntimeV1alpha1Interface`

---

## Typed client — `runtime/v1alpha1`

### `RuntimeV1alpha1Interface` (`clientset/versioned/typed/runtime/v1alpha1/runtime_client.go`)

```go
type RuntimeV1alpha1Interface interface {
	RESTClient() rest.Interface
	AgentRuntimesGetter
	CodeInterpretersGetter
}
```

`RuntimeV1alpha1Client` implements this interface. REST defaults: `GroupVersion` = `pkg/apis/runtime/v1alpha1`.SchemeGroupVersion, `APIPath` = `/apis`, negotiated serializer from `clientset/versioned/scheme`.

### `AgentRuntimesGetter` / `AgentRuntimeInterface` (`.../agentruntime.go`)

```go
type AgentRuntimesGetter interface {
	AgentRuntimes(namespace string) AgentRuntimeInterface
}

type AgentRuntimeInterface interface {
	Create(ctx context.Context, agentRuntime *runtimev1alpha1.AgentRuntime, opts metav1.CreateOptions) (*runtimev1alpha1.AgentRuntime, error)
	Update(ctx context.Context, agentRuntime *runtimev1alpha1.AgentRuntime, opts metav1.UpdateOptions) (*runtimev1alpha1.AgentRuntime, error)
	UpdateStatus(ctx context.Context, agentRuntime *runtimev1alpha1.AgentRuntime, opts metav1.UpdateOptions) (*runtimev1alpha1.AgentRuntime, error)
	Delete(ctx context.Context, name string, opts metav1.DeleteOptions) error
	DeleteCollection(ctx context.Context, opts metav1.DeleteOptions, listOpts metav1.ListOptions) error
	Get(ctx context.Context, name string, opts metav1.GetOptions) (*runtimev1alpha1.AgentRuntime, error)
	List(ctx context.Context, opts metav1.ListOptions) (*runtimev1alpha1.AgentRuntimeList, error)
	Watch(ctx context.Context, opts metav1.ListOptions) (watch.Interface, error)
	Patch(ctx context.Context, name string, pt types.PatchType, data []byte, opts metav1.PatchOptions, subresources ...string) (*runtimev1alpha1.AgentRuntime, error)
	AgentRuntimeExpansion
}
```

REST resource plural: **`agentruntimes`**.

### `CodeInterpretersGetter` / `CodeInterpreterInterface` (`.../codeinterpreter.go`)

Same method shape as `AgentRuntimeInterface`, types `*runtimev1alpha1.CodeInterpreter` / `CodeInterpreterList`. REST resource plural: **`codeinterpreters`**.

### Expansion hooks (`generated_expansion.go`)

```go
type AgentRuntimeExpansion interface{}
type CodeInterpreterExpansion interface{}
```

(Empty — reserved for custom methods.)

### Fake clients (`typed/runtime/v1alpha1/fake/`)

`fake_runtime_client.go`, `fake_agentruntime.go`, `fake_codeinterpreter.go` — test doubles implementing the typed interfaces; `doc.go` markers.

---

## Scheme (`clientset/versioned/scheme/`)

| File | Role |
|------|------|
| `register.go` | Builds `Scheme`, `Codecs`, `ParameterCodec`; `AddToScheme` registers `runtime/v1alpha1` types |
| `doc.go` | Package doc |

---

## Informer factory

### `SharedInformerFactory` (`informers/externalversions/factory.go`)

```go
type SharedInformerFactory interface {
	internalinterfaces.SharedInformerFactory
	Start(stopCh <-chan struct{})
	Shutdown()
	WaitForCacheSync(stopCh <-chan struct{}) map[reflect.Type]bool
	ForResource(resource schema.GroupVersionResource) (GenericInformer, error)
	InformerFor(obj runtime.Object, newFunc internalinterfaces.NewInformerFunc) cache.SharedIndexInformer
	Runtime() externalversionsruntime.Interface
}
```

**Constructors / options**

- `NewSharedInformerFactory(client versioned.Interface, defaultResync time.Duration)`
- `NewSharedInformerFactoryWithOptions(client, defaultResync, options ...SharedInformerOption)`
- `NewFilteredSharedInformerFactory` (deprecated alias to WithOptions)
- Options: `WithCustomResyncConfig`, `WithTweakListOptions`, `WithNamespace`, `WithTransform`

### Group interface (`informers/externalversions/runtime/interface.go`)

```go
type Interface interface {
	V1alpha1() v1alpha1.Interface
}
```

`New(factory, namespace, tweakListOptions)` returns group accessor.

### Version interface (`informers/externalversions/runtime/v1alpha1/interface.go`)

```go
type Interface interface {
	AgentRuntimes() AgentRuntimeInformer
	CodeInterpreters() CodeInterpreterInformer
}
```

### Per-type informers (`.../runtime/v1alpha1/agentruntime.go`, `codeinterpreter.go`)

Example (`AgentRuntimeInformer`):

```go
type AgentRuntimeInformer interface {
	Informer() cache.SharedIndexInformer
	Lister() runtimev1alpha1.AgentRuntimeLister
}
```

Also provides `NewAgentRuntimeInformer`, `NewFilteredAgentRuntimeInformer`, and analogous constructors for CodeInterpreter.

### Generic resource routing (`informers/externalversions/generic.go`)

`ForResource` switches on:

- `v1alpha1.SchemeGroupVersion.WithResource("agentruntimes")` → `f.Runtime().V1alpha1().AgentRuntimes().Informer()`
- `...WithResource("codeinterpreters")` → `...CodeInterpreters().Informer()`

### `internalinterfaces` (`informers/externalversions/internalinterfaces/factory_interfaces.go`)

```go
type NewInformerFunc func(versioned.Interface, time.Duration) cache.SharedIndexInformer
type SharedInformerFactory interface {
	Start(stopCh <-chan struct{})
	InformerFor(obj runtime.Object, newFunc NewInformerFunc) cache.SharedIndexInformer
}
type TweakListOptionsFunc func(*metav1.ListOptions)
```

---

## Listers (`listers/runtime/v1alpha1/`)

### `AgentRuntimeLister` / `AgentRuntimeNamespaceLister` (`agentruntime.go`)

```go
type AgentRuntimeLister interface {
	List(selector labels.Selector) ([]*runtimev1alpha1.AgentRuntime, error)
	AgentRuntimes(namespace string) AgentRuntimeNamespaceLister
	AgentRuntimeListerExpansion
}

type AgentRuntimeNamespaceLister interface {
	List(selector labels.Selector) ([]*runtimev1alpha1.AgentRuntime, error)
	Get(name string) (*runtimev1alpha1.AgentRuntime, error)
	AgentRuntimeNamespaceListerExpansion
}
```

`NewAgentRuntimeLister` uses `runtimev1alpha1.Resource("agentruntime").GroupResource()`.

### `CodeInterpreterLister` / `CodeInterpreterNamespaceLister` (`codeinterpreter.go`)

Same pattern for `CodeInterpreter`; `NewCodeInterpreterLister` uses `Resource("codeinterpreter").GroupResource()`.

### Expansion (`expansion_generated.go`)

Empty expansion interfaces for listers and namespace listers (all four types).

---

## Fake clientset (`clientset/versioned/fake/`)

| File | Role |
|------|------|
| `clientset_generated.go` | `NewSimpleClientset`, `NewClientset` — in-memory fake `Clientset` |
| `register.go` | Scheme registration for fakes |
| `doc.go` | Package doc |

---

## File index (all paths under `client-go/`)

| Path | Role |
|------|------|
| `clientset/versioned/clientset.go` | `Clientset`, `Interface`, constructors |
| `clientset/versioned/scheme/register.go` | Scheme / codecs for generated client |
| `clientset/versioned/scheme/doc.go` | Doc |
| `clientset/versioned/fake/clientset_generated.go` | Fake clientset implementation |
| `clientset/versioned/fake/register.go` | Fake scheme wiring |
| `clientset/versioned/fake/doc.go` | Doc |
| `clientset/versioned/typed/runtime/v1alpha1/runtime_client.go` | `RuntimeV1alpha1Client`, `RuntimeV1alpha1Interface` |
| `clientset/versioned/typed/runtime/v1alpha1/agentruntime.go` | `AgentRuntimeInterface`, typed REST client |
| `clientset/versioned/typed/runtime/v1alpha1/codeinterpreter.go` | `CodeInterpreterInterface`, typed REST client |
| `clientset/versioned/typed/runtime/v1alpha1/generated_expansion.go` | Expansion interfaces |
| `clientset/versioned/typed/runtime/v1alpha1/doc.go` | Doc |
| `clientset/versioned/typed/runtime/v1alpha1/fake/fake_runtime_client.go` | Fake runtime group client |
| `clientset/versioned/typed/runtime/v1alpha1/fake/fake_agentruntime.go` | Fake AgentRuntime client |
| `clientset/versioned/typed/runtime/v1alpha1/fake/fake_codeinterpreter.go` | Fake CodeInterpreter client |
| `clientset/versioned/typed/runtime/v1alpha1/fake/doc.go` | Doc |
| `informers/externalversions/factory.go` | `SharedInformerFactory`, options, `Start`/`Shutdown`/`WaitForCacheSync` |
| `informers/externalversions/generic.go` | `GenericInformer`, `ForResource` |
| `informers/externalversions/runtime/interface.go` | Group `runtime` informer accessor |
| `informers/externalversions/runtime/v1alpha1/interface.go` | `v1alpha1` informer accessors |
| `informers/externalversions/runtime/v1alpha1/agentruntime.go` | AgentRuntime informer + constructor |
| `informers/externalversions/runtime/v1alpha1/codeinterpreter.go` | CodeInterpreter informer + constructor |
| `informers/externalversions/internalinterfaces/factory_interfaces.go` | Small factory interface + `NewInformerFunc`, `TweakListOptionsFunc` |
| `listers/runtime/v1alpha1/agentruntime.go` | `AgentRuntimeLister`, namespace lister |
| `listers/runtime/v1alpha1/codeinterpreter.go` | `CodeInterpreterLister`, namespace lister |
| `listers/runtime/v1alpha1/expansion_generated.go` | Lister expansion interfaces |

**Regeneration:** `make gen-client` → `hack/update-codegen.sh` (`k8s.io/code-generator` v0.34.1, `--with-watch`, output package `github.com/volcano-sh/agentcube/client-go`).
