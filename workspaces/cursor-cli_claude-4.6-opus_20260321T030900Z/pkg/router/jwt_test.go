package router

import (
	"crypto/rand"
	"crypto/rsa"
	"testing"

	"github.com/golang-jwt/jwt/v5"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func TestGenerateAndParseToken(t *testing.T) {
	priv, err := rsa.GenerateKey(rand.Reader, 2048)
	require.NoError(t, err)
	m := &JWTManager{}
	m.id = &Identity{PrivateKey: priv, PublicKey: &priv.PublicKey}

	raw, err := m.GenerateToken("session-abc")
	require.NoError(t, err)

	parsed, err := jwt.ParseWithClaims(raw, &jwt.RegisteredClaims{}, func(t *jwt.Token) (interface{}, error) {
		return priv.Public(), nil
	})
	require.NoError(t, err)
	require.True(t, parsed.Valid)

	claims, ok := parsed.Claims.(*jwt.RegisteredClaims)
	require.True(t, ok)
	assert.Equal(t, "session-abc", claims.Subject)
	assert.Equal(t, issuer, claims.Issuer)
}

func TestTokenExpiry(t *testing.T) {
	priv, err := rsa.GenerateKey(rand.Reader, 2048)
	require.NoError(t, err)
	m := &JWTManager{}
	m.id = &Identity{PrivateKey: priv, PublicKey: &priv.PublicKey}

	raw, err := m.GenerateToken("sess-exp")
	require.NoError(t, err)

	parsed, err := jwt.ParseWithClaims(raw, &jwt.RegisteredClaims{}, func(t *jwt.Token) (interface{}, error) {
		return priv.Public(), nil
	})
	require.NoError(t, err)
	claims := parsed.Claims.(*jwt.RegisteredClaims)
	require.NotNil(t, claims.ExpiresAt)
	require.NotNil(t, claims.IssuedAt)

	ttl := claims.ExpiresAt.Sub(claims.IssuedAt.Time)
	assert.InDelta(t, tokenTTL.Seconds(), ttl.Seconds(), 1.0)
}

func TestGenerateTokenRequiresIdentity(t *testing.T) {
	m := &JWTManager{}
	_, err := m.GenerateToken("x")
	require.Error(t, err)
	assert.Contains(t, err.Error(), "identity not loaded")
}
