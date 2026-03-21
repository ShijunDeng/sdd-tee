package picod

import (
	"bytes"
	"crypto/rand"
	"crypto/rsa"
	"crypto/x509"
	"encoding/json"
	"encoding/pem"
	"mime/multipart"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/golang-jwt/jwt/v5"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func rsaPEMKeys(t *testing.T) (priv *rsa.PrivateKey, pubPEM string) {
	t.Helper()
	priv, err := rsa.GenerateKey(rand.Reader, 2048)
	require.NoError(t, err)
	pubDER, err := x509.MarshalPKIXPublicKey(&priv.PublicKey)
	require.NoError(t, err)
	pubPEM = string(pem.EncodeToMemory(&pem.Block{Type: "PUBLIC KEY", Bytes: pubDER}))
	return priv, pubPEM
}

func signSessionToken(t *testing.T, priv *rsa.PrivateKey, sub string) string {
	t.Helper()
	tok, err := jwt.NewWithClaims(jwt.SigningMethodRS256, jwt.RegisteredClaims{
		Subject:   sub,
		ExpiresAt: jwt.NewNumericDate(time.Now().Add(5 * time.Minute)),
	}).SignedString(priv)
	require.NoError(t, err)
	return tok
}

func TestHealthEndpoint(t *testing.T) {
	_, pub := rsaPEMKeys(t)
	t.Setenv("PICOD_AUTH_PUBLIC_KEY", pub)
	dir := t.TempDir()
	srv, err := NewServer(Config{Port: 18090, Workspace: dir})
	require.NoError(t, err)

	w := httptest.NewRecorder()
	srv.engine.ServeHTTP(w, httptest.NewRequest(http.MethodGet, "/health", nil))
	assert.Equal(t, http.StatusOK, w.Code)
	assert.Equal(t, "ok", w.Body.String())
}

func TestExecute(t *testing.T) {
	priv, pub := rsaPEMKeys(t)
	t.Setenv("PICOD_AUTH_PUBLIC_KEY", pub)
	dir := t.TempDir()
	srv, err := NewServer(Config{Port: 18091, Workspace: dir})
	require.NoError(t, err)

	body := map[string]any{"command": []string{"sh", "-c", "echo hi"}}
	b, _ := json.Marshal(body)
	req := httptest.NewRequest(http.MethodPost, "/api/execute", bytes.NewReader(b))
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Authorization", "Bearer "+signSessionToken(t, priv, "s1"))
	w := httptest.NewRecorder()
	srv.engine.ServeHTTP(w, req)
	require.Equal(t, http.StatusOK, w.Code)
	var resp ExecuteResponse
	require.NoError(t, json.Unmarshal(w.Body.Bytes(), &resp))
	assert.Equal(t, 0, resp.ExitCode)
	assert.Contains(t, resp.Stdout, "hi")
}

func TestFileOperations(t *testing.T) {
	priv, pub := rsaPEMKeys(t)
	t.Setenv("PICOD_AUTH_PUBLIC_KEY", pub)
	dir := t.TempDir()
	srv, err := NewServer(Config{Port: 18092, Workspace: dir})
	require.NoError(t, err)
	auth := "Bearer " + signSessionToken(t, priv, "s2")

	var buf bytes.Buffer
	mw := multipart.NewWriter(&buf)
	require.NoError(t, mw.WriteField("path", "notes.txt"))
	fw, err := mw.CreateFormFile("file", "notes.txt")
	require.NoError(t, err)
	_, err = fw.Write([]byte("hello-files"))
	require.NoError(t, err)
	require.NoError(t, mw.Close())

	up := httptest.NewRequest(http.MethodPost, "/api/files", &buf)
	up.Header.Set("Content-Type", mw.FormDataContentType())
	up.Header.Set("Authorization", auth)
	wUp := httptest.NewRecorder()
	srv.engine.ServeHTTP(wUp, up)
	require.Equal(t, http.StatusOK, wUp.Code)

	listReq := httptest.NewRequest(http.MethodGet, "/api/files", nil)
	listReq.Header.Set("Authorization", auth)
	wList := httptest.NewRecorder()
	srv.engine.ServeHTTP(wList, listReq)
	require.Equal(t, http.StatusOK, wList.Code)
	var listed []FileInfo
	require.NoError(t, json.Unmarshal(wList.Body.Bytes(), &listed))
	names := make([]string, 0, len(listed))
	for _, fi := range listed {
		names = append(names, fi.Name)
	}
	assert.Contains(t, names, "notes.txt")

	getReq := httptest.NewRequest(http.MethodGet, "/api/files/notes.txt", nil)
	getReq.Header.Set("Authorization", auth)
	wGet := httptest.NewRecorder()
	srv.engine.ServeHTTP(wGet, getReq)
	require.Equal(t, http.StatusOK, wGet.Code)
	assert.Contains(t, wGet.Body.String(), "hello-files")

	miss := httptest.NewRequest(http.MethodGet, "/api/files/nope.txt", nil)
	miss.Header.Set("Authorization", auth)
	wMiss := httptest.NewRecorder()
	srv.engine.ServeHTTP(wMiss, miss)
	assert.Equal(t, http.StatusNotFound, wMiss.Code)
}
