# AR-035 — client-go 类型客户端生成 Tasks

**Module**: `client-go`
**Language**: Go
**Size**: L
**Stage**: ST-3 completed

---

## Tasks

### T001: Create client-go module structure
- [ ] Create `client-go/` directory
- [ ] Create `client-go/go.mod` with module `github.com/volcano-sh/agentcube/client-go`
- [ ] Set Go version to `1.21` in go.mod
- [ ] Verify module initialized with `go mod init`

### T002: Add Kubernetes dependencies
- [ ] Add `k8s.io/api v0.28.0` to go.mod
- [ ] Add `k8s.io/apimachinery v0.28.0` to go.mod
- [ ] Add `k8s.io/client-go v0.28.0` to go.mod
- [ ] Add `k8s.io/code-generator v0.28.0` to go.mod
- [ ] Run `go mod tidy` to resolve dependencies
- [ ] Verify go.sum is generated

### T003: Create directory structure for generated code
- [ ] Create `client-go/clientset/versioned/` directory
- [ ] Create `client-go/informers/externalversions/` directory
- [ ] Create `client-go/listers/` directory
- [ ] Verify all directories exist

### T004: Create hack directory for code generation
- [ ] Create `client-go/hack/` directory
- [ ] Create `client-go/hack/boilerplate.go.txt` with Apache 2.0 license header
- [ ] Verify boilerplate file exists

### T005: Create code generation script
- [ ] Create `client-go/hack/update-codegen.sh`
- [ ] Make script executable (`chmod +x`)
- [ ] Add client-gen invocation with correct parameters:
  - `--input-base="github.com/volcano-sh/agentcube/pkg/apis"`
  - `--input="runtime/v1alpha1"`
  - `--clientset-path="github.com/volcano-sh/agentcube/client-go/clientset"`
- [ ] Add informer-gen invocation with correct parameters:
  - `--input-dirs="github.com/volcano-sh/agentcube/pkg/apis/runtime/v1alpha1"`
  - `--versioned-clientset-package="github.com/volcano-sh/agentcube/client-go/clientset/versioned"`
  - `--listers-package="github.com/volcano-sh/agentcube/client-go/listers"`
- [ ] Add lister-gen invocation with correct parameters
- [ ] Set `GO111MODULE=on` and `GOPATH` environment variables
- [ ] Verify script syntax is correct

### T006: Create Makefile for code generation
- [ ] Create `client-go/Makefile`
- [ ] Add `gen-client` target that calls `hack/update-codegen.sh`
- [ ] Add `gen-client-verify` target for verification
- [ ] Add `go mod tidy` after code generation
- [ ] Verify Makefile syntax

### T007: Run code generation
- [ ] Run `make gen-client`
- [ ] Verify no errors during generation
- [ ] Check that `client-go/clientset/versioned/clientset.go` is created
- [ ] Check that `client-go/clientset/versioned/doc.go` is created
- [ ] Check that `client-go/clientset/versioned/scheme/register.go` is created

### T008: Verify clientset structure
- [ ] Verify `client-go/clientset/versioned/clientset.go` has `Interface` interface
- [ ] Verify `Interface` has `RuntimeV1alpha1()` method
- [ ] Verify `Interface` has `Discovery()` method
- [ ] Verify `Clientset` struct is defined
- [ ] Verify `NewForConfig()` function exists
- [ ] Verify `NewForConfigOrDie()` function exists

### T009: Verify RuntimeV1alpha1 client
- [ ] Verify `client-go/clientset/versioned/typed/runtime/v1alpha1/runtime_client.go` exists
- [ ] Verify `RuntimeV1alpha1Client` struct is defined
- [ ] Verify `RuntimeV1alpha1Interface` is defined
- [ ] Verify `AgentRuntimes()` method exists
- [ ] Verify `CodeInterpreters()` method exists

### T010: Verify AgentRuntime client
- [ ] Verify `client-go/clientset/versioned/typed/runtime/v1alpha1/agentruntime.go` exists
- [ ] Verify `AgentRuntimeInterface` is defined
- [ ] Verify `Create()` method exists
- [ ] Verify `Update()` method exists
- [ ] Verify `UpdateStatus()` method exists
- [ ] Verify `Delete()` method exists
- [ ] Verify `Get()` method exists
- [ ] Verify `List()` method exists
- [ ] Verify `Watch()` method exists
- [ ] Verify `Patch()` method exists

### T011: Verify CodeInterpreter client
- [ ] Verify `client-go/clientset/versioned/typed/runtime/v1alpha1/codeinterpreter.go` exists
- [ ] Verify `CodeInterpreterInterface` is defined
- [ ] Verify `Create()` method exists
- [ ] Verify `Update()` method exists
- [ ] Verify `UpdateStatus()` method exists
- [ ] Verify `Delete()` method exists
- [ ] Verify `Get()` method exists
- [ ] Verify `List()` method exists
- [ ] Verify `Watch()` method exists
- [ ] Verify `Patch()` method exists

### T012: Verify fake clientset
- [ ] Verify `client-go/clientset/versioned/fake/clientset_generated.go` exists
- [ ] Verify `FakeClientset` struct is defined
- [ ] Verify `NewSimpleClientset()` function exists

### T013: Verify informer factory
- [ ] Verify `client-go/informers/externalversions/factory.go` exists
- [ ] Verify `SharedInformerFactory` interface is defined
- [ ] Verify `NewSharedInformerFactory()` function exists
- [ ] Verify `Start()` method exists
- [ ] Verify `WaitForCacheSync()` method exists

### T014: Verify generic informer
- [ ] Verify `client-go/informers/externalversions/generic.go` exists
- [ ] Verify `GenericInformer` interface is defined
- [ ] Verify `ForResource()` method exists

### T015: Verify runtime informers
- [ ] Verify `client-go/informers/externalversions/runtime/interface.go` exists
- [ ] Verify `client-go/informers/externalversions/runtime/v1alpha1/interface.go` exists
- [ ] Verify `AgentRuntimes()` method exists
- [ ] Verify `CodeInterpreters()` method exists

### T016: Verify AgentRuntime informer
- [ ] Verify `client-go/informers/externalversions/runtime/v1alpha1/agentruntime.go` exists
- [ ] Verify `AgentRuntimeInformer` interface is defined
- [ ] Verify `Informer()` method returns `cache.SharedIndexInformer`
- [ ] Verify `Lister()` method returns `v1alpha1.AgentRuntimeLister`

### T017: Verify CodeInterpreter informer
- [ ] Verify `client-go/informers/externalversions/runtime/v1alpha1/codeinterpreter.go` exists
- [ ] Verify `CodeInterpreterInformer` interface is defined
- [ ] Verify `Informer()` method returns `cache.SharedIndexInformer`
- [ ] Verify `Lister()` method returns `v1alpha1.CodeInterpreterLister`

### T018: Verify listers
- [ ] Verify `client-go/listers/runtime/v1alpha1/agentruntime.go` exists
- [ ] Verify `AgentRuntimeLister` interface is defined
- [ ] Verify `AgentRuntimeNamespaceLister` interface is defined
- [ ] Verify `List()` method exists
- [ ] Verify `AgentRuntimes()` method exists
- [ ] Verify `client-go/listers/runtime/v1alpha1/codeinterpreter.go` exists
- [ ] Verify `CodeInterpreterLister` interface is defined
- [ ] Verify `CodeInterpreterNamespaceLister` interface is defined

### T019: Verify fake clients
- [ ] Verify `client-go/clientset/versioned/typed/runtime/v1alpha1/fake/fake_agentruntime.go` exists
- [ ] Verify `client-go/clientset/versioned/typed/runtime/v1alpha1/fake/fake_codeinterpreter.go` exists
- [ ] Verify fake methods are implemented

### T020: Build generated code
- [ ] Run `go build ./client-go/...`
- [ ] Verify no compilation errors
- [ ] Verify all imports resolve correctly

### T021: Create README.md
- [ ] Create `client-go/README.md`
- [ ] Add installation instructions (`go get github.com/volcano-sh/agentcube/client-go`)
- [ ] Add basic usage example for creating ClientSet
- [ ] Add AgentRuntime CRUD example
- [ ] Add CodeInterpreter CRUD example
- [ ] Add informer usage example
- [ ] Add watch example

### T022: Create client usage example
- [ ] Create `client-go/examples/client_example.go`
- [ ] Example: Create ClientSet from config
- [ ] Example: Create AgentRuntime
- [ ] Example: Get AgentRuntime
- [ ] Example: List AgentRuntimes
- [ ] Example: Update AgentRuntime
- [ ] Example: Delete AgentRuntime
- [ ] Example: Watch AgentRuntimes

### T023: Create informer usage example
- [ ] Create `client-go/examples/informer_example.go`
- [ ] Example: Create SharedInformerFactory
- [ ] Example: Get AgentRuntimeInformer
- [ ] Example: Register event handlers (Add, Update, Delete)
- [ ] Example: Start informer
- [ ] Example: Use lister for read operations

### T024: Create unit test for AgentRuntime client
- [ ] Create `client-go/clientset/versioned/typed/runtime/v1alpha1/agentruntime_test.go`
- [ ] Test `Create()` with valid AgentRuntime
- [ ] Test `Get()` returns correct AgentRuntime
- [ ] Test `List()` returns multiple AgentRuntimes
- [ ] Test `Update()` modifies AgentRuntime
- [ ] Test `UpdateStatus()` modifies status only
- [ ] Test `Delete()` removes AgentRuntime
- [ ] Test error handling for non-existent resource

### T025: Create unit test for CodeInterpreter client
- [ ] Create `client-go/clientset/versioned/typed/runtime/v1alpha1/codeinterpreter_test.go`
- [ ] Test `Create()` with valid CodeInterpreter
- [ ] Test `Get()` returns correct CodeInterpreter
- [ ] Test `List()` returns multiple CodeInterpreters
- [ ] Test `Update()` modifies CodeInterpreter
- [ ] Test `UpdateStatus()` modifies status only
- [ ] Test `Delete()` removes CodeInterpreter
- [ ] Test error handling for non-existent resource

### T026: Create unit test for informer
- [ ] Create `client-go/informers/externalversions/runtime/v1alpha1/agentruntime_test.go`
- [ ] Test informer initialization
- [ ] Test Add event is received
- [ ] Test Update event is received
- [ ] Test Delete event is received
- [ ] Test cache synchronization

### T027: Run unit tests
- [ ] Run `go test ./client-go/clientset/...`
- [ ] Run `go test ./client-go/informers/...`
- [ ] Run `go test ./client-go/listers/...`
- [ ] Verify all tests pass
- [ ] Verify test coverage

### T028: Create code generation verification script
- [ ] Create `client-go/hack/verify-codegen.sh`
- [ ] Script should run code generation and check for diffs
- [ ] Script should fail if generated code differs
- [ ] Verify script works correctly

### T029: Test code generation verification
- [ ] Run `make gen-client-verify`
- [ ] Verify no changes detected (initial run)
- [ ] Modify a generated file slightly
- [ ] Run verification again and verify it detects changes
- [ ] Restore original file

### T030: Create .gitignore
- [ ] Create `client-go/.gitignore`
- [ ] Ignore binaries
- [ ] Ignore test output
- [ ] Ignore IDE files

### T031: Verify package documentation
- [ ] Verify `client-go/clientset/versioned/doc.go` has package docs
- [ ] Verify `client-go/clientset/versioned/scheme/doc.go` has scheme docs
- [ ] Verify `client-go/informers/externalversions/doc.go` has docs
- [ ] Verify all public types have comments

### T032: Test against real API types
- [ ] Verify client can import `github.com/volcano-sh/agentcube/pkg/apis/runtime/v1alpha1`
- [ ] Verify AgentRuntime type is accessible
- [ ] Verify CodeInterpreter type is accessible
- [ ] Verify types are correctly registered in scheme

### T033: Verify clientset REST configuration
- [ ] Verify `setConfigDefaults()` sets correct GroupVersion
- [ ] Verify GroupVersion is `runtime.agentcube.volcano.sh/v1alpha1`
- [ ] Verify APIPath is `/apis`
- [ ] Verify NegotiatedSerializer is configured

### T034: Verify AgentRuntime REST endpoints
- [ ] Verify `Get()` uses `/apis/runtime.agentcube.volcano.sh/v1alpha1/namespaces/{ns}/agentruntimes/{name}`
- [ ] Verify `List()` uses `/apis/runtime.agentcube.volcano.sh/v1alpha1/namespaces/{ns}/agentruntimes`
- [ ] Verify `Create()` uses POST to `/apis/runtime.agentcube.volcano.sh/v1alpha1/namespaces/{ns}/agentruntimes`
- [ ] Verify `Update()` uses PUT to `/apis/runtime.agentcube.volcano.sh/v1alpha1/namespaces/{ns}/agentruntimes/{name}`
- [ ] Verify `UpdateStatus()` uses PUT to `/apis/runtime.agentcube.volcano.sh/v1alpha1/namespaces/{ns}/agentruntimes/{name}/status`
- [ ] Verify `Delete()` uses DELETE to `/apis/runtime.agentcube.volcano.sh/v1alpha1/namespaces/{ns}/agentruntimes/{name}`

### T035: Verify CodeInterpreter REST endpoints
- [ ] Verify `Get()` uses `/apis/runtime.agentcube.volcano.sh/v1alpha1/namespaces/{ns}/codeinterpreters/{name}`
- [ ] Verify `List()` uses `/apis/runtime.agentcube.volcano.sh/v1alpha1/namespaces/{ns}/codeinterpreters`
- [ ] Verify `Create()` uses POST to `/apis/runtime.agentcube.volcano.sh/v1alpha1/namespaces/{ns}/codeinterpreters`
- [ ] Verify `Update()` uses PUT to `/apis/runtime.agentcube.volcano.sh/v1alpha1/namespaces/{ns}/codeinterpreters/{name}`
- [ ] Verify `UpdateStatus()` uses PUT to `/apis/runtime.agentcube.volcano.sh/v1alpha1/namespaces/{ns}/codeinterpreters/{name}/status`
- [ ] Verify `Delete()` uses DELETE to `/apis/runtime.agentcube.volcano.sh/v1alpha1/namespaces/{ns}/codeinterpreters/{name}`

### T036: Verify informer configuration
- [ ] Verify informer uses correct GroupVersionResource
- [ ] Verify informer resync period is configurable
- [ ] Verify informer supports namespace filtering
- [ ] Verify informer supports tweak list options

### T037: Final integration check
- [ ] Run `go mod tidy` to clean up dependencies
- [ ] Run `go build ./...` to ensure everything compiles
- [ ] Run `go test ./...` to run all tests
- [ ] Verify all generated files have correct license headers
- [ ] Verify no TODO or FIXME comments in generated code

---

## Verification

- [ ] All 37 tasks completed
- [ ] Go module compiles without errors
- [ ] All unit tests pass
- [ ] Code generation script produces correct output
- [ ] Verification script works correctly
- [ ] All REST endpoints configured correctly
- [ ] Informers and listers work as expected
- [ ] Documentation is complete
- [ ] Examples are functional
- [ ] Generated code follows Kubernetes conventions