package router

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"os"
	"strings"
	"time"

	"github.com/google/uuid"
	commontypes "github.com/volcano-sh/agentcube/pkg/common/types"
	"github.com/volcano-sh/agentcube/pkg/store"
	"k8s.io/klog/v2"
)

const headerSessionID = "X-Agentcube-Session-Id"

// SessionManager resolves sessions against the store and materializes sandboxes via workload-manager.
type SessionManager struct {
	Store      store.Store
	HTTPClient *http.Client
	wmBase     string
}

// NewSessionManager builds a manager using WORKLOAD_MANAGER_URL.
func NewSessionManager(st store.Store) *SessionManager {
	base := strings.TrimSuffix(strings.TrimSpace(os.Getenv("WORKLOAD_MANAGER_URL")), "/")
	if base == "" {
		base = "http://127.0.0.1:8081"
	}
	return &SessionManager{
		Store:      st,
		wmBase:     base,
		HTTPClient: &http.Client{Timeout: 120 * time.Second},
	}
}

// GetSandboxBySession returns an existing sandbox or asks workload-manager to create one.
func (m *SessionManager) GetSandboxBySession(ctx context.Context, namespace, resourceName, kind, sessionID string) (*store.Sandbox, string, error) {
	if m.Store == nil {
		return nil, "", errors.New("store is nil")
	}
	sid := strings.TrimSpace(sessionID)
	if sid == "" {
		sid = uuid.NewString()
	}
	sb, err := m.Store.GetSandboxBySessionID(ctx, sid)
	if err == nil {
		return sb, sid, nil
	}
	if !errors.Is(err, store.ErrNotFound) {
		return nil, sid, err
	}

	reqBody := commontypes.CreateSandboxRequest{
		Name:      resourceName,
		Namespace: namespace,
		Kind:      kind,
		Metadata:  map[string]string{"sessionID": sid},
	}
	if err := reqBody.Validate(); err != nil {
		return nil, sid, err
	}

	path := "/v1/agent-runtime"
	if kind == commontypes.CodeInterpreterKind {
		path = "/v1/code-interpreter"
	}
	buf, err := json.Marshal(reqBody)
	if err != nil {
		return nil, sid, err
	}
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, m.wmBase+path, bytes.NewReader(buf))
	if err != nil {
		return nil, sid, err
	}
	req.Header.Set("Content-Type", "application/json")
	resp, err := m.HTTPClient.Do(req)
	if err != nil {
		return nil, sid, fmt.Errorf("workload manager: %w", err)
	}
	defer resp.Body.Close()
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		return nil, sid, fmt.Errorf("workload manager: status %d", resp.StatusCode)
	}
	var csr commontypes.CreateSandboxResponse
	if err := json.NewDecoder(resp.Body).Decode(&csr); err != nil {
		return nil, sid, fmt.Errorf("decode create response: %w", err)
	}
	now := time.Now().Unix()
	port := defaultPort(csr.EntryPoints)
	rk := kind
	switch kind {
	case commontypes.AgentRuntimeKind:
		rk = "agent-runtime"
	case commontypes.CodeInterpreterKind:
		rk = "code-interpreter"
	}
	nsOut := csr.Namespace
	if nsOut == "" {
		nsOut = namespace
	}
	nameOut := csr.Name
	if nameOut == "" {
		nameOut = resourceName
	}
	rec := &store.Sandbox{
		SessionID:     sid,
		Namespace:     nsOut,
		ResourceName:  nameOut,
		ResourceKind:  rk,
		SandboxCRName: csr.SandboxName,
		PodIP:         csr.PodIP,
		UpstreamPort:  int(port),
		CreatedAt:     now,
		LastActivity:  now,
		ExpiresAt:     now + int64(8*time.Hour/time.Second),
	}
	if err := m.Store.StoreSandbox(ctx, rec); err != nil {
		return nil, sid, err
	}
	klog.InfoS("session materialized", "sessionID", sid, "namespace", namespace, "resource", resourceName)
	return rec, sid, nil
}

func defaultPort(eps []commontypes.SandboxEntryPoint) uint32 {
	if len(eps) == 0 {
		return 8080
	}
	if eps[0].Port == 0 {
		return 8080
	}
	return eps[0].Port
}

// DeleteSession removes routing state; workload-manager owns sandbox teardown.
func (m *SessionManager) DeleteSession(ctx context.Context, kind, sessionID string) error {
	if m.Store == nil {
		return errors.New("store is nil")
	}
	path := "/v1/agent-runtime/sessions/" + sessionID
	if kind == commontypes.CodeInterpreterKind {
		path = "/v1/code-interpreter/sessions/" + sessionID
	}
	req, err := http.NewRequestWithContext(ctx, http.MethodDelete, m.wmBase+path, nil)
	if err != nil {
		return err
	}
	resp, err := m.HTTPClient.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	_ = m.Store.DeleteSandboxBySessionID(ctx, sessionID)
	if resp.StatusCode >= 300 {
		return fmt.Errorf("workload manager delete: status %d", resp.StatusCode)
	}
	return nil
}

// SessionHeader is the canonical header name for sticky sessions.
func SessionHeader() string { return headerSessionID }
