package workloadmanager_test

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync"
	"testing"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
	corev1 "k8s.io/api/core/v1"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/apis/meta/v1/unstructured"
	"k8s.io/apimachinery/pkg/runtime"
	dynamicfake "k8s.io/client-go/dynamic/fake"
	kubefake "k8s.io/client-go/kubernetes/fake"
	kubetesting "k8s.io/client-go/testing"

	runtimev1 "github.com/volcano-sh/agentcube/pkg/apis/runtime/v1alpha1"
	sandboxv1 "github.com/volcano-sh/agentcube/pkg/apis/agentsandbox/v1alpha1"
	commontypes "github.com/volcano-sh/agentcube/pkg/common/types"
	"github.com/volcano-sh/agentcube/pkg/store"
	"github.com/volcano-sh/agentcube/pkg/workloadmanager"
)

type memStore struct {
	mu sync.Mutex
	m  map[string]*store.Sandbox
}

func newMemStore() *memStore {
	return &memStore{m: map[string]*store.Sandbox{}}
}

func (m *memStore) Ping(ctx context.Context) error { return nil }

func (m *memStore) GetSandboxBySessionID(ctx context.Context, sessionID string) (*store.Sandbox, error) {
	m.mu.Lock()
	defer m.mu.Unlock()
	sb, ok := m.m[sessionID]
	if !ok {
		return nil, store.ErrNotFound
	}
	cp := *sb
	return &cp, nil
}

func (m *memStore) StoreSandbox(ctx context.Context, sb *store.Sandbox) error {
	m.mu.Lock()
	defer m.mu.Unlock()
	m.m[sb.SessionID] = sb
	return nil
}

func (m *memStore) UpdateSandbox(ctx context.Context, sb *store.Sandbox) error {
	m.mu.Lock()
	defer m.mu.Unlock()
	m.m[sb.SessionID] = sb
	return nil
}

func (m *memStore) DeleteSandboxBySessionID(ctx context.Context, sessionID string) error {
	m.mu.Lock()
	defer m.mu.Unlock()
	delete(m.m, sessionID)
	return nil
}

func (m *memStore) ListExpiredSandboxes(ctx context.Context, beforeUnix int64, limit int) ([]*store.Sandbox, error) {
	return nil, nil
}

func (m *memStore) ListInactiveSandboxes(ctx context.Context, lastActivityBeforeUnix int64, limit int) ([]*store.Sandbox, error) {
	return nil, nil
}

func (m *memStore) UpdateSessionLastActivity(ctx context.Context, sessionID string, ts int64) error {
	m.mu.Lock()
	defer m.mu.Unlock()
	if sb, ok := m.m[sessionID]; ok {
		sb.LastActivity = ts
	}
	return nil
}

func (m *memStore) Close() error { return nil }

func testScheme(t *testing.T) *runtime.Scheme {
	t.Helper()
	s := runtime.NewScheme()
	require.NoError(t, corev1.AddToScheme(s))
	require.NoError(t, runtimev1.AddToScheme(s))
	require.NoError(t, sandboxv1.AddToScheme(s))
	return s
}

// dynamic fake DeepCopy panics on uint64 in typed CRDs; use JSON-compatible maps for seeds.
func agentRuntimeUnstructured(name, ns string) *unstructured.Unstructured {
	return &unstructured.Unstructured{Object: map[string]interface{}{
		"apiVersion": "runtime.agentcube.volcano.sh/v1alpha1",
		"kind":       "AgentRuntime",
		"metadata": map[string]interface{}{
			"name": name, "namespace": ns,
		},
		"spec": map[string]interface{}{
			"targetPorts": []interface{}{
				map[string]interface{}{"pathPrefix": "/", "name": "http", "port": int64(8080), "protocol": "HTTP"},
			},
			"podTemplate": map[string]interface{}{
				"spec": map[string]interface{}{
					"containers": []interface{}{
						map[string]interface{}{"name": "c", "image": "busybox:latest"},
					},
				},
			},
		},
	}}
}

func codeInterpreterUnstructured(name, ns string) *unstructured.Unstructured {
	return &unstructured.Unstructured{Object: map[string]interface{}{
		"apiVersion": "runtime.agentcube.volcano.sh/v1alpha1",
		"kind":       "CodeInterpreter",
		"metadata":   map[string]interface{}{"name": name, "namespace": ns},
		"spec": map[string]interface{}{
			"ports": []interface{}{
				map[string]interface{}{"pathPrefix": "/", "name": "http", "port": int64(8080), "protocol": "HTTP"},
			},
			"template": map[string]interface{}{
				"image": "python:3.12",
			},
		},
	}}
}

func codeInterpreterNoTemplateUnstructured(name, ns string) *unstructured.Unstructured {
	return &unstructured.Unstructured{Object: map[string]interface{}{
		"apiVersion": "runtime.agentcube.volcano.sh/v1alpha1",
		"kind":       "CodeInterpreter",
		"metadata":   map[string]interface{}{"name": name, "namespace": ns},
		"spec": map[string]interface{}{
			"ports": []interface{}{
				map[string]interface{}{"pathPrefix": "/", "name": "h", "port": int64(9000), "protocol": "HTTP"},
			},
		},
	}}
}

func codeInterpreterUnstructuredPort(name, ns string, port int64) *unstructured.Unstructured {
	return &unstructured.Unstructured{Object: map[string]interface{}{
		"apiVersion": "runtime.agentcube.volcano.sh/v1alpha1",
		"kind":       "CodeInterpreter",
		"metadata":   map[string]interface{}{"name": name, "namespace": ns},
		"spec": map[string]interface{}{
			"ports": []interface{}{
				map[string]interface{}{"pathPrefix": "/", "name": "h", "port": port, "protocol": "HTTP"},
			},
			"template": map[string]interface{}{
				"image": "python:3.12",
			},
		},
	}}
}

func TestHealthEndpoint(t *testing.T) {
	s := testScheme(t)
	kube := kubefake.NewSimpleClientset()
	dyn := dynamicfake.NewSimpleDynamicClient(s)
	b := &workloadmanager.SandboxBuilder{Dyn: dyn, Kube: kube}
	srv := workloadmanager.NewAPIServer(workloadmanager.Config{Port: 8082}, kube, dyn, newMemStore(), b, nil, nil)

	w := httptest.NewRecorder()
	srv.Engine.ServeHTTP(w, httptest.NewRequest(http.MethodGet, "/health", nil))
	assert.Equal(t, http.StatusOK, w.Code)
	assert.Equal(t, "ok", w.Body.String())
}

func TestCreateAgentRuntime(t *testing.T) {
	s := testScheme(t)
	dyn := dynamicfake.NewSimpleDynamicClient(s, agentRuntimeUnstructured("demo", "default"))
	kube := kubefake.NewSimpleClientset()
	kube.PrependReactor("create", "pods", func(action kubetesting.Action) (bool, runtime.Object, error) {
		create := action.(kubetesting.CreateAction)
		pod := create.GetObject().(*corev1.Pod)
		if pod.Name == "" {
			pod.Name = "pod-ar-demo"
		}
		pod.Status.PodIP = "10.244.0.10"
		return false, nil, nil
	})

	b := &workloadmanager.SandboxBuilder{Dyn: dyn, Kube: kube}
	srv := workloadmanager.NewAPIServer(workloadmanager.Config{Port: 8082}, kube, dyn, newMemStore(), b, nil, nil)

	body := `{"name":"demo","namespace":"default","kind":"AgentRuntime"}`
	w := httptest.NewRecorder()
	req := httptest.NewRequest(http.MethodPost, "/v1/agent-runtime", strings.NewReader(body))
	req.Header.Set("Content-Type", "application/json")
	srv.Engine.ServeHTTP(w, req)
	require.Equal(t, http.StatusOK, w.Code, w.Body.String())

	var resp commontypes.CreateSandboxResponse
	require.NoError(t, json.Unmarshal(w.Body.Bytes(), &resp))
	assert.Equal(t, "10.244.0.10", resp.PodIP)
	assert.NotEmpty(t, resp.SandboxName)
}

func TestCreateCodeInterpreter(t *testing.T) {
	s := testScheme(t)
	dyn := dynamicfake.NewSimpleDynamicClient(s, codeInterpreterUnstructured("ci1", "default"))
	kube := kubefake.NewSimpleClientset()
	kube.PrependReactor("create", "pods", func(action kubetesting.Action) (bool, runtime.Object, error) {
		create := action.(kubetesting.CreateAction)
		pod := create.GetObject().(*corev1.Pod)
		if pod.Name == "" {
			pod.Name = "pod-ci1"
		}
		pod.Status.PodIP = "10.244.0.11"
		return false, nil, nil
	})
	b := &workloadmanager.SandboxBuilder{Dyn: dyn, Kube: kube}
	srv := workloadmanager.NewAPIServer(workloadmanager.Config{Port: 8082}, kube, dyn, newMemStore(), b, nil, nil)

	body := `{"name":"ci1","namespace":"default","kind":"CodeInterpreter"}`
	w := httptest.NewRecorder()
	req := httptest.NewRequest(http.MethodPost, "/v1/code-interpreter", strings.NewReader(body))
	req.Header.Set("Content-Type", "application/json")
	srv.Engine.ServeHTTP(w, req)
	require.Equal(t, http.StatusOK, w.Code, w.Body.String())
	var resp commontypes.CreateSandboxResponse
	require.NoError(t, json.Unmarshal(w.Body.Bytes(), &resp))
	assert.Equal(t, "10.244.0.11", resp.PodIP)
}

func TestDeleteSandbox(t *testing.T) {
	s := testScheme(t)
	st := newMemStore()
	require.NoError(t, st.StoreSandbox(context.Background(), &store.Sandbox{
		SessionID:     "sid-1",
		Namespace:     "default",
		SandboxCRName: "sbx-1",
		ResourceKind:  "agent-runtime",
	}))

	sbObj := &unstructured.Unstructured{Object: map[string]interface{}{
		"apiVersion": "agentsandbox.agentcube.volcano.sh/v1alpha1",
		"kind":       "Sandbox",
		"metadata": map[string]interface{}{
			"name":      "sbx-1",
			"namespace": "default",
			"annotations": map[string]interface{}{
				"agentcube.volcano.sh/pod-name": "pod-1",
			},
		},
	}}

	dyn := dynamicfake.NewSimpleDynamicClient(s, sbObj)
	kube := kubefake.NewSimpleClientset(&corev1.Pod{
		ObjectMeta: metav1.ObjectMeta{Name: "pod-1", Namespace: "default"},
		Status:     corev1.PodStatus{PodIP: "10.0.0.1"},
	})
	b := &workloadmanager.SandboxBuilder{Dyn: dyn, Kube: kube}
	srv := workloadmanager.NewAPIServer(workloadmanager.Config{Port: 8082}, kube, dyn, st, b, nil, nil)

	w := httptest.NewRecorder()
	req := httptest.NewRequest(http.MethodDelete, "/v1/agent-runtime/sessions/sid-1", nil)
	srv.Engine.ServeHTTP(w, req)
	assert.Equal(t, http.StatusNoContent, w.Code)
	_, err := st.GetSandboxBySessionID(context.Background(), "sid-1")
	assert.ErrorIs(t, err, store.ErrNotFound)
}
