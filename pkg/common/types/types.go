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

package types

import (
	"time"

	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
)

const (
	AgentRuntimeKind     = "AgentRuntime"
	CodeInterpreterKind  = "CodeInterpreter"
	SandboxClaimsKind    = "SandboxClaims"
	SessionLabelKey      = "session-id"
	SandboxLabelKey      = "sandbox-id"
	SandboxNameLabelKey  = "sandbox-name"
	SandboxKindLabelKey  = "sandbox-kind"
	TemplateLabelKey     = "template-name"
	TemplateKindLabelKey = "template-kind"
)

type SandboxInfo struct {
	SessionID         string              `json:"sessionId"`
	SandboxID         string              `json:"sandboxId"`
	Name              string              `json:"name"`
	SandboxNamespace  string              `json:"sandboxNamespace"`
	Kind              string              `json:"kind"`
	TemplateName      string              `json:"templateName"`
	TemplateNamespace string              `json:"templateNamespace"`
	TemplateKind      string              `json:"templateKind"`
	Labels            map[string]string   `json:"labels,omitempty"`
	Annotations       map[string]string   `json:"annotations,omitempty"`
	EntryPoints       []SandboxEntryPoint `json:"entryPoints"`
	CreatedAt         time.Time           `json:"createdAt"`
	ExpiresAt         time.Time           `json:"expiresAt"`
	LastActivityAt    time.Time           `json:"lastActivityAt"`
}

type SandboxEntryPoint struct {
	Path     string `json:"path"`
	Protocol string `json:"protocol"`
	Endpoint string `json:"endpoint"`
}

type CreateSandboxRequest struct {
	Name      string `json:"name"`
	Namespace string `json:"namespace"`
}

type CreateSandboxResponse struct {
	SessionID   string              `json:"sessionId"`
	SandboxID   string              `json:"sandboxId"`
	SandboxName string              `json:"sandboxName"`
	EntryPoints []SandboxEntryPoint `json:"entryPoints"`
}

type SandboxStatusUpdate struct {
	SandboxName      string             `json:"sandboxName"`
	SandboxNamespace string             `json:"sandboxNamespace"`
	Phase            SandboxPhase       `json:"phase"`
	Conditions       []metav1.Condition `json:"conditions"`
	PodIP            string             `json:"podIP,omitempty"`
}

type SandboxPhase string

const (
	SandboxPhasePending   SandboxPhase = "Pending"
	SandboxPhaseRunning   SandboxPhase = "Running"
	SandboxPhaseSucceeded SandboxPhase = "Succeeded"
	SandboxPhaseFailed    SandboxPhase = "Failed"
	SandboxPhaseUnknown   SandboxPhase = "Unknown"
)
