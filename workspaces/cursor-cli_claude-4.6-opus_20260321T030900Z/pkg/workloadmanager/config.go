package workloadmanager

import (
	"time"

	"k8s.io/apimachinery/pkg/runtime/schema"
)

// Config controls the workload-manager HTTP server.
type Config struct {
	Port             int
	RuntimeClassName string
	EnableTLS        bool
	TLSCert          string
	TLSKey           string
	EnableAuth       bool
}

const (
	DefaultSandboxTTL         = 8 * time.Hour
	DefaultSandboxIdleTimeout = 15 * time.Minute
)

var (
	AgentRuntimeGVR = schema.GroupVersionResource{
		Group:    "runtime.agentcube.volcano.sh",
		Version:  "v1alpha1",
		Resource: "agentruntimes",
	}
	CodeInterpreterGVR = schema.GroupVersionResource{
		Group:    "runtime.agentcube.volcano.sh",
		Version:  "v1alpha1",
		Resource: "codeinterpreters",
	}
	SandboxGVR = schema.GroupVersionResource{
		Group:    "agentsandbox.agentcube.volcano.sh",
		Version:  "v1alpha1",
		Resource: "sandboxes",
	}
	SandboxClaimGVR = schema.GroupVersionResource{
		Group:    "agentsandbox.agentcube.volcano.sh",
		Version:  "v1alpha1",
		Resource: "sandboxclaims",
	}
	SandboxTemplateGVR = schema.GroupVersionResource{
		Group:    "agentsandbox.agentcube.volcano.sh",
		Version:  "v1alpha1",
		Resource: "sandboxtemplates",
	}
	SandboxWarmPoolGVR = schema.GroupVersionResource{
		Group:    "agentsandbox.agentcube.volcano.sh",
		Version:  "v1alpha1",
		Resource: "sandboxwarmpools",
	}
)
