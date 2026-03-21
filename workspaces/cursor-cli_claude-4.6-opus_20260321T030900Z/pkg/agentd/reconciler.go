package agentd

import (
	"context"
	"strconv"
	"time"

	agentsandboxv1 "github.com/volcano-sh/agentcube/pkg/apis/agentsandbox/v1alpha1"
	"github.com/volcano-sh/agentcube/pkg/workloadmanager"
	"k8s.io/apimachinery/pkg/runtime"
	ctrl "sigs.k8s.io/controller-runtime"
	"sigs.k8s.io/controller-runtime/pkg/client"
	"sigs.k8s.io/controller-runtime/pkg/log"
)

const idleTimeout = 15 * time.Minute

// Reconciler garbage-collects idle Sandbox objects on agent nodes based on last-activity annotations.
type Reconciler struct {
	Client client.Client
	Scheme *runtime.Scheme
}

// Reconcile implements controller-runtime reconcile.Reconciler.
func (r *Reconciler) Reconcile(ctx context.Context, req ctrl.Request) (ctrl.Result, error) {
	logger := log.FromContext(ctx).WithValues("sandbox", req.NamespacedName)
	var sb agentsandboxv1.Sandbox
	if err := r.Client.Get(ctx, req.NamespacedName, &sb); err != nil {
		return ctrl.Result{}, client.IgnoreNotFound(err)
	}
	raw := sb.Annotations[workloadmanager.LastActivityAnnotationKey]
	if raw == "" {
		logger.V(4).Info("missing last activity annotation; requeue")
		return ctrl.Result{RequeueAfter: time.Minute}, nil
	}
	ts, err := strconv.ParseInt(raw, 10, 64)
	if err != nil {
		logger.Info("invalid last activity annotation", "value", raw)
		return ctrl.Result{RequeueAfter: time.Minute}, nil
	}
	last := time.Unix(ts, 0)
	now := time.Now()
	if now.Sub(last) >= idleTimeout {
		if err := r.Client.Delete(ctx, &sb); err != nil {
			return ctrl.Result{}, err
		}
		logger.Info("deleted expired sandbox", "lastActivity", last.UTC())
		return ctrl.Result{}, nil
	}
	wait := idleTimeout - now.Sub(last)
	if wait < time.Second {
		wait = time.Second
	}
	return ctrl.Result{RequeueAfter: wait}, nil
}

// SetupWithManager registers this reconciler.
func (r *Reconciler) SetupWithManager(mgr ctrl.Manager) error {
	return ctrl.NewControllerManagedBy(mgr).
		For(&agentsandboxv1.Sandbox{}).
		Complete(r)
}
