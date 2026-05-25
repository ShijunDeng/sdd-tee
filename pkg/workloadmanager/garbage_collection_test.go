/*
Copyright The Volcano Authors.

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
*/

package workloadmanager

import (
	"context"
	"errors"
	"testing"
	"time"

	"github.com/stretchr/testify/require"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/apis/meta/v1/unstructured"
	"k8s.io/apimachinery/pkg/runtime"
	"k8s.io/apimachinery/pkg/runtime/schema"
	dynamicfake "k8s.io/client-go/dynamic/fake"

	"github.com/volcano-sh/agentcube/pkg/common/types"
	"github.com/volcano-sh/agentcube/pkg/store"
)

type mockGCStore struct {
	store.Store
	sessions      map[string]*types.SandboxInfo
	expiredList   []*types.SandboxInfo
	inactiveList  []*types.SandboxInfo
	expiredErr    error
	inactiveErr   error
	deleteErr     error
	deleteCalls   int
	expiredCalls  int
	inactiveCalls int
}

func newMockGCStore() *mockGCStore {
	return &mockGCStore{
		sessions: make(map[string]*types.SandboxInfo),
	}
}

func (m *mockGCStore) Ping(_ context.Context) error { return nil }
func (m *mockGCStore) GetSandboxBySessionID(_ context.Context, _ string) (*types.SandboxInfo, error) {
	return nil, store.ErrNotFound
}
func (m *mockGCStore) StoreSandbox(_ context.Context, _ *types.SandboxInfo) error  { return nil }
func (m *mockGCStore) UpdateSandbox(_ context.Context, _ *types.SandboxInfo) error { return nil }
func (m *mockGCStore) DeleteSandboxBySessionID(_ context.Context, sessionID string) error {
	m.deleteCalls++
	delete(m.sessions, sessionID)
	return m.deleteErr
}
func (m *mockGCStore) ListExpiredSandboxes(_ context.Context, _ time.Time, _ int64) ([]*types.SandboxInfo, error) {
	m.expiredCalls++
	return m.expiredList, m.expiredErr
}
func (m *mockGCStore) ListInactiveSandboxes(_ context.Context, _ time.Time, _ int64) ([]*types.SandboxInfo, error) {
	m.inactiveCalls++
	return m.inactiveList, m.inactiveErr
}
func (m *mockGCStore) UpdateSessionLastActivity(_ context.Context, _ string, _ time.Time) error {
	return nil
}
func (m *mockGCStore) Close() error { return nil }

func createGCTestK8sClient() *K8sClient {
	scheme := runtime.NewScheme()
	dynamicClient := dynamicfake.NewSimpleDynamicClientWithCustomListKinds(scheme,
		map[schema.GroupVersionResource]string{
			SandboxGVR:      "SandboxList",
			SandboxClaimGVR: "SandboxClaimList",
		})
	return &K8sClient{
		dynamicClient: dynamicClient,
	}
}

func TestNewGarbageCollector(t *testing.T) {
	k8sClient := createGCTestK8sClient()
	mockStore := newMockGCStore()
	interval := 15 * time.Second

	gc := newGarbageCollector(k8sClient, mockStore, interval)

	require.NotNil(t, gc)
	require.Equal(t, k8sClient, gc.k8sClient)
	require.Equal(t, mockStore, gc.storeClient)
	require.Equal(t, interval, gc.interval)
}

func TestGarbageCollector_GCInterval(t *testing.T) {
	require.Equal(t, 15*time.Second, DefaultGCInterval)
}

func TestGarbageCollector_DeleteSandbox(t *testing.T) {
	k8sClient := createGCTestK8sClient()
	mockStore := newMockGCStore()
	gc := newGarbageCollector(k8sClient, mockStore, DefaultGCInterval)

	sandbox := &unstructured.Unstructured{}
	sandbox.SetGroupVersionKind(SandboxGVR.GroupVersion().WithKind("Sandbox"))
	sandbox.SetName("test-sandbox")
	sandbox.SetNamespace("default")

	_, err := k8sClient.dynamicClient.Resource(SandboxGVR).Namespace("default").Create(context.Background(), sandbox, metav1.CreateOptions{})
	require.NoError(t, err)

	err = gc.deleteSandbox(context.Background(), "default", "test-sandbox")
	require.NoError(t, err)
}

func TestGarbageCollector_DeleteSandbox_AlreadyDeleted(t *testing.T) {
	k8sClient := createGCTestK8sClient()
	mockStore := newMockGCStore()
	gc := newGarbageCollector(k8sClient, mockStore, DefaultGCInterval)

	err := gc.deleteSandbox(context.Background(), "default", "nonexistent-sandbox")
	require.NoError(t, err)
}

func TestGarbageCollector_DeleteSandboxClaim(t *testing.T) {
	k8sClient := createGCTestK8sClient()
	mockStore := newMockGCStore()
	gc := newGarbageCollector(k8sClient, mockStore, DefaultGCInterval)

	claim := &unstructured.Unstructured{}
	claim.SetGroupVersionKind(SandboxClaimGVR.GroupVersion().WithKind("SandboxClaim"))
	claim.SetName("test-claim")
	claim.SetNamespace("default")

	_, err := k8sClient.dynamicClient.Resource(SandboxClaimGVR).Namespace("default").Create(context.Background(), claim, metav1.CreateOptions{})
	require.NoError(t, err)

	err = gc.deleteSandboxClaim(context.Background(), "default", "test-claim")
	require.NoError(t, err)
}

func TestGarbageCollector_DeleteSandboxClaim_AlreadyDeleted(t *testing.T) {
	k8sClient := createGCTestK8sClient()
	mockStore := newMockGCStore()
	gc := newGarbageCollector(k8sClient, mockStore, DefaultGCInterval)

	err := gc.deleteSandboxClaim(context.Background(), "default", "nonexistent-claim")
	require.NoError(t, err)
}

func TestGarbageCollector_Once_ProcessesExpiredSandboxes(t *testing.T) {
	k8sClient := createGCTestK8sClient()
	mockStore := newMockGCStore()

	sessionID := "expired-session-1"
	info := &types.SandboxInfo{
		SessionID:        sessionID,
		SandboxID:        "expired-sandbox-1",
		Name:             "expired-sandbox-1",
		SandboxNamespace: "default",
		Kind:             types.AgentRuntimeKind,
		CreatedAt:        time.Now().Add(-2 * time.Hour),
		ExpiresAt:        time.Now().Add(-1 * time.Hour),
		LastActivityAt:   time.Now().Add(-1 * time.Hour),
	}
	mockStore.sessions[sessionID] = info
	mockStore.expiredList = []*types.SandboxInfo{info}

	sandbox := &unstructured.Unstructured{}
	sandbox.SetGroupVersionKind(SandboxGVR.GroupVersion().WithKind("Sandbox"))
	sandbox.SetName("expired-sandbox-1")
	sandbox.SetNamespace("default")
	_, err := k8sClient.dynamicClient.Resource(SandboxGVR).Namespace("default").Create(context.Background(), sandbox, metav1.CreateOptions{})
	require.NoError(t, err)

	gc := newGarbageCollector(k8sClient, mockStore, DefaultGCInterval)
	gc.once()

	require.Equal(t, 1, mockStore.expiredCalls)
	require.Equal(t, 1, mockStore.inactiveCalls)
	require.Equal(t, 1, mockStore.deleteCalls)
	require.NotContains(t, mockStore.sessions, sessionID)
}

func TestGarbageCollector_Once_ProcessesInactiveSandboxes(t *testing.T) {
	k8sClient := createGCTestK8sClient()
	mockStore := newMockGCStore()

	sessionID := "inactive-session-1"
	info := &types.SandboxInfo{
		SessionID:        sessionID,
		SandboxID:        "inactive-sandbox-1",
		Name:             "inactive-sandbox-1",
		SandboxNamespace: "default",
		Kind:             types.AgentRuntimeKind,
		CreatedAt:        time.Now().Add(-30 * time.Minute),
		ExpiresAt:        time.Now().Add(8 * time.Hour),
		LastActivityAt:   time.Now().Add(-20 * time.Minute),
	}
	mockStore.sessions[sessionID] = info
	mockStore.inactiveList = []*types.SandboxInfo{info}

	sandbox := &unstructured.Unstructured{}
	sandbox.SetGroupVersionKind(SandboxGVR.GroupVersion().WithKind("Sandbox"))
	sandbox.SetName("inactive-sandbox-1")
	sandbox.SetNamespace("default")
	_, err := k8sClient.dynamicClient.Resource(SandboxGVR).Namespace("default").Create(context.Background(), sandbox, metav1.CreateOptions{})
	require.NoError(t, err)

	gc := newGarbageCollector(k8sClient, mockStore, DefaultGCInterval)
	gc.once()

	require.Equal(t, 1, mockStore.expiredCalls)
	require.Equal(t, 1, mockStore.inactiveCalls)
	require.Equal(t, 1, mockStore.deleteCalls)
	require.NotContains(t, mockStore.sessions, sessionID)
}

func TestGarbageCollector_Once_ProcessesSandboxClaims(t *testing.T) {
	k8sClient := createGCTestK8sClient()
	mockStore := newMockGCStore()

	sessionID := "expired-claim-session-1"
	info := &types.SandboxInfo{
		SessionID:        sessionID,
		SandboxID:        "expired-claim-1",
		Name:             "expired-claim-1",
		SandboxNamespace: "default",
		Kind:             types.SandboxClaimsKind,
		CreatedAt:        time.Now().Add(-2 * time.Hour),
		ExpiresAt:        time.Now().Add(-1 * time.Hour),
		LastActivityAt:   time.Now().Add(-1 * time.Hour),
	}
	mockStore.sessions[sessionID] = info
	mockStore.expiredList = []*types.SandboxInfo{info}

	claim := &unstructured.Unstructured{}
	claim.SetGroupVersionKind(SandboxClaimGVR.GroupVersion().WithKind("SandboxClaim"))
	claim.SetName("expired-claim-1")
	claim.SetNamespace("default")
	_, err := k8sClient.dynamicClient.Resource(SandboxClaimGVR).Namespace("default").Create(context.Background(), claim, metav1.CreateOptions{})
	require.NoError(t, err)

	gc := newGarbageCollector(k8sClient, mockStore, DefaultGCInterval)
	gc.once()

	require.Equal(t, 1, mockStore.expiredCalls)
	require.Equal(t, 1, mockStore.inactiveCalls)
	require.Equal(t, 1, mockStore.deleteCalls)
	require.NotContains(t, mockStore.sessions, sessionID)
}

func TestGarbageCollector_Once_MergesLists(t *testing.T) {
	k8sClient := createGCTestK8sClient()
	mockStore := newMockGCStore()

	expiredSessionID := "expired-session"
	inactiveSessionID := "inactive-session"

	expiredInfo := &types.SandboxInfo{
		SessionID:        expiredSessionID,
		SandboxID:        "expired-sandbox",
		Name:             "expired-sandbox",
		SandboxNamespace: "default",
		Kind:             types.AgentRuntimeKind,
		CreatedAt:        time.Now().Add(-2 * time.Hour),
		ExpiresAt:        time.Now().Add(-1 * time.Hour),
		LastActivityAt:   time.Now().Add(-1 * time.Hour),
	}

	inactiveInfo := &types.SandboxInfo{
		SessionID:        inactiveSessionID,
		SandboxID:        "inactive-sandbox",
		Name:             "inactive-sandbox",
		SandboxNamespace: "default",
		Kind:             types.AgentRuntimeKind,
		CreatedAt:        time.Now().Add(-30 * time.Minute),
		ExpiresAt:        time.Now().Add(8 * time.Hour),
		LastActivityAt:   time.Now().Add(-20 * time.Minute),
	}

	mockStore.sessions[expiredSessionID] = expiredInfo
	mockStore.sessions[inactiveSessionID] = inactiveInfo
	mockStore.expiredList = []*types.SandboxInfo{expiredInfo}
	mockStore.inactiveList = []*types.SandboxInfo{inactiveInfo}

	sandbox1 := &unstructured.Unstructured{}
	sandbox1.SetGroupVersionKind(SandboxGVR.GroupVersion().WithKind("Sandbox"))
	sandbox1.SetName("expired-sandbox")
	sandbox1.SetNamespace("default")
	_, err := k8sClient.dynamicClient.Resource(SandboxGVR).Namespace("default").Create(context.Background(), sandbox1, metav1.CreateOptions{})
	require.NoError(t, err)

	sandbox2 := &unstructured.Unstructured{}
	sandbox2.SetGroupVersionKind(SandboxGVR.GroupVersion().WithKind("Sandbox"))
	sandbox2.SetName("inactive-sandbox")
	sandbox2.SetNamespace("default")
	_, err = k8sClient.dynamicClient.Resource(SandboxGVR).Namespace("default").Create(context.Background(), sandbox2, metav1.CreateOptions{})
	require.NoError(t, err)

	gc := newGarbageCollector(k8sClient, mockStore, DefaultGCInterval)
	gc.once()

	require.Equal(t, 1, mockStore.expiredCalls)
	require.Equal(t, 1, mockStore.inactiveCalls)
	require.Equal(t, 2, mockStore.deleteCalls)
	require.NotContains(t, mockStore.sessions, expiredSessionID)
	require.NotContains(t, mockStore.sessions, inactiveSessionID)
}

func TestGarbageCollector_Once_TreatsK8sNotFoundAsSuccess(t *testing.T) {
	k8sClient := createGCTestK8sClient()
	mockStore := newMockGCStore()

	sessionID := "gc-notfound-session"
	info := &types.SandboxInfo{
		SessionID:        sessionID,
		SandboxID:        "gc-notfound-sandbox",
		Name:             "gc-notfound-sandbox",
		SandboxNamespace: "default",
		Kind:             types.AgentRuntimeKind,
		CreatedAt:        time.Now().Add(-2 * time.Hour),
		ExpiresAt:        time.Now().Add(-1 * time.Hour),
		LastActivityAt:   time.Now().Add(-1 * time.Hour),
	}
	mockStore.sessions[sessionID] = info
	mockStore.expiredList = []*types.SandboxInfo{info}

	gc := newGarbageCollector(k8sClient, mockStore, DefaultGCInterval)
	gc.once()

	require.Equal(t, 1, mockStore.deleteCalls)
	require.NotContains(t, mockStore.sessions, sessionID)
}

func TestGarbageCollector_Once_ContinuesOnError(t *testing.T) {
	k8sClient := createGCTestK8sClient()
	mockStore := newMockGCStore()

	sessionID1 := "session-1"
	sessionID2 := "session-2"

	info1 := &types.SandboxInfo{
		SessionID:        sessionID1,
		SandboxID:        "sandbox-1",
		Name:             "sandbox-1",
		SandboxNamespace: "default",
		Kind:             types.AgentRuntimeKind,
		CreatedAt:        time.Now().Add(-2 * time.Hour),
		ExpiresAt:        time.Now().Add(-1 * time.Hour),
		LastActivityAt:   time.Now().Add(-1 * time.Hour),
	}

	info2 := &types.SandboxInfo{
		SessionID:        sessionID2,
		SandboxID:        "sandbox-2",
		Name:             "sandbox-2",
		SandboxNamespace: "default",
		Kind:             types.AgentRuntimeKind,
		CreatedAt:        time.Now().Add(-2 * time.Hour),
		ExpiresAt:        time.Now().Add(-1 * time.Hour),
		LastActivityAt:   time.Now().Add(-1 * time.Hour),
	}

	mockStore.sessions[sessionID1] = info1
	mockStore.sessions[sessionID2] = info2
	mockStore.expiredList = []*types.SandboxInfo{info1, info2}
	mockStore.deleteErr = errors.New("delete error")

	gc := newGarbageCollector(k8sClient, mockStore, DefaultGCInterval)
	gc.once()

	require.Equal(t, 2, mockStore.deleteCalls)
}

func TestGarbageCollector_Run_StopsOnStopCh(t *testing.T) {
	k8sClient := createGCTestK8sClient()
	mockStore := newMockGCStore()
	gc := newGarbageCollector(k8sClient, mockStore, DefaultGCInterval)

	stopCh := make(chan struct{})
	done := make(chan struct{})

	go func() {
		gc.run(stopCh)
		close(done)
	}()

	time.Sleep(50 * time.Millisecond)
	close(stopCh)

	select {
	case <-done:
	case <-time.After(1 * time.Second):
		t.Fatal("garbage collector did not stop")
	}
}

func TestGarbageCollector_DefaultSandboxIdleTimeout(t *testing.T) {
	require.Equal(t, 15*time.Minute, DefaultSandboxIdleTimeout)
}

func TestGarbageCollector_GCOnceTimeout(t *testing.T) {
	require.Equal(t, 2*time.Minute, gcOnceTimeout)
}
