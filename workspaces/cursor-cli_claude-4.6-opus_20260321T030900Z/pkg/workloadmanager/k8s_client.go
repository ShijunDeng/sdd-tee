package workloadmanager

import (
	"context"
	"encoding/json"
	"fmt"
	"strconv"
	"strings"

	sandboxv1 "github.com/volcano-sh/agentcube/pkg/apis/agentsandbox/v1alpha1"
	corev1 "k8s.io/api/core/v1"
	apierrors "k8s.io/apimachinery/pkg/api/errors"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/apis/meta/v1/unstructured"
	"k8s.io/apimachinery/pkg/runtime"
	"k8s.io/apimachinery/pkg/types"
	"k8s.io/client-go/dynamic"
	"k8s.io/client-go/kubernetes"
	"k8s.io/klog/v2"
)

// LastActivityAnnotationKey matches router idle tracking.
const LastActivityAnnotationKey = "agentcube.volcano.sh/last-activity"

const (
	annotationPodName = "agentcube.volcano.sh/pod-name"
	annotationPodIP   = "agentcube.volcano.sh/pod-ip"
)

// CreateSandbox persists the Sandbox CR and creates the backing Pod.
func CreateSandbox(ctx context.Context, kube kubernetes.Interface, dyn dynamic.Interface, pod *corev1.Pod, sb *sandboxv1.Sandbox) error {
	if pod.Namespace == "" || sb.Namespace == "" {
		return fmt.Errorf("namespace required")
	}
	created, err := kube.CoreV1().Pods(pod.Namespace).Create(ctx, pod, metav1.CreateOptions{})
	if err != nil {
		return fmt.Errorf("create pod: %w", err)
	}
	if sb.Annotations == nil {
		sb.Annotations = map[string]string{}
	}
	sb.Annotations[annotationPodName] = created.Name
	sb.Annotations[LastActivityAnnotationKey] = strconv.FormatInt(metav1.Now().Unix(), 10)

	if sb.APIVersion == "" {
		sb.APIVersion = sandboxv1.SchemeGroupVersion.String()
	}
	if sb.Kind == "" {
		sb.Kind = sandboxv1.SandboxKind
	}
	uobj, err := runtime.DefaultUnstructuredConverter.ToUnstructured(sb)
	if err != nil {
		return fmt.Errorf("sandbox to unstructured: %w", err)
	}
	u := &unstructured.Unstructured{Object: uobj}
	if _, err := dyn.Resource(SandboxGVR).Namespace(sb.Namespace).Create(ctx, u, metav1.CreateOptions{}); err != nil {
		_ = kube.CoreV1().Pods(pod.Namespace).Delete(ctx, created.Name, metav1.DeleteOptions{})
		return fmt.Errorf("create sandbox: %w", err)
	}
	klog.InfoS("created sandbox workload", "sandbox", sb.Name, "pod", created.Name, "namespace", sb.Namespace)
	return nil
}

// DeleteSandbox removes the Sandbox CR and associated Pod when known.
func DeleteSandbox(ctx context.Context, kube kubernetes.Interface, dyn dynamic.Interface, namespace, sandboxName string) error {
	u, err := dyn.Resource(SandboxGVR).Namespace(namespace).Get(ctx, sandboxName, metav1.GetOptions{})
	if err != nil {
		if apierrors.IsNotFound(err) {
			return nil
		}
		return err
	}
	ann, _, _ := unstructured.NestedStringMap(u.Object, "metadata", "annotations")
	var podName string
	if ann != nil {
		podName = ann[annotationPodName]
	}
	if podName != "" {
		if err := kube.CoreV1().Pods(namespace).Delete(ctx, podName, metav1.DeleteOptions{}); err != nil && !apierrors.IsNotFound(err) {
			klog.ErrorS(err, "delete sandbox pod", "pod", podName)
		}
	}
	if err := dyn.Resource(SandboxGVR).Namespace(namespace).Delete(ctx, sandboxName, metav1.DeleteOptions{}); err != nil && !apierrors.IsNotFound(err) {
		return err
	}
	return nil
}

// GetSandboxPodIP returns the pod IP for a Sandbox, using direct pod name or annotations.
func GetSandboxPodIP(ctx context.Context, kube kubernetes.Interface, dyn dynamic.Interface, namespace, sandboxName string) (string, error) {
	u, err := dyn.Resource(SandboxGVR).Namespace(namespace).Get(ctx, sandboxName, metav1.GetOptions{})
	if err != nil {
		return "", err
	}
	ann, _, _ := unstructured.NestedStringMap(u.Object, "metadata", "annotations")
	var podName string
	if ann != nil {
		if ip := strings.TrimSpace(ann[annotationPodIP]); ip != "" {
			return ip, nil
		}
		podName = ann[annotationPodName]
	}
	if podName == "" {
		return "", fmt.Errorf("sandbox %s/%s: no pod reference", namespace, sandboxName)
	}
	pod, err := kube.CoreV1().Pods(namespace).Get(ctx, podName, metav1.GetOptions{})
	if err != nil {
		return "", err
	}
	if pod.Status.PodIP == "" {
		return "", fmt.Errorf("pod %s has no IP yet", podName)
	}
	return pod.Status.PodIP, nil
}

// PatchSandboxPodIP writes the observed pod IP onto the Sandbox for fast routing.
func PatchSandboxPodIP(ctx context.Context, dyn dynamic.Interface, namespace, sandboxName, ip string) error {
	patch, err := json.Marshal(map[string]interface{}{
		"metadata": map[string]interface{}{
			"annotations": map[string]string{annotationPodIP: ip},
		},
	})
	if err != nil {
		return err
	}
	_, err = dyn.Resource(SandboxGVR).Namespace(namespace).Patch(ctx, sandboxName, types.MergePatchType, patch, metav1.PatchOptions{})
	return err
}
