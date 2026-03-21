package workloadmanager

import (
	"context"
	"encoding/json"
	"fmt"

	runtimev1 "github.com/volcano-sh/agentcube/pkg/apis/runtime/v1alpha1"
	apierrors "k8s.io/apimachinery/pkg/api/errors"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/apis/meta/v1/unstructured"
	"k8s.io/apimachinery/pkg/runtime"
	"k8s.io/apimachinery/pkg/types"
	"k8s.io/client-go/dynamic"
	"k8s.io/klog/v2"
)

// CodeInterpreterReconciler manages SandboxTemplate / SandboxWarmPool objects for CodeInterpreter warm pools.
type CodeInterpreterReconciler struct {
	Dyn dynamic.Interface
}

// Reconcile applies warm-pool auxiliary resources and updates Ready status.
func (r *CodeInterpreterReconciler) Reconcile(ctx context.Context, ci *runtimev1.CodeInterpreter) error {
	if r.Dyn == nil || ci == nil {
		return fmt.Errorf("invalid reconciler state")
	}
	ns := ci.Namespace
	name := ci.Name
	if ci.Spec.WarmPoolSize != nil && *ci.Spec.WarmPoolSize > 0 {
		if err := r.ensureSandboxTemplate(ctx, ns, name, ci); err != nil {
			return err
		}
		if err := r.ensureSandboxWarmPool(ctx, ns, name, ci); err != nil {
			return err
		}
		return r.updateStatus(ctx, ns, name, true)
	}
	if err := r.deleteWarmPool(ctx, ns, name); err != nil {
		return err
	}
	return r.updateStatus(ctx, ns, name, false)
}

func (r *CodeInterpreterReconciler) ensureSandboxTemplate(ctx context.Context, namespace, ciName string, ci *runtimev1.CodeInterpreter) error {
	tplName := fmt.Sprintf("%s-template", ciName)
	tplObj, err := runtime.DefaultUnstructuredConverter.ToUnstructured(ci.Spec.Template)
	if err != nil {
		return fmt.Errorf("template to unstructured: %w", err)
	}
	obj := &unstructured.Unstructured{Object: map[string]interface{}{
		"apiVersion": SandboxTemplateGVR.Group + "/" + SandboxTemplateGVR.Version,
		"kind":       "SandboxTemplate",
		"metadata": map[string]interface{}{
			"name":      tplName,
			"namespace": namespace,
			"labels": map[string]string{
				"agentcube.volcano.sh/code-interpreter": ciName,
			},
		},
		"spec": map[string]interface{}{
			"codeInterpreterRef": ciName,
			"template":           tplObj,
		},
	}}
	return r.createIfAbsent(ctx, r.Dyn.Resource(SandboxTemplateGVR).Namespace(namespace), tplName, obj, "SandboxTemplate")
}

func (r *CodeInterpreterReconciler) ensureSandboxWarmPool(ctx context.Context, namespace, ciName string, ci *runtimev1.CodeInterpreter) error {
	poolName := fmt.Sprintf("%s-warmpool", ciName)
	size := int64(0)
	if ci.Spec.WarmPoolSize != nil {
		size = int64(*ci.Spec.WarmPoolSize)
	}
	obj := &unstructured.Unstructured{Object: map[string]interface{}{
		"apiVersion": SandboxWarmPoolGVR.Group + "/" + SandboxWarmPoolGVR.Version,
		"kind":       "SandboxWarmPool",
		"metadata": map[string]interface{}{
			"name":      poolName,
			"namespace": namespace,
			"labels": map[string]string{
				"agentcube.volcano.sh/code-interpreter": ciName,
			},
		},
		"spec": map[string]interface{}{
			"size":               size,
			"codeInterpreterRef": ciName,
			"templateRef":        fmt.Sprintf("%s-template", ciName),
		},
	}}
	return r.createIfAbsent(ctx, r.Dyn.Resource(SandboxWarmPoolGVR).Namespace(namespace), poolName, obj, "SandboxWarmPool")
}

func (r *CodeInterpreterReconciler) deleteWarmPool(ctx context.Context, namespace, ciName string) error {
	_ = r.Dyn.Resource(SandboxWarmPoolGVR).Namespace(namespace).Delete(ctx, fmt.Sprintf("%s-warmpool", ciName), metav1.DeleteOptions{})
	_ = r.Dyn.Resource(SandboxTemplateGVR).Namespace(namespace).Delete(ctx, fmt.Sprintf("%s-template", ciName), metav1.DeleteOptions{})
	return nil
}

func (r *CodeInterpreterReconciler) createIfAbsent(ctx context.Context, ri dynamic.ResourceInterface, name string, obj *unstructured.Unstructured, kind string) error {
	_, err := ri.Get(ctx, name, metav1.GetOptions{})
	if apierrors.IsNotFound(err) {
		if _, err := ri.Create(ctx, obj, metav1.CreateOptions{}); err != nil {
			return fmt.Errorf("create %s %s: %w", kind, name, err)
		}
		klog.InfoS("created warm-pool resource", "kind", kind, "name", name)
		return nil
	}
	return err
}

func (r *CodeInterpreterReconciler) updateStatus(ctx context.Context, namespace, name string, ready bool) error {
	cond := map[string]interface{}{
		"type":               "Ready",
		"status":             "False",
		"reason":             "WarmPoolDisabled",
		"message":            "Warm pool not configured",
		"lastTransitionTime": metav1.Now().UTC().Format("2006-01-02T15:04:05Z07:00"),
	}
	if ready {
		cond["status"] = "True"
		cond["reason"] = "WarmPoolReady"
		cond["message"] = "Warm pool resources ensured"
	}
	patch, err := json.Marshal(map[string]interface{}{
		"status": map[string]interface{}{
			"ready":      ready,
			"conditions": []interface{}{cond},
		},
	})
	if err != nil {
		return err
	}
	_, err = r.Dyn.Resource(CodeInterpreterGVR).Namespace(namespace).Patch(ctx, name, types.MergePatchType, patch, metav1.PatchOptions{}, "status")
	if err != nil {
		return fmt.Errorf("patch CodeInterpreter status: %w", err)
	}
	return nil
}
