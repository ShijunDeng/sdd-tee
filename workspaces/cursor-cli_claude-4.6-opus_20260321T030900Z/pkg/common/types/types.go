package types

import (
	"errors"
	"fmt"
	"strings"
	"time"
)

const (
	AgentRuntimeKind    = "AgentRuntime"
	CodeInterpreterKind = "CodeInterpreter"
	SandboxKind         = "Sandbox"
	SandboxClaimsKind   = "SandboxClaims"
)

// SandboxInfo describes a materialized sandbox instance for routing and lifecycle.
type SandboxInfo struct {
	SessionID    string              `json:"sessionID"`
	Name         string              `json:"name"`
	Namespace    string              `json:"namespace"`
	Kind         string              `json:"kind"`
	PodIP        string              `json:"podIP,omitempty"`
	EntryPoints  []SandboxEntryPoint `json:"entryPoints,omitempty"`
	CreatedAt    time.Time           `json:"createdAt"`
	ExpiresAt    time.Time           `json:"expiresAt"`
	LastActivity time.Time           `json:"lastActivity"`
}

// SandboxEntryPoint is a single HTTP(S) ingress target for a sandbox.
type SandboxEntryPoint struct {
	PathPrefix string `json:"pathPrefix"`
	Name       string `json:"name"`
	Port       uint32 `json:"port"`
	Protocol   string `json:"protocol"`
	URL        string `json:"url,omitempty"`
}

// CreateSandboxRequest is the control-plane request to create a sandbox session.
type CreateSandboxRequest struct {
	Name      string            `json:"name"`
	Namespace string            `json:"namespace"`
	Kind      string            `json:"kind"`
	Metadata  map[string]string `json:"metadata,omitempty"`
}

// CreateSandboxResponse is returned after a sandbox is scheduled.
type CreateSandboxResponse struct {
	SessionID   string              `json:"sessionID"`
	Name        string              `json:"name"`
	Namespace   string              `json:"namespace"`
	SandboxName string              `json:"sandboxName,omitempty"`
	PodIP       string              `json:"podIP,omitempty"`
	EntryPoints []SandboxEntryPoint `json:"entryPoints,omitempty"`
}

// Validate checks required fields on CreateSandboxRequest.
func (r *CreateSandboxRequest) Validate() error {
	if r == nil {
		return errors.New("request is nil")
	}
	if strings.TrimSpace(r.Name) == "" {
		return fmt.Errorf("name is required")
	}
	if strings.TrimSpace(r.Namespace) == "" {
		return fmt.Errorf("namespace is required")
	}
	if strings.TrimSpace(r.Kind) == "" {
		return fmt.Errorf("kind is required")
	}
	return nil
}
