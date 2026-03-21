package workloadmanager

import (
	"context"
	"sync"
	"testing"
	"time"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
	corev1 "k8s.io/api/core/v1"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/apis/meta/v1/unstructured"
	"k8s.io/apimachinery/pkg/runtime"
	dynamicfake "k8s.io/client-go/dynamic/fake"
	kubefake "k8s.io/client-go/kubernetes/fake"

	sandboxv1 "github.com/volcano-sh/agentcube/pkg/apis/agentsandbox/v1alpha1"
	"github.com/volcano-sh/agentcube/pkg/store"
)

type gcMemStore struct {
	mu   sync.Mutex
	m    map[string]*store.Sandbox
	dead []string
}

func newGCMemStore() *gcMemStore {
	return &gcMemStore{m: map[string]*store.Sandbox{}}
}

func (g *gcMemStore) Ping(ctx context.Context) error { return nil }

func (g *gcMemStore) GetSandboxBySessionID(ctx context.Context, sessionID string) (*store.Sandbox, error) {
	g.mu.Lock()
	defer g.mu.Unlock()
	sb, ok := g.m[sessionID]
	if !ok {
		return nil, store.ErrNotFound
	}
	cp := *sb
	return &cp, nil
}

func (g *gcMemStore) StoreSandbox(ctx context.Context, sb *store.Sandbox) error {
	g.mu.Lock()
	defer g.mu.Unlock()
	g.m[sb.SessionID] = sb
	return nil
}

func (g *gcMemStore) UpdateSandbox(ctx context.Context, sb *store.Sandbox) error {
	g.mu.Lock()
	defer g.mu.Unlock()
	g.m[sb.SessionID] = sb
	return nil
}

func (g *gcMemStore) DeleteSandboxBySessionID(ctx context.Context, sessionID string) error {
	g.mu.Lock()
	defer g.mu.Unlock()
	delete(g.m, sessionID)
	g.dead = append(g.dead, sessionID)
	return nil
}

func (g *gcMemStore) ListExpiredSandboxes(ctx context.Context, beforeUnix int64, limit int) ([]*store.Sandbox, error) {
	g.mu.Lock()
	defer g.mu.Unlock()
	var out []*store.Sandbox
	for _, sb := range g.m {
		if sb != nil && sb.ExpiresAt <= beforeUnix {
			cp := *sb
			out = append(out, &cp)
			if len(out) >= limit {
				break
			}
		}
	}
	return out, nil
}

func (g *gcMemStore) ListInactiveSandboxes(ctx context.Context, lastActivityBeforeUnix int64, limit int) ([]*store.Sandbox, error) {
	return nil, nil
}

func (g *gcMemStore) UpdateSessionLastActivity(ctx context.Context, sessionID string, ts int64) error { return nil }
func (g *gcMemStore) Close() error                                                                     { return nil }

func schemeForGC(t *testing.T) *runtime.Scheme {
	t.Helper()
	s := runtime.NewScheme()
	require.NoError(t, corev1.AddToScheme(s))
	require.NoError(t, sandboxv1.AddToScheme(s))
	return s
}

func TestRunGarbageCollectionPass_OrphanSessionRow(t *testing.T) {
	s := schemeForGC(t)
	st := newGCMemStore()
	past := time.Now().Unix() - 10
	require.NoError(t, st.StoreSandbox(context.Background(), &store.Sandbox{
		SessionID: "orphan", ExpiresAt: past,
		// no namespace / CR name → GC should delete store row only
	}))

	kube := kubefake.NewSimpleClientset()
	dyn := dynamicfake.NewSimpleDynamicClient(s)
	runGarbageCollectionPass(context.Background(), kube, dyn, st)
	assert.Contains(t, st.dead, "orphan")
}

func TestStartGarbageCollection_DisabledWithoutDeps(t *testing.T) {
	ctx, cancel := context.WithCancel(context.Background())
	t.Cleanup(cancel)
	StartGarbageCollection(ctx, nil, nil, nil)
	cancel()
	// exits quickly when ctx done; no panic when dependencies are nil
}

func TestRunGarbageCollectionPass_DeletesKubeSandbox(t *testing.T) {
	s := schemeForGC(t)
	st := newGCMemStore()
	past := time.Now().Unix() - 10
	require.NoError(t, st.StoreSandbox(context.Background(), &store.Sandbox{
		SessionID:     "live",
		Namespace:     "default",
		SandboxCRName: "sbx-99",
		ExpiresAt:     past,
	}))

	sbObj := &unstructured.Unstructured{Object: map[string]interface{}{
		"apiVersion": "agentsandbox.agentcube.volcano.sh/v1alpha1",
		"kind":       "Sandbox",
		"metadata": map[string]interface{}{
			"name":      "sbx-99",
			"namespace": "default",
			"annotations": map[string]interface{}{
				"agentcube.volcano.sh/pod-name": "p-99",
			},
		},
	}}
	dyn := dynamicfake.NewSimpleDynamicClient(s, sbObj)
	kube := kubefake.NewSimpleClientset(&corev1.Pod{
		ObjectMeta: metav1.ObjectMeta{Name: "p-99", Namespace: "default"},
	})

	runGarbageCollectionPass(context.Background(), kube, dyn, st)
	assert.Contains(t, st.dead, "live")
}
