package store

import (
	"context"
	"errors"
	"os"
	"strings"
	"sync"

	_ "github.com/valkey-io/valkey-go"
	"k8s.io/klog/v2"
)

// ErrNotFound is returned when a session or sandbox record does not exist.
var ErrNotFound = errors.New("not found")

// Sandbox is the persisted session/sandbox metadata stored in the backing store.
type Sandbox struct {
	SessionID       string `json:"session_id"`
	Namespace       string `json:"namespace"`
	ResourceName    string `json:"resource_name"`
	ResourceKind    string `json:"resource_kind"` // "agent-runtime" | "code-interpreter"
	SandboxCRName   string `json:"sandbox_cr_name,omitempty"`
	PodIP           string `json:"pod_ip"`
	UpstreamPort    int    `json:"upstream_port,omitempty"`
	UpstreamBaseURL string `json:"upstream_base_url,omitempty"`
	ExpiresAt       int64  `json:"expires_at"`
	CreatedAt       int64  `json:"created_at"`
	LastActivity    int64  `json:"last_activity"`
}

// Store abstracts session persistence for router and workload manager.
type Store interface {
	Ping(ctx context.Context) error
	GetSandboxBySessionID(ctx context.Context, sessionID string) (*Sandbox, error)
	StoreSandbox(ctx context.Context, sb *Sandbox) error
	UpdateSandbox(ctx context.Context, sb *Sandbox) error
	DeleteSandboxBySessionID(ctx context.Context, sessionID string) error
	ListExpiredSandboxes(ctx context.Context, beforeUnix int64, limit int) ([]*Sandbox, error)
	ListInactiveSandboxes(ctx context.Context, lastActivityBeforeUnix int64, limit int) ([]*Sandbox, error)
	UpdateSessionLastActivity(ctx context.Context, sessionID string, ts int64) error
	Close() error
}

var (
	storageOnce sync.Once
	storageInst Store
	storageErr  error
)

// Storage returns a process-wide Store implementation based on STORE_TYPE
// ("redis", "valkey"; default "redis"). The first successful call initializes
// the singleton; subsequent calls return the same instance or initialization error.
func Storage() (Store, error) {
	storageOnce.Do(func() {
		t := strings.ToLower(strings.TrimSpace(os.Getenv("STORE_TYPE")))
		if t == "" {
			t = "redis"
		}
		switch t {
		case "redis":
			storageInst, storageErr = newRedisStoreFromEnv()
		case "valkey":
			storageInst, storageErr = newValkeyStoreFromEnv()
		default:
			storageErr = errors.New("unsupported STORE_TYPE: " + t)
			klog.ErrorS(storageErr, "invalid STORE_TYPE")
		}
	})
	return storageInst, storageErr
}
