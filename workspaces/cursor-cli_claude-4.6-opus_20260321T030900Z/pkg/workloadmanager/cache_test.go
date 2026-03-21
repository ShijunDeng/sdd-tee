package workloadmanager_test

import (
	"testing"
	"time"

	"github.com/golang-jwt/jwt/v5"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
	"k8s.io/client-go/rest"

	"github.com/volcano-sh/agentcube/pkg/workloadmanager"
)

func TestTokenCacheHitMiss(t *testing.T) {
	c, err := workloadmanager.NewTokenCache()
	require.NoError(t, err)

	ok, hit := c.Get("tok-a")
	assert.False(t, ok)
	assert.False(t, hit)

	c.Put("tok-a", true)
	ok, hit = c.Get("tok-a")
	assert.True(t, ok)
	assert.True(t, hit)

	c.Put("tok-b", false)
	ok, hit = c.Get("tok-b")
	assert.False(t, ok)
	assert.True(t, hit)
}

func TestTokenCacheNilSafe(t *testing.T) {
	var c *workloadmanager.TokenCache
	ok, hit := c.Get("x")
	assert.False(t, ok)
	assert.False(t, hit)
	c.Put("x", true) // no panic
}

func TestClientCacheReturnsSameClient(t *testing.T) {
	cc, err := workloadmanager.NewClientCache()
	require.NoError(t, err)

	exp := time.Now().Add(time.Hour)
	tok, err := jwt.NewWithClaims(jwt.SigningMethodHS256, jwt.RegisteredClaims{
		ExpiresAt: jwt.NewNumericDate(exp),
	}).SignedString([]byte("secret"))
	require.NoError(t, err)

	cfg := &rest.Config{Host: "https://127.0.0.1:6443"}
	c1, err := cc.ClientForToken(cfg, tok)
	require.NoError(t, err)
	c2, err := cc.ClientForToken(cfg, tok)
	require.NoError(t, err)
	assert.Same(t, c1, c2)
}

func TestClientCacheNilBaseConfig(t *testing.T) {
	cc, err := workloadmanager.NewClientCache()
	require.NoError(t, err)
	_, err = cc.ClientForToken(nil, "any")
	require.Error(t, err)
}
