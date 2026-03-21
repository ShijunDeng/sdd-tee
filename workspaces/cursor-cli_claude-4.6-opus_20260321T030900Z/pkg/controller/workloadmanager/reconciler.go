package workloadmanager

import (
	"context"

	agentsandboxv1 "github.com/volcano-sh/agentcube/pkg/apis/agentsandbox/v1alpha1"
	runtimev1alpha1 "github.com/volcano-sh/agentcube/pkg/apis/runtime/v1alpha1"
	wlm "github.com/volcano-sh/agentcube/pkg/workloadmanager"
	"k8s.io/apimachinery/pkg/runtime"
	ctrl "sigs.k8s.io/controller-runtime"
	"sigs.k8s.io/controller-runtime/pkg/client"
	"sigs.k8s.io/controller-runtime/pkg/log"
)

// SandboxReconciler drives Sandbox lifecycle in the control plane.
type SandboxReconciler struct {
	Client           client.Client
	Scheme           *runtime.Scheme
	RuntimeClassName string
}

// Reconcile satisfies ctrl.Reconciler.
func (r *SandboxReconciler) Reconcile(ctx context.Context, req ctrl.Request) (ctrl.Result, error) {
	logger := log.FromContext(ctx).WithValues("sandbox", req.NamespacedName)
	var sb agentsandboxv1.Sandbox
	if err := r.Client.Get(ctx, req.NamespacedName, &sb); err != nil {
		return ctrl.Result{}, client.IgnoreNotFound(err)
	}
	if r.RuntimeClassName != "" && (sb.Spec.RuntimeClassName == nil || *sb.Spec.RuntimeClassName == "") {
		rc := r.RuntimeClassName
		sb.Spec.RuntimeClassName = &rc
		if err := r.Client.Update(ctx, &sb); err != nil {
			return ctrl.Result{}, err
		}
	}
	logger.V(4).Info("reconciled sandbox")
	return ctrl.Result{}, nil
}

// SetupWithManager wires the controller.
func (r *SandboxReconciler) SetupWithManager(mgr ctrl.Manager) error {
	return ctrl.NewControllerManagedBy(mgr).
		For(&agentsandboxv1.Sandbox{}).
		Complete(r)
}

// CodeInterpreterReconciler manages CodeInterpreter resources.
type CodeInterpreterReconciler struct {
	Client client.Client
	Scheme *runtime.Scheme
	Warm   *wlm.CodeInterpreterReconciler
}

// Reconcile satisfies ctrl.Reconciler.
func (r *CodeInterpreterReconciler) Reconcile(ctx context.Context, req ctrl.Request) (ctrl.Result, error) {
	logger := log.FromContext(ctx).WithValues("codeInterpreter", req.NamespacedName)
	var ci runtimev1alpha1.CodeInterpreter
	if err := r.Client.Get(ctx, req.NamespacedName, &ci); err != nil {
		return ctrl.Result{}, client.IgnoreNotFound(err)
	}
	ci.Namespace = req.Namespace
	if r.Warm != nil {
		if err := r.Warm.Reconcile(ctx, &ci); err != nil {
			return ctrl.Result{}, err
		}
	}
	logger.V(4).Info("reconciled code interpreter")
	return ctrl.Result{}, nil
}

// SetupWithManager wires the controller.
func (r *CodeInterpreterReconciler) SetupWithManager(mgr ctrl.Manager) error {
	return ctrl.NewControllerManagedBy(mgr).
		For(&runtimev1alpha1.CodeInterpreter{}).
		Complete(r)
}
