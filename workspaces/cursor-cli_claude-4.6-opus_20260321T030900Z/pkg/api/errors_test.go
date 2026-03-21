package api_test

import (
	"errors"
	"net/http"
	"testing"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
	apierrors "k8s.io/apimachinery/pkg/api/errors"

	"github.com/volcano-sh/agentcube/pkg/api"
)

func TestNewSessionNotFoundError(t *testing.T) {
	err := api.NewSessionNotFoundError("sess-1")
	var st *apierrors.StatusError
	require.True(t, errors.As(err, &st))
	assert.Equal(t, http.StatusNotFound, int(st.Status().Code))
	assert.Contains(t, st.Error(), "sess-1")
}

func TestNewSandboxTemplateNotFoundError(t *testing.T) {
	err := api.NewSandboxTemplateNotFoundError("tpl-a")
	var st *apierrors.StatusError
	require.True(t, errors.As(err, &st))
	assert.Equal(t, http.StatusNotFound, int(st.Status().Code))
}

func TestNewInternalError(t *testing.T) {
	inner := errors.New("boom")
	err := api.NewInternalError(inner)
	var st *apierrors.StatusError
	require.True(t, errors.As(err, &st))
	assert.Equal(t, http.StatusInternalServerError, int(st.Status().Code))
}

func TestNewUpstreamUnavailableError(t *testing.T) {
	err := api.NewUpstreamUnavailableError("redis down")
	require.NotNil(t, err)
	assert.Equal(t, http.StatusServiceUnavailable, int(err.Status().Code))
	assert.Contains(t, err.Error(), "redis down")
}

func TestSentinelErrors(t *testing.T) {
	assert.ErrorIs(t, api.ErrAgentRuntimeNotFound, api.ErrAgentRuntimeNotFound)
	assert.ErrorIs(t, api.ErrCodeInterpreterNotFound, api.ErrCodeInterpreterNotFound)
}
