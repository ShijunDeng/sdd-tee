package agentd_test

import (
	"context"
	"strconv"
	"testing"
	"time"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
	apierrors "k8s.io/apimachinery/pkg/api/errors"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/runtime"
	"k8s.io/apimachinery/pkg/types"
	ctrl "sigs.k8s.io/controller-runtime"
	"sigs.k8s.io/controller-runtime/pkg/client"
	"sigs.k8s.io/controller-runtime/pkg/client/fake"

	agentsandboxv1 "github.com/volcano-sh/agentcube/pkg/apis/agentsandbox/v1alpha1"
	"github.com/volcano-sh/agentcube/pkg/agentd"
	"github.com/volcano-sh/agentcube/pkg/workloadmanager"
)

func schemeWithSandbox(t *testing.T) *runtime.Scheme {
	t.Helper()
	s := runtime.NewScheme()
	require.NoError(t, agentsandboxv1.AddToScheme(s))
	return s
}

func TestReconciler_DeletesIdleSandbox(t *testing.T) {
	s := schemeWithSandbox(t)
	old := time.Now().Add(-20 * time.Minute).Unix()
	sb := &agentsandboxv1.Sandbox{
		ObjectMeta: metav1.ObjectMeta{
			Name:      "sbx",
			Namespace: "default",
			Annotations: map[string]string{
				workloadmanager.LastActivityAnnotationKey: strconv.FormatInt(old, 10),
			},
		},
	}
	c := fake.NewClientBuilder().WithScheme(s).WithObjects(sb).Build()
	r := &agentd.Reconciler{Client: c, Scheme: s}

	_, err := r.Reconcile(context.Background(), ctrl.Request{NamespacedName: types.NamespacedName{Namespace: "default", Name: "sbx"}})
	require.NoError(t, err)

	var still agentsandboxv1.Sandbox
	err = c.Get(context.Background(), client.ObjectKey{Namespace: "default", Name: "sbx"}, &still)
	assert.True(t, apierrors.IsNotFound(err))
}

func TestReconciler_RequeuesRecentActivity(t *testing.T) {
	s := schemeWithSandbox(t)
	recent := time.Now().Add(-time.Minute).Unix()
	sb := &agentsandboxv1.Sandbox{
		ObjectMeta: metav1.ObjectMeta{
			Name:      "sbx2",
			Namespace: "default",
			Annotations: map[string]string{
				workloadmanager.LastActivityAnnotationKey: strconv.FormatInt(recent, 10),
			},
		},
	}
	c := fake.NewClientBuilder().WithScheme(s).WithObjects(sb).Build()
	r := &agentd.Reconciler{Client: c, Scheme: s}

	res, err := r.Reconcile(context.Background(), ctrl.Request{NamespacedName: types.NamespacedName{Namespace: "default", Name: "sbx2"}})
	require.NoError(t, err)
	assert.Greater(t, res.RequeueAfter, time.Duration(0))

	var still agentsandboxv1.Sandbox
	require.NoError(t, c.Get(context.Background(), client.ObjectKey{Namespace: "default", Name: "sbx2"}, &still))
}

func TestReconciler_MissingAnnotationRequeues(t *testing.T) {
	s := schemeWithSandbox(t)
	sb := &agentsandboxv1.Sandbox{
		ObjectMeta: metav1.ObjectMeta{Name: "sbx3", Namespace: "default"},
	}
	c := fake.NewClientBuilder().WithScheme(s).WithObjects(sb).Build()
	r := &agentd.Reconciler{Client: c, Scheme: s}

	res, err := r.Reconcile(context.Background(), ctrl.Request{NamespacedName: types.NamespacedName{Namespace: "default", Name: "sbx3"}})
	require.NoError(t, err)
	assert.Equal(t, time.Minute, res.RequeueAfter)
}
