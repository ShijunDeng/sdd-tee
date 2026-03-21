// Copyright 2026 The Volcano Authors.
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0

package v1alpha1

import (
	corev1 "k8s.io/api/core/v1"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/runtime/schema"
)

const (
	AuthModePicoD = "picod"
	AuthModeNone  = "none"

	ProtocolTypeHTTP  = "HTTP"
	ProtocolTypeHTTPS = "HTTPS"
)

// AuthModeType defines how the code interpreter authenticates sessions.
// +kubebuilder:validation:Enum=picod;none
type AuthModeType string

// ProtocolType defines the protocol exposed by a target port.
// +kubebuilder:validation:Enum=HTTP;HTTPS
type ProtocolType string

var (
	AgentRuntimeKind        = "AgentRuntime"
	AgentRuntimeListKind    = "AgentRuntimeList"
	CodeInterpreterKind     = "CodeInterpreter"
	CodeInterpreterListKind = "CodeInterpreterList"
)

// ResourceForKind returns the canonical plural resource name for well-known kinds.
func ResourceForKind(kind string) schema.GroupResource {
	switch kind {
	case AgentRuntimeKind:
		return Resource("agentruntimes")
	case CodeInterpreterKind:
		return Resource("codeinterpreters")
	case AgentRuntimeListKind:
		return Resource("agentruntimes")
	case CodeInterpreterListKind:
		return Resource("codeinterpreters")
	default:
		return Resource("")
	}
}

// +kubebuilder:object:root=true
// +kubebuilder:subresource:status
// +kubebuilder:resource:path=agentruntimes,scope=Namespaced,shortName=ar
// +kubebuilder:printcolumn:name="Age",type="date",JSONPath=".metadata.creationTimestamp"
// AgentRuntime defines a reusable runtime template for agent sandboxes.
type AgentRuntime struct {
	metav1.TypeMeta   `json:",inline"`
	metav1.ObjectMeta `json:"metadata,omitempty"`

	Spec   AgentRuntimeSpec   `json:"spec,omitempty"`
	Status AgentRuntimeStatus `json:"status,omitempty"`
}

// +kubebuilder:object:root=true
// AgentRuntimeList contains a list of AgentRuntime.
type AgentRuntimeList struct {
	metav1.TypeMeta `json:",inline"`
	metav1.ListMeta `json:"metadata,omitempty"`
	Items           []AgentRuntime `json:"items"`
}

// AgentRuntimeSpec defines the desired state of AgentRuntime.
type AgentRuntimeSpec struct {
	// targetPorts declares ingress paths and service ports exposed by the runtime.
	// +kubebuilder:validation:MinItems=1
	TargetPorts []TargetPort `json:"targetPorts,omitempty"`

	// podTemplate describes the pod specification used for sandbox instances.
	PodTemplate *SandboxTemplate `json:"podTemplate,omitempty"`

	// sessionTimeout is the idle timeout before a session is reclaimed.
	// +kubebuilder:default="15m"
	// +optional
	SessionTimeout *metav1.Duration `json:"sessionTimeout,omitempty"`

	// maxSessionDuration is the hard cap on session lifetime.
	// +kubebuilder:default="8h"
	// +optional
	MaxSessionDuration *metav1.Duration `json:"maxSessionDuration,omitempty"`
}

// AgentRuntimeStatus defines the observed state of AgentRuntime.
type AgentRuntimeStatus struct {
	// conditions represent the latest available observations of the runtime's state.
	// +optional
	// +patchMergeKey=type
	// +patchStrategy=merge
	// +listType=map
	// +listMapKey=type
	Conditions []metav1.Condition `json:"conditions,omitempty"`
}

// +kubebuilder:object:root=true
// +kubebuilder:subresource:status
// +kubebuilder:resource:path=codeinterpreters,scope=Namespaced,shortName=ci
// +kubebuilder:printcolumn:name="Ready",type="boolean",JSONPath=".status.ready"
// +kubebuilder:printcolumn:name="Age",type="date",JSONPath=".metadata.creationTimestamp"
// CodeInterpreter defines a managed code interpreter sandbox pool.
type CodeInterpreter struct {
	metav1.TypeMeta   `json:",inline"`
	metav1.ObjectMeta `json:"metadata,omitempty"`

	Spec   CodeInterpreterSpec   `json:"spec,omitempty"`
	Status CodeInterpreterStatus `json:"status,omitempty"`
}

// +kubebuilder:object:root=true
// CodeInterpreterList contains a list of CodeInterpreter.
type CodeInterpreterList struct {
	metav1.TypeMeta `json:",inline"`
	metav1.ListMeta `json:"metadata,omitempty"`
	Items           []CodeInterpreter `json:"items"`
}

// CodeInterpreterSpec defines the desired state of CodeInterpreter.
type CodeInterpreterSpec struct {
	// ports declares ingress paths and container ports for the interpreter HTTP(S) endpoints.
	// +kubebuilder:validation:MinItems=1
	Ports []TargetPort `json:"ports,omitempty"`

	// template is the pod template fragment used to materialize interpreter sandboxes.
	// +kubebuilder:validation:Required
	Template *CodeInterpreterSandboxTemplate `json:"template"`

	// sessionTimeout is the idle timeout before a session is reclaimed.
	// +kubebuilder:default="15m"
	// +optional
	SessionTimeout *metav1.Duration `json:"sessionTimeout,omitempty"`

	// maxSessionDuration is the hard cap on session lifetime.
	// +kubebuilder:default="8h"
	// +optional
	MaxSessionDuration *metav1.Duration `json:"maxSessionDuration,omitempty"`

	// warmPoolSize controls how many idle sandboxes are kept ready.
	// +optional
	WarmPoolSize *int32 `json:"warmPoolSize,omitempty"`

	// authMode selects the authentication mechanism for interpreter sessions.
	// +kubebuilder:default=picod
	// +optional
	AuthMode AuthModeType `json:"authMode,omitempty"`
}

// CodeInterpreterSandboxTemplate describes the pod shape for a code interpreter sandbox.
type CodeInterpreterSandboxTemplate struct {
	// labels are merged into the sandbox pod labels.
	// +optional
	Labels map[string]string `json:"labels,omitempty"`

	// annotations are merged into the sandbox pod annotations.
	// +optional
	Annotations map[string]string `json:"annotations,omitempty"`

	// runtimeClassName is the RuntimeClass for the sandbox pod.
	// +optional
	RuntimeClassName *string `json:"runtimeClassName,omitempty"`

	// image is the container image for the interpreter.
	// +kubebuilder:validation:Required
	Image string `json:"image"`

	// imagePullPolicy determines when kubelet pulls the image.
	// +optional
	ImagePullPolicy corev1.PullPolicy `json:"imagePullPolicy,omitempty"`

	// imagePullSecrets are references to secrets for pulling private images.
	// +optional
	ImagePullSecrets []corev1.LocalObjectReference `json:"imagePullSecrets,omitempty"`

	// environment variables injected into the interpreter container.
	// +optional
	Environment []corev1.EnvVar `json:"environment,omitempty"`

	// command overrides the container entrypoint.
	// +optional
	Command []string `json:"command,omitempty"`

	// args overrides the container arguments.
	// +optional
	Args []string `json:"args,omitempty"`

	// resources requests and limits for the interpreter container.
	// +optional
	Resources corev1.ResourceRequirements `json:"resources,omitempty"`
}

// CodeInterpreterStatus defines the observed state of CodeInterpreter.
type CodeInterpreterStatus struct {
	// conditions represent the latest available observations of the interpreter's state.
	// +optional
	// +patchMergeKey=type
	// +patchStrategy=merge
	// +listType=map
	// +listMapKey=type
	Conditions []metav1.Condition `json:"conditions,omitempty"`

	// ready indicates whether the controller considers the interpreter pool operational.
	// +optional
	Ready bool `json:"ready,omitempty"`
}

// TargetPort describes an HTTP(S) entrypoint exposed by a sandbox.
type TargetPort struct {
	// pathPrefix is the URL path prefix routed to this port.
	// +kubebuilder:validation:Required
	PathPrefix string `json:"pathPrefix"`

	// name is a stable identifier for this port (used in status and routing).
	// +kubebuilder:validation:Required
	Name string `json:"name"`

	// port is the container/listener port number.
	// +kubebuilder:validation:Minimum=1
	// +kubebuilder:validation:Maximum=65535
	Port uint32 `json:"port"`

	// protocol is HTTP or HTTPS.
	// +kubebuilder:validation:Enum=HTTP;HTTPS
	// +kubebuilder:default=HTTP
	Protocol ProtocolType `json:"protocol,omitempty"`
}

// SandboxTemplate embeds a full PodSpec for maximum flexibility.
type SandboxTemplate struct {
	// labels are merged into the sandbox pod labels.
	// +optional
	Labels map[string]string `json:"labels,omitempty"`

	// annotations are merged into the sandbox pod annotations.
	// +optional
	Annotations map[string]string `json:"annotations,omitempty"`

	// spec is the pod specification for sandbox instances.
	// +kubebuilder:validation:Required
	Spec corev1.PodSpec `json:"spec"`
}
