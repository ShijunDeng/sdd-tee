// Copyright 2026 The Volcano Authors.
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0

package v1alpha1

import (
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
)

const (
	SandboxKind       = "Sandbox"
	SandboxClaimsKind = "SandboxClaims"
)

// +kubebuilder:object:root=true
// +kubebuilder:subresource:status
// +kubebuilder:resource:path=sandboxes,scope=Namespaced,shortName=sbx
// Sandbox represents a running agent sandbox workload.
type Sandbox struct {
	metav1.TypeMeta   `json:",inline"`
	metav1.ObjectMeta `json:"metadata,omitempty"`

	Spec   SandboxSpec   `json:"spec,omitempty"`
	Status SandboxStatus `json:"status,omitempty"`
}

// +kubebuilder:object:root=true
// SandboxList contains a list of Sandbox.
type SandboxList struct {
	metav1.TypeMeta `json:",inline"`
	metav1.ListMeta `json:"metadata,omitempty"`
	Items           []Sandbox `json:"items"`
}

// SandboxSpec defines the desired state of Sandbox.
type SandboxSpec struct {
	// runtimeClassName is the RuntimeClass for the sandbox pod.
	// +optional
	RuntimeClassName *string `json:"runtimeClassName,omitempty"`
}

// SandboxStatus defines the observed state of Sandbox.
type SandboxStatus struct {
	// phase is a high-level lifecycle phase of the sandbox.
	// +optional
	Phase string `json:"phase,omitempty"`
}

// +kubebuilder:object:root=true
// +kubebuilder:resource:path=sandboxclaims,scope=Namespaced
// SandboxClaims binds identity and quota to sandbox sessions.
type SandboxClaims struct {
	metav1.TypeMeta   `json:",inline"`
	metav1.ObjectMeta `json:"metadata,omitempty"`

	Spec SandboxClaimsSpec `json:"spec,omitempty"`
}

// +kubebuilder:object:root=true
// SandboxClaimsList contains a list of SandboxClaims.
type SandboxClaimsList struct {
	metav1.TypeMeta `json:",inline"`
	metav1.ListMeta `json:"metadata,omitempty"`
	Items           []SandboxClaims `json:"items"`
}

// SandboxClaimsSpec defines the desired state of SandboxClaims.
type SandboxClaimsSpec struct {
	// sessionID references the logical session owning these claims.
	// +optional
	SessionID string `json:"sessionID,omitempty"`
}
