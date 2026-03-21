package router

import (
	"context"
	"sync"

	"github.com/volcano-sh/agentcube/pkg/store"
)

type stubStore struct {
	mu   sync.Mutex
	data map[string]*store.Sandbox
}

func newStubStore() *stubStore {
	return &stubStore{data: map[string]*store.Sandbox{}}
}

func (s *stubStore) Ping(ctx context.Context) error { return nil }

func (s *stubStore) GetSandboxBySessionID(ctx context.Context, sessionID string) (*store.Sandbox, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	sb, ok := s.data[sessionID]
	if !ok {
		return nil, store.ErrNotFound
	}
	cp := *sb
	return &cp, nil
}

func (s *stubStore) StoreSandbox(ctx context.Context, sb *store.Sandbox) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.data[sb.SessionID] = sb
	return nil
}

func (s *stubStore) UpdateSandbox(ctx context.Context, sb *store.Sandbox) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.data[sb.SessionID] = sb
	return nil
}

func (s *stubStore) DeleteSandboxBySessionID(ctx context.Context, sessionID string) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	delete(s.data, sessionID)
	return nil
}

func (s *stubStore) ListExpiredSandboxes(ctx context.Context, beforeUnix int64, limit int) ([]*store.Sandbox, error) {
	return nil, nil
}

func (s *stubStore) ListInactiveSandboxes(ctx context.Context, lastActivityBeforeUnix int64, limit int) ([]*store.Sandbox, error) {
	return nil, nil
}

func (s *stubStore) UpdateSessionLastActivity(ctx context.Context, sessionID string, ts int64) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	if sb, ok := s.data[sessionID]; ok {
		sb.LastActivity = ts
	}
	return nil
}

func (s *stubStore) Close() error { return nil }
