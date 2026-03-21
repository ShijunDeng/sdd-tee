package v1alpha1_test

import (
	"testing"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"

	runtimev1 "github.com/volcano-sh/agentcube/pkg/apis/runtime/v1alpha1"
)

func TestAgentRuntimeDeepCopy(t *testing.T) {
	src := &runtimev1.AgentRuntime{
		ObjectMeta: metav1.ObjectMeta{Name: "ar", Namespace: "ns", Labels: map[string]string{"k": "v"}},
		Spec: runtimev1.AgentRuntimeSpec{
			TargetPorts: []runtimev1.TargetPort{{PathPrefix: "/", Name: "h", Port: 8080}},
		},
	}
	cp := src.DeepCopy()
	require.NotNil(t, cp)
	cp.Spec.TargetPorts[0].Port = 9090
	assert.Equal(t, uint32(8080), src.Spec.TargetPorts[0].Port)
	cp.ObjectMeta.Labels["k"] = "changed"
	assert.Equal(t, "v", src.ObjectMeta.Labels["k"])
}

func TestCodeInterpreterDeepCopy(t *testing.T) {
	src := &runtimev1.CodeInterpreter{
		ObjectMeta: metav1.ObjectMeta{Name: "ci"},
		Spec: runtimev1.CodeInterpreterSpec{
			Template: &runtimev1.CodeInterpreterSandboxTemplate{Image: "img:v1"},
		},
	}
	cp := src.DeepCopy()
	require.NotNil(t, cp)
	cp.Spec.Template.Image = "img:v2"
	assert.Equal(t, "img:v1", src.Spec.Template.Image)
}

func TestResourceForKind(t *testing.T) {
	tests := []struct {
		kind string
		res  string
	}{
		{runtimev1.AgentRuntimeKind, "agentruntimes"},
		{runtimev1.CodeInterpreterKind, "codeinterpreters"},
		{runtimev1.AgentRuntimeListKind, "agentruntimes"},
		{"UnknownKind", ""},
	}
	for _, tt := range tests {
		t.Run(tt.kind, func(t *testing.T) {
			gr := runtimev1.ResourceForKind(tt.kind)
			assert.Equal(t, tt.res, gr.Resource)
			assert.Equal(t, runtimev1.SchemeGroupVersion.Group, gr.Group)
		})
	}
}

func TestResourcePlural(t *testing.T) {
	gr := runtimev1.Resource("sandboxes")
	assert.Equal(t, "sandboxes", gr.Resource)
	assert.Equal(t, runtimev1.SchemeGroupVersion.Group, gr.Group)
}
