//go:build e2e

package e2e_test

import (
	"context"
	"os"
	"testing"
	"time"

	apierrors "k8s.io/apimachinery/pkg/api/errors"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/apis/meta/v1/unstructured"
	"k8s.io/apimachinery/pkg/runtime/schema"
	"k8s.io/client-go/dynamic"
	"k8s.io/client-go/tools/clientcmd"
)

var runtimeGVR = schema.GroupVersionResource{
	Group:    "runtime.agentcube.volcano.sh",
	Version:  "v1alpha1",
	Resource: "agentruntimes",
}

var interpreterGVR = schema.GroupVersionResource{
	Group:    "runtime.agentcube.volcano.sh",
	Version:  "v1alpha1",
	Resource: "codeinterpreters",
}

func kubeConfigPath() string {
	if p := os.Getenv("KUBECONFIG"); p != "" {
		return p
	}
	if home, err := os.UserHomeDir(); err == nil {
		return home + "/.kube/config"
	}
	return ""
}

func dynamicClient(t *testing.T) dynamic.Interface {
	t.Helper()
	cfgPath := kubeConfigPath()
	cfg, err := clientcmd.BuildConfigFromFlags("", cfgPath)
	if err != nil {
		t.Skipf("kubeconfig not available: %v", err)
	}
	cli, err := dynamic.NewForConfig(cfg)
	if err != nil {
		t.Fatalf("dynamic client: %v", err)
	}
	return cli
}

func testNamespace() string {
	if ns := os.Getenv("AGENTCUBE_E2E_NAMESPACE"); ns != "" {
		return ns
	}
	return "default"
}

func TestCodeInterpreterCRUD(t *testing.T) {
	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Minute)
	defer cancel()

	cli := dynamicClient(t)
	ns := testNamespace()

	name := "e2e-ci-" + time.Now().Format("150405")
	obj := &unstructured.Unstructured{
		Object: map[string]interface{}{
			"apiVersion": "runtime.agentcube.volcano.sh/v1alpha1",
			"kind":       "CodeInterpreter",
			"metadata": map[string]interface{}{
				"name":      name,
				"namespace": ns,
			},
			"spec": map[string]interface{}{
				"ports": []interface{}{
					map[string]interface{}{
						"pathPrefix": "/api",
						"name":       "http",
						"port":       int64(8080),
						"protocol":   "HTTP",
					},
				},
				"template": map[string]interface{}{
					"image": "busybox:1.36",
				},
			},
		},
	}

	_, err := cli.Resource(interpreterGVR).Namespace(ns).Create(ctx, obj, metav1.CreateOptions{})
	if err != nil {
		if apierrors.IsNotFound(err) {
			t.Skipf("CodeInterpreter CRD not installed: %v", err)
		}
		t.Fatalf("create CodeInterpreter: %v", err)
	}
	t.Cleanup(func() {
		_ = cli.Resource(interpreterGVR).Namespace(ns).Delete(context.Background(), name, metav1.DeleteOptions{})
	})

	got, err := cli.Resource(interpreterGVR).Namespace(ns).Get(ctx, name, metav1.GetOptions{})
	if err != nil {
		t.Fatalf("get CodeInterpreter: %v", err)
	}
	if got.GetName() != name {
		t.Fatalf("unexpected name %q", got.GetName())
	}
}

func TestAgentRuntimeCRUD(t *testing.T) {
	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Minute)
	defer cancel()

	cli := dynamicClient(t)
	ns := testNamespace()

	name := "e2e-ar-" + time.Now().Format("150405")
	obj := &unstructured.Unstructured{
		Object: map[string]interface{}{
			"apiVersion": "runtime.agentcube.volcano.sh/v1alpha1",
			"kind":       "AgentRuntime",
			"metadata": map[string]interface{}{
				"name":      name,
				"namespace": ns,
			},
			"spec": map[string]interface{}{
				"targetPorts": []interface{}{
					map[string]interface{}{
						"pathPrefix": "/",
						"name":       "http",
						"port":       int64(8080),
						"protocol":   "HTTP",
					},
				},
				"podTemplate": map[string]interface{}{
					"spec": map[string]interface{}{
						"containers": []interface{}{
							map[string]interface{}{
								"name":  "agent",
								"image": "busybox:1.36",
							},
						},
					},
				},
			},
		},
	}

	_, err := cli.Resource(runtimeGVR).Namespace(ns).Create(ctx, obj, metav1.CreateOptions{})
	if err != nil {
		if apierrors.IsNotFound(err) {
			t.Skipf("AgentRuntime CRD not installed: %v", err)
		}
		t.Fatalf("create AgentRuntime: %v", err)
	}
	t.Cleanup(func() {
		_ = cli.Resource(runtimeGVR).Namespace(ns).Delete(context.Background(), name, metav1.DeleteOptions{})
	})

	got, err := cli.Resource(runtimeGVR).Namespace(ns).Get(ctx, name, metav1.GetOptions{})
	if err != nil {
		t.Fatalf("get AgentRuntime: %v", err)
	}
	if got.GetName() != name {
		t.Fatalf("unexpected name %q", got.GetName())
	}
}
