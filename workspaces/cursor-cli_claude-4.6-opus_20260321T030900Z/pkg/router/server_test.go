package router

import (
	"context"
	"net/http"
	"net/http/httptest"
	"net/url"
	"strconv"
	"testing"
	"time"

	"github.com/google/uuid"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"

	"github.com/volcano-sh/agentcube/pkg/store"
)

// reverseProxy + Gin may type-assert http.CloseNotify on the ResponseWriter; httptest.ResponseRecorder does not implement it.
type recorderWithCloseNotify struct {
	*httptest.ResponseRecorder
}

func (r *recorderWithCloseNotify) CloseNotify() <-chan bool {
	ch := make(chan bool)
	return ch
}

func TestHealthEndpoints(t *testing.T) {
	st := newStubStore()
	srv, err := NewServer(Config{Port: 18080, Debug: false, MaxConcurrentRequests: 8}, st, nil)
	require.NoError(t, err)

	w := httptest.NewRecorder()
	srv.engine.ServeHTTP(w, httptest.NewRequest(http.MethodGet, "/health/live", nil))
	assert.Equal(t, http.StatusOK, w.Code)

	w2 := httptest.NewRecorder()
	srv.engine.ServeHTTP(w2, httptest.NewRequest(http.MethodGet, "/health/ready", nil))
	assert.Equal(t, http.StatusOK, w2.Code)
}

func TestInvokeRouting(t *testing.T) {
	be := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		assert.Equal(t, "/hello", r.URL.Path)
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte("pong"))
	}))
	t.Cleanup(be.Close)

	u, err := url.Parse(be.URL)
	require.NoError(t, err)
	port, err := strconv.Atoi(u.Port())
	require.NoError(t, err)

	st := newStubStore()
	sid := uuid.NewString()
	require.NoError(t, st.StoreSandbox(context.Background(), &store.Sandbox{
		SessionID:     sid,
		Namespace:     "default",
		ResourceName:  "my-ar",
		ResourceKind:  "agent-runtime",
		PodIP:         "127.0.0.1",
		UpstreamPort:  port,
		ExpiresAt:     time.Now().Unix() + 1000,
		CreatedAt:     time.Now().Unix(),
		LastActivity:  time.Now().Unix(),
	}))

	srv, err := NewServer(Config{Port: 18080, Debug: false, MaxConcurrentRequests: 8}, st, nil)
	require.NoError(t, err)

	req := httptest.NewRequest(http.MethodGet, "/v1/namespaces/default/agent-runtimes/my-ar/invocations/hello", nil)
	req.Header.Set(SessionHeader(), sid)
	w := &recorderWithCloseNotify{ResponseRecorder: httptest.NewRecorder()}
	srv.engine.ServeHTTP(w, req)
	assert.Equal(t, http.StatusOK, w.Code)
	assert.Equal(t, "pong", w.Body.String())
}

func TestConcurrencyLimit(t *testing.T) {
	ready := make(chan struct{})
	release := make(chan struct{})
	be := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		close(ready)
		<-release
		w.WriteHeader(http.StatusOK)
	}))
	t.Cleanup(be.Close)

	u, err := url.Parse(be.URL)
	require.NoError(t, err)
	port, err := strconv.Atoi(u.Port())
	require.NoError(t, err)

	st := newStubStore()
	sid := uuid.NewString()
	require.NoError(t, st.StoreSandbox(context.Background(), &store.Sandbox{
		SessionID:     sid,
		Namespace:     "ns",
		ResourceName:  "x",
		ResourceKind:  "agent-runtime",
		PodIP:         "127.0.0.1",
		UpstreamPort:  port,
		ExpiresAt:     time.Now().Unix() + 1000,
		CreatedAt:     time.Now().Unix(),
		LastActivity:  time.Now().Unix(),
	}))

	srv, err := NewServer(Config{Port: 18081, Debug: false, MaxConcurrentRequests: 1}, st, nil)
	require.NoError(t, err)

	done := make(chan struct{})
	go func() {
		req := httptest.NewRequest(http.MethodGet, "/v1/namespaces/ns/agent-runtimes/x/invocations/wait", nil)
		req.Header.Set(SessionHeader(), sid)
		w := &recorderWithCloseNotify{ResponseRecorder: httptest.NewRecorder()}
		srv.engine.ServeHTTP(w, req)
		close(done)
	}()

	select {
	case <-ready:
	case <-time.After(3 * time.Second):
		t.Fatal("backend handler did not start")
	}

	req2 := httptest.NewRequest(http.MethodGet, "/v1/namespaces/ns/agent-runtimes/x/invocations/other", nil)
	req2.Header.Set(SessionHeader(), sid)
	w2 := &recorderWithCloseNotify{ResponseRecorder: httptest.NewRecorder()}
	srv.engine.ServeHTTP(w2, req2)
	assert.Equal(t, http.StatusTooManyRequests, w2.Code)

	close(release)
	select {
	case <-done:
	case <-time.After(3 * time.Second):
		t.Fatal("first request did not finish")
	}
}
