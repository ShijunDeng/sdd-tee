package store_test

import (
	"context"
	"testing"
	"time"

	"github.com/alicebob/miniredis/v2"
	"github.com/redis/go-redis/v9"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"

	"github.com/volcano-sh/agentcube/pkg/store"
)

func newTestRedisStore(t *testing.T) (store.Store, func()) {
	t.Helper()
	mr := miniredis.RunT(t)
	rdb := redis.NewClient(&redis.Options{Addr: mr.Addr()})
	t.Cleanup(func() { _ = rdb.Close() })
	return store.NewRedisStoreFromClient(rdb), func() {}
}

func TestStoreSandbox(t *testing.T) {
	ctx := context.Background()
	s, _ := newTestRedisStore(t)
	now := time.Now().Unix()
	sb := &store.Sandbox{
		SessionID:    "sess-store-1",
		Namespace:    "ns1",
		ResourceName: "ar1",
		ResourceKind: "agent-runtime",
		PodIP:        "10.0.0.1",
		ExpiresAt:    now + 3600,
		CreatedAt:    now,
		LastActivity: now,
	}
	require.NoError(t, s.StoreSandbox(ctx, sb))
	got, err := s.GetSandboxBySessionID(ctx, "sess-store-1")
	require.NoError(t, err)
	assert.Equal(t, "ns1", got.Namespace)
	assert.Equal(t, "10.0.0.1", got.PodIP)
}

func TestGetSandboxBySessionID_NotFound(t *testing.T) {
	ctx := context.Background()
	s, _ := newTestRedisStore(t)
	_, err := s.GetSandboxBySessionID(ctx, "missing")
	assert.ErrorIs(t, err, store.ErrNotFound)
}

func TestDeleteSandbox(t *testing.T) {
	ctx := context.Background()
	s, _ := newTestRedisStore(t)
	now := time.Now().Unix()
	sb := &store.Sandbox{
		SessionID:    "sess-del",
		Namespace:    "ns",
		ResourceName: "r",
		ResourceKind: "agent-runtime",
		ExpiresAt:    now + 10,
		CreatedAt:    now,
		LastActivity: now,
	}
	require.NoError(t, s.StoreSandbox(ctx, sb))
	require.NoError(t, s.DeleteSandboxBySessionID(ctx, "sess-del"))
	_, err := s.GetSandboxBySessionID(ctx, "sess-del")
	assert.ErrorIs(t, err, store.ErrNotFound)
}

func TestListExpired(t *testing.T) {
	ctx := context.Background()
	s, _ := newTestRedisStore(t)
	past := time.Now().Unix() - 100
	future := time.Now().Unix() + 3600
	require.NoError(t, s.StoreSandbox(ctx, &store.Sandbox{
		SessionID: "exp-a", Namespace: "n", ResourceName: "x", ResourceKind: "agent-runtime",
		ExpiresAt: past, CreatedAt: past, LastActivity: past,
	}))
	require.NoError(t, s.StoreSandbox(ctx, &store.Sandbox{
		SessionID: "ok-b", Namespace: "n", ResourceName: "y", ResourceKind: "agent-runtime",
		ExpiresAt: future, CreatedAt: past, LastActivity: past,
	}))
	list, err := s.ListExpiredSandboxes(ctx, time.Now().Unix(), 10)
	require.NoError(t, err)
	ids := make([]string, 0, len(list))
	for _, x := range list {
		ids = append(ids, x.SessionID)
	}
	assert.Contains(t, ids, "exp-a")
	assert.NotContains(t, ids, "ok-b")
}

func TestListInactive(t *testing.T) {
	ctx := context.Background()
	s, _ := newTestRedisStore(t)
	oldAct := time.Now().Unix() - 7200
	recentAct := time.Now().Unix()
	future := time.Now().Unix() + 3600
	require.NoError(t, s.StoreSandbox(ctx, &store.Sandbox{
		SessionID: "idle-a", Namespace: "n", ResourceName: "x", ResourceKind: "agent-runtime",
		ExpiresAt: future, CreatedAt: oldAct, LastActivity: oldAct,
	}))
	require.NoError(t, s.StoreSandbox(ctx, &store.Sandbox{
		SessionID: "active-b", Namespace: "n", ResourceName: "y", ResourceKind: "agent-runtime",
		ExpiresAt: future, CreatedAt: recentAct, LastActivity: recentAct,
	}))
	cutoff := time.Now().Unix() - 3600
	list, err := s.ListInactiveSandboxes(ctx, cutoff, 10)
	require.NoError(t, err)
	ids := make([]string, 0, len(list))
	for _, x := range list {
		ids = append(ids, x.SessionID)
	}
	assert.Contains(t, ids, "idle-a")
	assert.NotContains(t, ids, "active-b")
}

func TestUpdateLastActivity(t *testing.T) {
	ctx := context.Background()
	s, _ := newTestRedisStore(t)
	now := time.Now().Unix()
	require.NoError(t, s.StoreSandbox(ctx, &store.Sandbox{
		SessionID: "sess-act", Namespace: "n", ResourceName: "z", ResourceKind: "agent-runtime",
		ExpiresAt: now + 3600, CreatedAt: now, LastActivity: now,
	}))
	newTs := now + 42
	require.NoError(t, s.UpdateSessionLastActivity(ctx, "sess-act", newTs))
	got, err := s.GetSandboxBySessionID(ctx, "sess-act")
	require.NoError(t, err)
	assert.Equal(t, newTs, got.LastActivity)
}
