package workloadmanager

import (
	"context"
	"time"

	"github.com/volcano-sh/agentcube/pkg/store"
	"k8s.io/client-go/dynamic"
	"k8s.io/client-go/kubernetes"
	"k8s.io/klog/v2"
)

const gcBatchSize = 16

// StartGarbageCollection runs a background loop every 15s that deletes idle/expired sandboxes from Kubernetes and the store.
func StartGarbageCollection(ctx context.Context, kube kubernetes.Interface, dyn dynamic.Interface, st store.Store) {
	if st == nil || kube == nil || dyn == nil {
		klog.InfoS("garbage collection disabled: missing dependencies")
		return
	}
	go func() {
		ticker := time.NewTicker(15 * time.Second)
		defer ticker.Stop()
		for {
			select {
			case <-ctx.Done():
				return
			case <-ticker.C:
				runGarbageCollectionPass(context.Background(), kube, dyn, st)
			}
		}
	}()
}

func runGarbageCollectionPass(ctx context.Context, kube kubernetes.Interface, dyn dynamic.Interface, st store.Store) {
	now := time.Now().Unix()
	idleCutoff := time.Now().Add(-DefaultSandboxIdleTimeout).Unix()

	expired, err := st.ListExpiredSandboxes(ctx, now, gcBatchSize)
	if err != nil {
		klog.ErrorS(err, "list expired sandboxes")
	}
	inactive, err := st.ListInactiveSandboxes(ctx, idleCutoff, gcBatchSize)
	if err != nil {
		klog.ErrorS(err, "list inactive sandboxes")
	}

	seen := map[string]struct{}{}
	for _, sb := range append(expired, inactive...) {
		if sb == nil || sb.SessionID == "" {
			continue
		}
		if _, ok := seen[sb.SessionID]; ok {
			continue
		}
		seen[sb.SessionID] = struct{}{}
		if sb.SandboxCRName == "" || sb.Namespace == "" {
			if err := st.DeleteSandboxBySessionID(ctx, sb.SessionID); err != nil {
				klog.V(4).InfoS("gc store delete", "sessionID", sb.SessionID, "err", err)
			}
			continue
		}
		if err := DeleteSandbox(ctx, kube, dyn, sb.Namespace, sb.SandboxCRName); err != nil {
			klog.ErrorS(err, "gc delete sandbox", "sessionID", sb.SessionID, "sandbox", sb.SandboxCRName)
			continue
		}
		if err := st.DeleteSandboxBySessionID(ctx, sb.SessionID); err != nil {
			klog.V(4).InfoS("gc store delete after kube", "sessionID", sb.SessionID, "err", err)
		}
		klog.V(3).InfoS("gc reclaimed sandbox", "sessionID", sb.SessionID)
	}
}
