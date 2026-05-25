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
	"errors"
	"time"

	"github.com/volcano-sh/agentcube/pkg/common/types"
)

var (
	ErrNotFound = errors.New("not found")
)

type Store interface {
	Ping(ctx context.Context) error
	GetSandboxBySessionID(ctx context.Context, sessionID string) (*types.SandboxInfo, error)
	StoreSandbox(ctx context.Context, info *types.SandboxInfo) error
	UpdateSandbox(ctx context.Context, info *types.SandboxInfo) error
	DeleteSandboxBySessionID(ctx context.Context, sessionID string) error
	ListExpiredSandboxes(ctx context.Context, now time.Time, limit int64) ([]*types.SandboxInfo, error)
	ListInactiveSandboxes(ctx context.Context, inactiveSince time.Time, limit int64) ([]*types.SandboxInfo, error)
	UpdateSessionLastActivity(ctx context.Context, sessionID string, lastActivity time.Time) error
	Close() error
}
