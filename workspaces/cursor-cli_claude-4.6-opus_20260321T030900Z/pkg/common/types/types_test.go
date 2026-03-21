package types_test

import (
	"encoding/json"
	"testing"
	"time"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"

	"github.com/volcano-sh/agentcube/pkg/common/types"
)

func TestCreateSandboxRequestValidate(t *testing.T) {
	tests := []struct {
		name    string
		req     *types.CreateSandboxRequest
		wantErr string
	}{
		{name: "nil", req: nil, wantErr: "request is nil"},
		{name: "missing name", req: &types.CreateSandboxRequest{Namespace: "n", Kind: types.AgentRuntimeKind}, wantErr: "name"},
		{name: "missing namespace", req: &types.CreateSandboxRequest{Name: "x", Kind: types.AgentRuntimeKind}, wantErr: "namespace"},
		{name: "missing kind", req: &types.CreateSandboxRequest{Name: "x", Namespace: "n"}, wantErr: "kind"},
		{name: "ok", req: &types.CreateSandboxRequest{Name: "x", Namespace: "n", Kind: types.AgentRuntimeKind}, wantErr: ""},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			err := tt.req.Validate()
			if tt.wantErr == "" {
				require.NoError(t, err)
				return
			}
			require.Error(t, err)
			assert.Contains(t, err.Error(), tt.wantErr)
		})
	}
}

func TestSandboxInfoJSON(t *testing.T) {
	now := time.Date(2026, 3, 21, 12, 0, 0, 0, time.UTC)
	info := types.SandboxInfo{
		SessionID: "sid",
		Name:      "n",
		Namespace: "ns",
		Kind:      types.AgentRuntimeKind,
		PodIP:     "10.0.0.5",
		EntryPoints: []types.SandboxEntryPoint{
			{PathPrefix: "/api", Name: "main", Port: 8080, Protocol: "HTTP"},
		},
		CreatedAt:    now,
		ExpiresAt:    now.Add(time.Hour),
		LastActivity: now,
	}
	b, err := json.Marshal(&info)
	require.NoError(t, err)
	var out types.SandboxInfo
	require.NoError(t, json.Unmarshal(b, &out))
	assert.Equal(t, info.SessionID, out.SessionID)
	assert.Equal(t, info.PodIP, out.PodIP)
	assert.Len(t, out.EntryPoints, 1)
	assert.Equal(t, uint32(8080), out.EntryPoints[0].Port)
}

func TestSandboxEntryPointOmitempty(t *testing.T) {
	ep := types.SandboxEntryPoint{Name: "x", Port: 1, PathPrefix: "/"}
	b, err := json.Marshal(ep)
	require.NoError(t, err)
	assert.NotContains(t, string(b), `"url"`)
}
