/*
Copyright The Volcano Authors.

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
*/

package store

import (
	"context"
	"time"

	"github.com/volcano-sh/agentcube/pkg/common/types"
)

type MemoryStore struct {
	sandboxes map[string]*types.SandboxInfo
}

func NewMemoryStore() *MemoryStore {
	return &MemoryStore{
		sandboxes: make(map[string]*types.SandboxInfo),
	}
}

func (m *MemoryStore) Ping(_ context.Context) error {
	return nil
}

func (m *MemoryStore) GetSandboxBySessionID(_ context.Context, sessionID string) (*types.SandboxInfo, error) {
	info, ok := m.sandboxes[sessionID]
	if !ok {
		return nil, ErrNotFound
	}
	return info, nil
}

func (m *MemoryStore) StoreSandbox(_ context.Context, info *types.SandboxInfo) error {
	m.sandboxes[info.SessionID] = info
	return nil
}

func (m *MemoryStore) UpdateSandbox(_ context.Context, info *types.SandboxInfo) error {
	m.sandboxes[info.SessionID] = info
	return nil
}

func (m *MemoryStore) DeleteSandboxBySessionID(_ context.Context, sessionID string) error {
	delete(m.sandboxes, sessionID)
	return nil
}

func (m *MemoryStore) ListExpiredSandboxes(_ context.Context, now time.Time, _ int64) ([]*types.SandboxInfo, error) {
	var expired []*types.SandboxInfo
	for _, info := range m.sandboxes {
		if info.ExpiresAt.Before(now) {
			expired = append(expired, info)
		}
	}
	return expired, nil
}

func (m *MemoryStore) ListInactiveSandboxes(_ context.Context, inactiveSince time.Time, _ int64) ([]*types.SandboxInfo, error) {
	var inactive []*types.SandboxInfo
	for _, info := range m.sandboxes {
		if info.LastActivityAt.Before(inactiveSince) {
			inactive = append(inactive, info)
		}
	}
	return inactive, nil
}

func (m *MemoryStore) UpdateSessionLastActivity(_ context.Context, sessionID string, lastActivity time.Time) error {
	if info, ok := m.sandboxes[sessionID]; ok {
		info.LastActivityAt = lastActivity
		m.sandboxes[sessionID] = info
	}
	return nil
}

func (m *MemoryStore) Close() error {
	return nil
}
