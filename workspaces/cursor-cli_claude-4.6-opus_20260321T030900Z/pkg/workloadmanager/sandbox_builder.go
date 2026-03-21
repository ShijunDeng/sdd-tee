package workloadmanager

import (
	"context"
	"fmt"
	"strings"

	"github.com/google/uuid"
	sandboxv1 "github.com/volcano-sh/agentcube/pkg/apis/agentsandbox/v1alpha1"
	runtimev1 "github.com/volcano-sh/agentcube/pkg/apis/runtime/v1alpha1"
	commontypes "github.com/volcano-sh/agentcube/pkg/common/types"
	corev1 "k8s.io/api/core/v1"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/apis/meta/v1/unstructured"
	"k8s.io/apimachinery/pkg/runtime"
	"k8s.io/apimachinery/pkg/types"
	"k8s.io/client-go/dynamic"
	"k8s.io/client-go/kubernetes"
	"k8s.io/klog/v2"
)

// SandboxBuilder materializes pods and Sandbox / SandboxClaims from CRD templates.
type SandboxBuilder struct {
	Dyn  dynamic.Interface
	Kube kubernetes.Interface
	RC   *SandboxReconciler
}

func sessionFromRequest(req *commontypes.CreateSandboxRequest) string {
	if req.Metadata != nil {
		if s := strings.TrimSpace(req.Metadata["sessionID"]); s != "" {
			return s
		}
	}
	return uuid.NewString()
}

func shortSessionKey(s string) string {
	s = strings.ReplaceAll(s, "-", "")
	if len(s) < 8 {
		if s == "" {
			return "sess"
		}
		return s
	}
	return s[:8]
}

// BuildSandboxByAgentRuntime creates a Sandbox + Pod from an AgentRuntime template.
func (b *SandboxBuilder) BuildSandboxByAgentRuntime(ctx context.Context, req *commontypes.CreateSandboxRequest) (*commontypes.CreateSandboxResponse, types.NamespacedName, error) {
	if err := req.Validate(); err != nil {
		return nil, types.NamespacedName{}, err
	}
	u, err := b.Dyn.Resource(AgentRuntimeGVR).Namespace(req.Namespace).Get(ctx, req.Name, metav1.GetOptions{})
	if err != nil {
		return nil, types.NamespacedName{}, fmt.Errorf("get AgentRuntime: %w", err)
	}
	var ar runtimev1.AgentRuntime
	if err := runtime.DefaultUnstructuredConverter.FromUnstructured(u.Object, &ar); err != nil {
		return nil, types.NamespacedName{}, fmt.Errorf("convert AgentRuntime: %w", err)
	}
	if ar.Spec.PodTemplate == nil {
		return nil, types.NamespacedName{}, fmt.Errorf("AgentRuntime %s has no podTemplate", req.Name)
	}
	sid := sessionFromRequest(req)
	sandboxName := fmt.Sprintf("sbx-ar-%s-%s", sanitizeDNS(req.Name), shortSessionKey(sid))
	nn := types.NamespacedName{Namespace: req.Namespace, Name: sandboxName}

	pt := ar.Spec.PodTemplate
	pod := &corev1.Pod{
		ObjectMeta: metav1.ObjectMeta{
			Namespace:    req.Namespace,
			GenerateName: fmt.Sprintf("ac-ar-%s-", sanitizeDNS(req.Name)),
			Labels: mergeStringMaps(map[string]string{
				"agentcube.volcano.sh/session-id": sid,
				"agentcube.volcano.sh/resource":   req.Name,
				"app":                             "agentcube-sandbox",
			}, pt.Labels),
			Annotations: mergeStringMaps(map[string]string{
				LastActivityAnnotationKey: fmt.Sprintf("%d", metav1.Now().Unix()),
			}, pt.Annotations),
		},
		Spec: *pt.Spec.DeepCopy(),
	}

	sb := &sandboxv1.Sandbox{
		TypeMeta: metav1.TypeMeta{
			APIVersion: sandboxv1.SchemeGroupVersion.String(),
			Kind:       sandboxv1.SandboxKind,
		},
		ObjectMeta: metav1.ObjectMeta{
			Name:      sandboxName,
			Namespace: req.Namespace,
			Labels:    map[string]string{"agentcube.volcano.sh/session-id": sid},
		},
		Spec: sandboxv1.SandboxSpec{},
	}
	if pod.Spec.RuntimeClassName != nil && *pod.Spec.RuntimeClassName != "" {
		rc := *pod.Spec.RuntimeClassName
		sb.Spec.RuntimeClassName = &rc
	}

	if b.RC != nil {
		go b.RC.PollSandboxUntilReady(context.Background(), b.Kube, b.Dyn, nn)
	}
	if err := CreateSandbox(ctx, b.Kube, b.Dyn, pod, sb); err != nil {
		return nil, nn, err
	}

	resp := &commontypes.CreateSandboxResponse{
		SessionID:   sid,
		Name:        req.Name,
		Namespace:   req.Namespace,
		SandboxName: sandboxName,
		EntryPoints: entryPointsFromAR(ar),
	}
	klog.InfoS("built agent runtime sandbox", "sandbox", sandboxName, "session", sid)
	return resp, nn, nil
}

// BuildSandboxByCodeInterpreter creates sandboxes for a CodeInterpreter.
func (b *SandboxBuilder) BuildSandboxByCodeInterpreter(ctx context.Context, req *commontypes.CreateSandboxRequest) (*commontypes.CreateSandboxResponse, types.NamespacedName, error) {
	if err := req.Validate(); err != nil {
		return nil, types.NamespacedName{}, err
	}
	u, err := b.Dyn.Resource(CodeInterpreterGVR).Namespace(req.Namespace).Get(ctx, req.Name, metav1.GetOptions{})
	if err != nil {
		return nil, types.NamespacedName{}, fmt.Errorf("get CodeInterpreter: %w", err)
	}
	var ci runtimev1.CodeInterpreter
	if err := runtime.DefaultUnstructuredConverter.FromUnstructured(u.Object, &ci); err != nil {
		return nil, types.NamespacedName{}, fmt.Errorf("convert CodeInterpreter: %w", err)
	}
	if ci.Spec.Template == nil {
		return nil, types.NamespacedName{}, fmt.Errorf("CodeInterpreter %s has no template", req.Name)
	}
	sid := sessionFromRequest(req)
	sandboxName := fmt.Sprintf("sbx-ci-%s-%s", sanitizeDNS(req.Name), shortSessionKey(sid))
	nn := types.NamespacedName{Namespace: req.Namespace, Name: sandboxName}

	if ci.Spec.WarmPoolSize != nil && *ci.Spec.WarmPoolSize > 0 {
		if err := b.ensureSandboxClaim(ctx, req.Namespace, req.Name, sid); err != nil {
			return nil, nn, err
		}
	}

	tpl := ci.Spec.Template
	pod := &corev1.Pod{
		ObjectMeta: metav1.ObjectMeta{
			Namespace:    req.Namespace,
			GenerateName: fmt.Sprintf("ac-ci-%s-", sanitizeDNS(req.Name)),
			Labels: mergeStringMaps(map[string]string{
				"agentcube.volcano.sh/session-id": sid,
				"agentcube.volcano.sh/resource":   req.Name,
				"app":                             "agentcube-sandbox",
			}, tpl.Labels),
			Annotations: mergeStringMaps(map[string]string{
				LastActivityAnnotationKey: fmt.Sprintf("%d", metav1.Now().Unix()),
			}, tpl.Annotations),
		},
		Spec: corev1.PodSpec{
			Containers: []corev1.Container{
				{
					Name:            "interpreter",
					Image:           tpl.Image,
					ImagePullPolicy: tpl.ImagePullPolicy,
					Command:         tpl.Command,
					Args:            tpl.Args,
					Resources:       tpl.Resources,
					Env:             tpl.Environment,
				},
			},
			ImagePullSecrets: tpl.ImagePullSecrets,
			RuntimeClassName: tpl.RuntimeClassName,
		},
	}
	if ci.Spec.AuthMode == runtimev1.AuthModePicoD {
		if pod.Labels == nil {
			pod.Labels = map[string]string{}
		}
		pod.Labels["agentcube.volcano.sh/auth"] = "picod"
	}

	sb := &sandboxv1.Sandbox{
		TypeMeta: metav1.TypeMeta{
			APIVersion: sandboxv1.SchemeGroupVersion.String(),
			Kind:       sandboxv1.SandboxKind,
		},
		ObjectMeta: metav1.ObjectMeta{
			Name:      sandboxName,
			Namespace: req.Namespace,
			Labels:    map[string]string{"agentcube.volcano.sh/session-id": sid},
		},
		Spec: sandboxv1.SandboxSpec{},
	}
	if tpl.RuntimeClassName != nil {
		sb.Spec.RuntimeClassName = tpl.RuntimeClassName
	}

	if b.RC != nil {
		go b.RC.PollSandboxUntilReady(context.Background(), b.Kube, b.Dyn, nn)
	}
	if err := CreateSandbox(ctx, b.Kube, b.Dyn, pod, sb); err != nil {
		return nil, nn, err
	}

	resp := &commontypes.CreateSandboxResponse{
		SessionID:   sid,
		Name:        req.Name,
		Namespace:   req.Namespace,
		SandboxName: sandboxName,
		EntryPoints: entryPointsFromCI(ci),
	}
	klog.InfoS("built code interpreter sandbox", "sandbox", sandboxName, "session", sid)
	return resp, nn, nil
}

func (b *SandboxBuilder) ensureSandboxClaim(ctx context.Context, namespace, ciName, sessionID string) error {
	claim := &unstructured.Unstructured{Object: map[string]interface{}{
		"apiVersion": SandboxClaimGVR.Group + "/" + SandboxClaimGVR.Version,
		"kind":       "SandboxClaims",
		"metadata": map[string]interface{}{
			"name":      fmt.Sprintf("claim-%s-%s", sanitizeDNS(ciName), shortSessionKey(sessionID)),
			"namespace": namespace,
			"labels": map[string]string{
				"agentcube.volcano.sh/code-interpreter": ciName,
				"agentcube.volcano.sh/session-id":       sessionID,
			},
		},
		"spec": map[string]interface{}{
			"sessionID": sessionID,
		},
	}}
	if _, err := b.Dyn.Resource(SandboxClaimGVR).Namespace(namespace).Create(ctx, claim, metav1.CreateOptions{}); err != nil {
		return fmt.Errorf("create SandboxClaims: %w", err)
	}
	return nil
}

func entryPointsFromAR(ar runtimev1.AgentRuntime) []commontypes.SandboxEntryPoint {
	out := make([]commontypes.SandboxEntryPoint, 0, len(ar.Spec.TargetPorts))
	for _, tp := range ar.Spec.TargetPorts {
		out = append(out, commontypes.SandboxEntryPoint{
			PathPrefix: tp.PathPrefix,
			Name:       tp.Name,
			Port:       tp.Port,
			Protocol:   string(tp.Protocol),
		})
	}
	return out
}

func entryPointsFromCI(ci runtimev1.CodeInterpreter) []commontypes.SandboxEntryPoint {
	out := make([]commontypes.SandboxEntryPoint, 0, len(ci.Spec.Ports))
	for _, tp := range ci.Spec.Ports {
		out = append(out, commontypes.SandboxEntryPoint{
			PathPrefix: tp.PathPrefix,
			Name:       tp.Name,
			Port:       tp.Port,
			Protocol:   string(tp.Protocol),
		})
	}
	return out
}

func mergeStringMaps(base, extra map[string]string) map[string]string {
	if len(extra) == 0 {
		return base
	}
	if base == nil {
		base = map[string]string{}
	}
	for k, v := range extra {
		if v != "" {
			base[k] = v
		}
	}
	return base
}

func sanitizeDNS(s string) string {
	s = strings.ToLower(s)
	var b strings.Builder
	for _, r := range s {
		if (r >= 'a' && r <= 'z') || (r >= '0' && r <= '9') || r == '-' {
			b.WriteRune(r)
		} else {
			b.WriteRune('-')
		}
	}
	out := b.String()
	if out == "" {
		return "x"
	}
	return out
}

func deref(s *string) string {
	if s == nil {
		return ""
	}
	return *s
}
