package workloadmanager_test

import (
	"context"
	"testing"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
	corev1 "k8s.io/api/core/v1"
	"k8s.io/apimachinery/pkg/runtime"
	dynamicfake "k8s.io/client-go/dynamic/fake"
	kubefake "k8s.io/client-go/kubernetes/fake"
	kubetesting "k8s.io/client-go/testing"

	commontypes "github.com/volcano-sh/agentcube/pkg/common/types"
	"github.com/volcano-sh/agentcube/pkg/workloadmanager"
)

func TestBuildSandboxByAgentRuntime_Validation(t *testing.T) {
	s := testScheme(t)
	dyn := dynamicfake.NewSimpleDynamicClient(s)
	kube := kubefake.NewSimpleClientset()
	b := &workloadmanager.SandboxBuilder{Dyn: dyn, Kube: kube}

	_, _, err := b.BuildSandboxByAgentRuntime(context.Background(), &commontypes.CreateSandboxRequest{
		Name: "", Namespace: "ns", Kind: commontypes.AgentRuntimeKind,
	})
	require.Error(t, err)
	assert.Contains(t, err.Error(), "name")
}

func TestBuildSandboxByAgentRuntime_NotFound(t *testing.T) {
	s := testScheme(t)
	dyn := dynamicfake.NewSimpleDynamicClient(s)
	kube := kubefake.NewSimpleClientset()
	b := &workloadmanager.SandboxBuilder{Dyn: dyn, Kube: kube}

	_, _, err := b.BuildSandboxByAgentRuntime(context.Background(), &commontypes.CreateSandboxRequest{
		Name: "missing", Namespace: "default", Kind: commontypes.AgentRuntimeKind,
	})
	require.Error(t, err)
	assert.Contains(t, err.Error(), "AgentRuntime")
}

func TestBuildSandboxByAgentRuntime_Success(t *testing.T) {
	s := testScheme(t)
	dyn := dynamicfake.NewSimpleDynamicClient(s, agentRuntimeUnstructured("ar", "default"))
	kube := kubefake.NewSimpleClientset()
	kube.PrependReactor("create", "pods", func(action kubetesting.Action) (bool, runtime.Object, error) {
		create := action.(kubetesting.CreateAction)
		pod := create.GetObject().(*corev1.Pod)
		if pod.Name == "" {
			pod.Name = "pod-ar-success"
		}
		pod.Status.PodIP = "10.0.0.2"
		return false, nil, nil
	})
	b := &workloadmanager.SandboxBuilder{Dyn: dyn, Kube: kube}

	resp, nn, err := b.BuildSandboxByAgentRuntime(context.Background(), &commontypes.CreateSandboxRequest{
		Name: "ar", Namespace: "default", Kind: commontypes.AgentRuntimeKind,
		Metadata: map[string]string{"sessionID": "sess-fixed-12345678"},
	})
	require.NoError(t, err)
	assert.Equal(t, "default", nn.Namespace)
	assert.Contains(t, resp.SandboxName, "sbx-ar-ar-sessfixe")
	assert.Equal(t, "sess-fixed-12345678", resp.SessionID)
	assert.Len(t, resp.EntryPoints, 1)
	assert.Equal(t, uint32(8080), resp.EntryPoints[0].Port)
}

func TestBuildSandboxByCodeInterpreter_MissingTemplate(t *testing.T) {
	s := testScheme(t)
	dyn := dynamicfake.NewSimpleDynamicClient(s, codeInterpreterNoTemplateUnstructured("ci", "default"))
	kube := kubefake.NewSimpleClientset()
	b := &workloadmanager.SandboxBuilder{Dyn: dyn, Kube: kube}

	_, _, err := b.BuildSandboxByCodeInterpreter(context.Background(), &commontypes.CreateSandboxRequest{
		Name: "ci", Namespace: "default", Kind: commontypes.CodeInterpreterKind,
	})
	require.Error(t, err)
	assert.Contains(t, err.Error(), "template")
}

func TestBuildSandboxByCodeInterpreter_Success(t *testing.T) {
	s := testScheme(t)
	dyn := dynamicfake.NewSimpleDynamicClient(s, codeInterpreterUnstructuredPort("ci", "default", 9000))
	kube := kubefake.NewSimpleClientset()
	kube.PrependReactor("create", "pods", func(action kubetesting.Action) (bool, runtime.Object, error) {
		create := action.(kubetesting.CreateAction)
		pod := create.GetObject().(*corev1.Pod)
		if pod.Name == "" {
			pod.Name = "pod-ci-success"
		}
		pod.Status.PodIP = "10.0.0.3"
		return false, nil, nil
	})
	b := &workloadmanager.SandboxBuilder{Dyn: dyn, Kube: kube}

	resp, nn, err := b.BuildSandboxByCodeInterpreter(context.Background(), &commontypes.CreateSandboxRequest{
		Name: "ci", Namespace: "default", Kind: commontypes.CodeInterpreterKind,
	})
	require.NoError(t, err)
	assert.Equal(t, "default", nn.Namespace)
	assert.Contains(t, resp.SandboxName, "sbx-ci-ci-")
	assert.Len(t, resp.EntryPoints, 1)
	assert.Equal(t, uint32(9000), resp.EntryPoints[0].Port)
}
