package router

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"

	commontypes "github.com/volcano-sh/agentcube/pkg/common/types"
	"github.com/volcano-sh/agentcube/pkg/store"
)

func TestSessionManager_GetSandboxFromStore(t *testing.T) {
	st := newStubStore()
	t.Setenv("WORKLOAD_MANAGER_URL", "http://127.0.0.1:9")
	sm := NewSessionManager(st)

	ctx := context.Background()
	rec := &store.Sandbox{
		SessionID:    "sess-hit",
		Namespace:    "ns",
		ResourceName: "ar1",
		ResourceKind: "agent-runtime",
		PodIP:        "10.1.1.1",
		ExpiresAt:    time.Now().Unix() + 3600,
		CreatedAt:    time.Now().Unix(),
		LastActivity: time.Now().Unix(),
	}
	require.NoError(t, st.StoreSandbox(ctx, rec))

	out, sid, err := sm.GetSandboxBySession(ctx, "ns", "ar1", commontypes.AgentRuntimeKind, rec.SessionID)
	require.NoError(t, err)
	assert.Equal(t, rec.SessionID, sid)
	assert.Equal(t, rec.PodIP, out.PodIP)
}

func TestSessionManager_MaterializeFromWorkloadManager(t *testing.T) {
	wm := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost || r.URL.Path != "/v1/agent-runtime" {
			http.NotFound(w, r)
			return
		}
		_ = json.NewEncoder(w).Encode(commontypes.CreateSandboxResponse{
			SessionID:   "will-be-overwritten",
			Name:        "ar1",
			Namespace:   "ns",
			SandboxName: "sbx-1",
			PodIP:       "10.2.2.2",
			EntryPoints: []commontypes.SandboxEntryPoint{{Port: 9090, Name: "http"}},
		})
	}))
	t.Cleanup(wm.Close)

	st := newStubStore()
	t.Setenv("WORKLOAD_MANAGER_URL", wm.URL)
	sm := NewSessionManager(st)

	ctx := context.Background()
	out, sid, err := sm.GetSandboxBySession(ctx, "ns", "ar1", commontypes.AgentRuntimeKind, "")
	require.NoError(t, err)
	assert.NotEmpty(t, sid)
	assert.Equal(t, "10.2.2.2", out.PodIP)
	assert.Equal(t, 9090, out.UpstreamPort)

	got, err := st.GetSandboxBySessionID(ctx, sid)
	require.NoError(t, err)
	assert.Equal(t, sid, got.SessionID)
}

func TestSessionManager_NilStore(t *testing.T) {
	t.Setenv("WORKLOAD_MANAGER_URL", "http://127.0.0.1:9")
	sm := NewSessionManager(nil)
	_, _, err := sm.GetSandboxBySession(context.Background(), "ns", "x", commontypes.AgentRuntimeKind, "sid")
	require.Error(t, err)
	assert.Contains(t, err.Error(), "store is nil")
}
