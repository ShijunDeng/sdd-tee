# Code Execution (PicoD) — Design (from source)

Derived from `github.com/volcano-sh/agentcube/pkg/picod` and `cmd/picod` in `/tmp/agentcube-ref`. Field names, types, tags, and constants match the Go definitions.

## Packages and entrypoint

- **Main**: `cmd/picod/main.go` — parses flags, constructs `picod.Config`, `picod.NewServer(config)`, `server.Run()`.

## CLI flags and defaults

| Flag        | Type   | Default | Usage string |
|------------|--------|---------|--------------|
| `-port`    | `int`  | `8080`  | `Port for the PicoD server to listen on` |
| `-workspace` | `string` | `""` | `Root directory for file operations (default: current working directory)` |

`klog.InitFlags(nil)` is called so standard klog flags are also registered.

## Environment variables

| Name | Constant | Usage |
|------|----------|--------|
| `PICOD_AUTH_PUBLIC_KEY` | `PublicKeyEnvVar` | PEM-encoded PKIX public key (`PUBLIC KEY` block). Loaded in `NewServer` via `AuthManager.LoadPublicKeyFromEnv()`. If empty, invalid PEM, or not `*rsa.PublicKey`, `LoadPublicKeyFromEnv` returns an error and `NewServer` calls `klog.Fatalf` — **no serve without a valid key**. |

## Server configuration struct

```go
type Config struct {
	Port      int    `json:"port"`
	Workspace string `json:"workspace"`
}
```

## Internal server fields (`Server`)

- `engine *gin.Engine`
- `config Config`
- `authManager *AuthManager`
- `startTime time.Time` — set to `time.Now()` in `NewServer`
- `workspaceDir string` — absolute workspace root after `setWorkspace`

### Workspace resolution

- If `config.Workspace != ""`: `setWorkspace(config.Workspace)` → `filepath.Abs` when possible, else fallback to provided string.
- Else: `os.Getwd()` (fatal on error).

## Constants

| Name | Value | File | Meaning |
|------|-------|------|---------|
| `TimeoutExitCode` | `124` | `execute.go` | Exit code when context deadline exceeded |
| `MaxBodySize` | `32 << 20` (32 MiB) | `auth.go` | `http.MaxBytesReader` cap applied after successful JWT check |
| `PublicKeyEnvVar` | `"PICOD_AUTH_PUBLIC_KEY"` | `auth.go` | Env var for PEM public key |
| `maxFileMode` | `0777` | `files.go` | `parseFileMode` rejects modes `> 0777` (falls back to `0644`) |

### Default timeouts and modes

- **Execute default timeout** (when `ExecuteRequest.Timeout == ""`): `60 * time.Second` (note: struct comment in source says `"30s"` but code uses 60s).
- **Directory creation** (`MkdirAll`): `0755`
- **Default file mode** (`parseFileMode` empty/invalid/too large): `0644` (octal parsed with `strconv.ParseUint(modeStr, 8, 32)`)

## Request / response structs (exact JSON tags)

### Execute

```go
type ExecuteRequest struct {
	Command    []string          `json:"command" binding:"required"`
	Timeout    string            `json:"timeout"`
	WorkingDir string            `json:"working_dir"`
	Env        map[string]string `json:"env"`
}

type ExecuteResponse struct {
	Stdout    string    `json:"stdout"`
	Stderr    string    `json:"stderr"`
	ExitCode  int       `json:"exit_code"`
	Duration  float64   `json:"duration"`
	StartTime time.Time `json:"start_time"`
	EndTime   time.Time `json:"end_time"`
}
```

- **Binding**: `c.ShouldBindJSON(&req)` on `POST /api/execute`.
- **Command**: `exec.CommandContext(ctx, req.Command[0], req.Command[1:]...)`
- **Stdout/Stderr**: `bytes.Buffer` assigned to `cmd.Stdout` and `cmd.Stderr`; no `cmd.Stdin` assignment.
- **Exit code**: If `errors.Is(ctx.Err(), context.DeadlineExceeded)` → `TimeoutExitCode`; else if `cmd.ProcessState != nil` → `ExitCode()`; else `1` and append `err.Error()` to stderr (with newline if stderr non-empty).

### Files — upload response / JSON body

```go
type FileInfo struct {
	Path     string    `json:"path"`
	Size     int64     `json:"size"`
	Mode     string    `json:"mode"`
	Modified time.Time `json:"modified"`
}

type UploadFileRequest struct {
	Path    string `json:"path" binding:"required"`
	Content string `json:"content" binding:"required"`
	Mode    string `json:"mode"`
}
```

- **Multipart**: `Content-Type` prefix `multipart/form-data` → `handleMultipartUpload`.
  - Form: `c.PostForm("path")`, `c.FormFile("file")`, optional `c.PostForm("mode")`.
- **JSON**: `c.ShouldBindJSON` → Base64 decode `req.Content` with `base64.StdEncoding`.

### Files — listing

```go
type FileEntry struct {
	Name     string    `json:"name"`
	Size     int64     `json:"size"`
	Modified time.Time `json:"modified"`
	Mode     string    `json:"mode"`
	IsDir    bool      `json:"is_dir"`
}

type ListFilesResponse struct {
	Files []FileEntry `json:"files"`
}
```

- **Query**: `path := c.Query("path")` (required non-empty).

## HTTP error JSON shapes (Gin `gin.H`)

- **Generic** (400/500): `{"error": string, "code": int}` (`code` is numeric HTTP status).
- **Auth** (401): `{"error": string, "code": int, "detail": string}`.

## Gin setup and route registration

Pattern from `NewServer`:

1. `gin.SetMode(gin.ReleaseMode)`
2. `engine := gin.New()`
3. Global: `engine.Use(gin.Logger(), gin.Recovery())`
4. `authManager.LoadPublicKeyFromEnv()` — fatal on error
5. API group:

```go
api := engine.Group("/api")
api.Use(s.authManager.AuthMiddleware())
{
	api.POST("/execute", s.ExecuteHandler)
	api.POST("/files", s.UploadFileHandler)
	api.GET("/files", s.ListFilesHandler)
	api.GET("/files/*path", s.DownloadFileHandler)
}
engine.GET("/health", s.HealthCheckHandler)
```

- **Download param**: `path := c.Param("path")`; then `strings.TrimPrefix(path, "/")` before `sanitizePath`.

## Health response

```go
c.JSON(http.StatusOK, gin.H{
	"status":  "ok",
	"service": "PicoD",
	"version": "0.0.1",
	"uptime":  time.Since(s.startTime).String(),
})
```

## HTTP server

```go
server := &http.Server{
	Addr:              fmt.Sprintf(":%d", s.config.Port),
	Handler:           s.engine,
	ReadHeaderTimeout: 10 * time.Second,
}
return server.ListenAndServe()
```

## JWT middleware (`AuthManager`)

### Types

```go
type AuthManager struct {
	publicKey *rsa.PublicKey
	mutex     sync.RWMutex
}
```

### Key loading (`LoadPublicKeyFromEnv`)

1. `keyData := os.Getenv(PublicKeyEnvVar)`
2. If empty → error: `environment variable %s is not set`
3. `pem.Decode([]byte(keyData))` — nil block → error `failed to decode PEM block`
4. `x509.ParsePKIXPublicKey(block.Bytes)` — on success assert `*rsa.PublicKey`

### `AuthMiddleware` behavior

1. `authHeader := c.GetHeader("Authorization")`
2. If empty → 401 JSON missing header / JWT required detail
3. `parts := strings.Split(authHeader, " ")` — require `len(parts) == 2` and `parts[0] == "Bearer"` else 401 invalid format (`Use Bearer <token>`)
4. `tokenString := parts[1]`
5. `jwt.Parse(tokenString, func(token *jwt.Token) (interface{}, error) { ... }, jwt.WithExpirationRequired(), jwt.WithIssuedAt(), jwt.WithLeeway(time.Minute))`
   - Key func: require `token.Method` is `*jwt.SigningMethodRSA`; return `am.publicKey` (read lock)
6. If `err != nil || !token.Valid` → 401 `Invalid token` + detail with verification error
7. `c.Request.Body = http.MaxBytesReader(c.Writer, c.Request.Body, MaxBodySize)`
8. `c.Next()`

**Note**: Any RSA signing method instance satisfies the type assert (e.g. RS256 in tests); HS256 is rejected.

## Path security (`sanitizePath`)

Used by upload, list, download, and execute `working_dir`.

1. If `s.workspaceDir == ""` → error `workspace directory not initialized`
2. `resolvedWorkspace := filepath.EvalSymlinks(s.workspaceDir)`; on error fall back to `filepath.Abs` or `filepath.Clean`
3. `resolvedWorkspace = filepath.Clean(resolvedWorkspace)`
4. `cleanPath := filepath.Clean(p)`; if absolute, strip leading `os.PathSeparator` from path string
5. `fullPathCandidate := filepath.Clean(filepath.Join(resolvedWorkspace, cleanPath))`
6. `relPath, relErr := filepath.Rel(resolvedWorkspace, fullPathCandidate)` — error → access denied
7. If `strings.HasPrefix(relPath, ".."+separator)` or `relPath == ".."` → access denied
8. `resolvedFinalPath, err := filepath.EvalSymlinks(fullPathCandidate)`:
   - If success: re-check `filepath.Rel` against `resolvedWorkspace` for `..` escape; pass → return `resolvedFinalPath`
   - If error (e.g. path does not exist): return `fullPathCandidate` (already verified as inside workspace)

**Upload/list responses** use `filepath.Rel(s.workspaceDir, safePath)` for JSON `path` on uploaded files (not `resolvedWorkspace` symlink expansion — `safePath` is the sanitized target path).

## Multipart vs JSON detection

```go
contentType := c.ContentType()
if strings.HasPrefix(contentType, "multipart/form-data") {
	s.handleMultipartUpload(c)
} else {
	s.handleJSONBase64Upload(c)
}
```

## File download headers (exact strings)

- `Content-Description`: `File Transfer`
- `Content-Transfer-Encoding`: `binary`
- `Content-Disposition`: `fmt.Sprintf("attachment; filename=\"%s\"", filepath.Base(safePath))`
- `Content-Type`: `mime.TypeByExtension(filepath.Ext(safePath))` or `"application/octet-stream"`

This document is sufficient to reconstruct handlers, routes, structs, and security checks without reading the repo.
