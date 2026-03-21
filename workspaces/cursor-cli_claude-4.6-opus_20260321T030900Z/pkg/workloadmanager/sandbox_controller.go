package workloadmanager

import (
	"context"
	"sync"
	"time"

	"k8s.io/apimachinery/pkg/types"
	"k8s.io/client-go/dynamic"
	"k8s.io/client-go/kubernetes"
	"k8s.io/klog/v2"
)

// SandboxReconciler coordinates waiters for Sandbox readiness (pod IP available).
type SandboxReconciler struct {
	mu      sync.Mutex
	waiters map[types.NamespacedName]chan struct{}
}

// NewSandboxReconciler constructs an empty reconciler registry.
func NewSandboxReconciler() *SandboxReconciler {
	return &SandboxReconciler{
		waiters: make(map[types.NamespacedName]chan struct{}),
	}
}

// WatchSandboxOnce registers a channel closed when the sandbox becomes runnable (pod IP known).
func (r *SandboxReconciler) WatchSandboxOnce(nn types.NamespacedName) <-chan struct{} {
	ch := make(chan struct{})
	r.mu.Lock()
	r.waiters[nn] = ch
	r.mu.Unlock()
	return ch
}

// UnWatchSandbox removes a waiter and closes its channel so blocked callers can exit.
func (r *SandboxReconciler) UnWatchSandbox(nn types.NamespacedName) {
	r.mu.Lock()
	ch, ok := r.waiters[nn]
	delete(r.waiters, nn)
	r.mu.Unlock()
	if ok && ch != nil {
		close(ch)
	}
}

// NotifyRunning signals all waiters for the given Sandbox namespaced name.
func (r *SandboxReconciler) NotifyRunning(nn types.NamespacedName) {
	r.mu.Lock()
	ch, ok := r.waiters[nn]
	delete(r.waiters, nn)
	r.mu.Unlock()
	if ok && ch != nil {
		close(ch)
	}
}

// PollSandboxUntilReady polls Kubernetes until a pod IP is published or context ends.
func (r *SandboxReconciler) PollSandboxUntilReady(ctx context.Context, kube kubernetes.Interface, dyn dynamic.Interface, nn types.NamespacedName) {
	ticker := time.NewTicker(2 * time.Second)
	defer ticker.Stop()
	for {
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
			ip, err := GetSandboxPodIP(ctx, kube, dyn, nn.Namespace, nn.Name)
			if err != nil || ip == "" {
				continue
			}
			if err := PatchSandboxPodIP(ctx, dyn, nn.Namespace, nn.Name, ip); err != nil {
				klog.V(4).InfoS("patch sandbox pod ip", "err", err, "sandbox", nn.String())
			}
			r.NotifyRunning(nn)
			return
		}
	}
}
