package picod

import (
	"context"
	"crypto/rsa"
	"crypto/x509"
	"encoding/pem"
	"errors"
	"fmt"
	"io"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/golang-jwt/jwt/v5"
	"k8s.io/klog/v2"
)

// TimeoutExitCode is returned when a command exceeds its deadline (same as GNU timeout).
const TimeoutExitCode = 124

const defaultExecuteTimeout = 60 * time.Second

// ExecuteRequest is the JSON body for /api/execute.
type ExecuteRequest struct {
	Command []string `json:"command"`
	Timeout string   `json:"timeout,omitempty"`
	Cwd     string   `json:"cwd,omitempty"`
}

// ExecuteResponse reports stdout/stderr and exit metadata.
type ExecuteResponse struct {
	Stdout   string `json:"stdout"`
	Stderr   string `json:"stderr"`
	ExitCode int    `json:"exitCode"`
	TimedOut bool   `json:"timedOut,omitempty"`
}

// FileInfo describes a workspace file for listings.
type FileInfo struct {
	Name    string    `json:"name"`
	Path    string    `json:"path"`
	Size    int64     `json:"size"`
	ModTime time.Time `json:"modTime"`
	IsDir   bool      `json:"isDir"`
}

// UploadFileRequest documents the multipart fields for POST /api/files (path + file).
type UploadFileRequest struct {
	Path string `json:"path"`
}

// Server is the Gin HTTP server for PicoD.
type Server struct {
	cfg        Config
	engine     *gin.Engine
	publicKey  *rsa.PublicKey
	httpServer *http.Server
}

// NewServer validates config, loads PICOD_AUTH_PUBLIC_KEY PEM, and registers routes.
func NewServer(cfg Config) (*Server, error) {
	if cfg.Port <= 0 {
		return nil, fmt.Errorf("invalid port %d", cfg.Port)
	}
	if cfg.Workspace == "" {
		return nil, errors.New("workspace is required")
	}
	pemData := strings.TrimSpace(os.Getenv("PICOD_AUTH_PUBLIC_KEY"))
	if pemData == "" {
		return nil, errors.New("PICOD_AUTH_PUBLIC_KEY is required")
	}
	pub, err := parseRSAPublicKey([]byte(pemData))
	if err != nil {
		return nil, fmt.Errorf("parse public key: %w", err)
	}
	gin.SetMode(gin.ReleaseMode)
	r := gin.New()
	r.Use(gin.Recovery())

	s := &Server{cfg: cfg, engine: r, publicKey: pub}
	api := r.Group("/api")
	api.Use(s.jwtMiddleware())
	api.POST("/execute", s.handleExecute)
	api.POST("/files", s.handleUploadFile)
	api.GET("/files", s.handleListFiles)
	api.GET("/files/*path", s.handleGetFile)

	r.GET("/health", func(c *gin.Context) {
		c.String(http.StatusOK, "ok")
	})

	s.httpServer = &http.Server{
		Addr:              fmt.Sprintf(":%d", cfg.Port),
		Handler:           r,
		ReadHeaderTimeout: 30 * time.Second,
	}
	return s, nil
}

func (s *Server) jwtMiddleware() gin.HandlerFunc {
	return func(c *gin.Context) {
		h := c.GetHeader("Authorization")
		if !strings.HasPrefix(h, "Bearer ") {
			c.AbortWithStatusJSON(http.StatusUnauthorized, gin.H{"error": "missing bearer"})
			return
		}
		raw := strings.TrimSpace(strings.TrimPrefix(h, "Bearer "))
		tok, err := jwt.Parse(raw, func(t *jwt.Token) (interface{}, error) {
			if t.Method == nil || t.Method.Alg() != jwt.SigningMethodRS256.Alg() {
				return nil, fmt.Errorf("unexpected signing method")
			}
			return s.publicKey, nil
		})
		if err != nil || !tok.Valid {
			c.AbortWithStatusJSON(http.StatusUnauthorized, gin.H{"error": "invalid token"})
			return
		}
		c.Next()
	}
}

func (s *Server) handleExecute(c *gin.Context) {
	var req ExecuteRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.AbortWithStatusJSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}
	if len(req.Command) == 0 {
		c.AbortWithStatusJSON(http.StatusBadRequest, gin.H{"error": "command required"})
		return
	}
	timeout := defaultExecuteTimeout
	if req.Timeout != "" {
		if d, err := time.ParseDuration(req.Timeout); err == nil && d > 0 {
			timeout = d
		}
	}
	cwd := s.cfg.Workspace
	if req.Cwd != "" {
		var err error
		cwd, err = sanitizePath(s.cfg.Workspace, req.Cwd)
		if err != nil {
			c.AbortWithStatusJSON(http.StatusBadRequest, gin.H{"error": err.Error()})
			return
		}
	}
	ctx, cancel := context.WithTimeout(c.Request.Context(), timeout)
	defer cancel()
	cmd := exec.CommandContext(ctx, req.Command[0], req.Command[1:]...)
	cmd.Dir = cwd
	var stdout, stderr strings.Builder
	cmd.Stdout = &stdout
	cmd.Stderr = &stderr
	err := cmd.Run()
	resp := ExecuteResponse{Stdout: stdout.String(), Stderr: stderr.String()}
	if ctx.Err() == context.DeadlineExceeded {
		resp.TimedOut = true
		resp.ExitCode = TimeoutExitCode
		c.JSON(http.StatusOK, resp)
		return
	}
	if err != nil {
		if exitErr, ok := err.(*exec.ExitError); ok {
			resp.ExitCode = exitErr.ExitCode()
		} else {
			resp.Stderr = err.Error()
			resp.ExitCode = -1
		}
		c.JSON(http.StatusOK, resp)
		return
	}
	c.JSON(http.StatusOK, resp)
}

func (s *Server) handleUploadFile(c *gin.Context) {
	rel := c.PostForm("path")
	if rel == "" {
		c.AbortWithStatusJSON(http.StatusBadRequest, gin.H{"error": "path required"})
		return
	}
	target, err := sanitizePath(s.cfg.Workspace, rel)
	if err != nil {
		c.AbortWithStatusJSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}
	fh, err := c.FormFile("file")
	if err != nil {
		c.AbortWithStatusJSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}
	src, err := fh.Open()
	if err != nil {
		c.AbortWithStatusJSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	defer src.Close()
	if err := os.MkdirAll(filepath.Dir(target), 0o755); err != nil {
		c.AbortWithStatusJSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	dst, err := os.Create(target)
	if err != nil {
		c.AbortWithStatusJSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	defer dst.Close()
	if _, err := io.Copy(dst, src); err != nil {
		c.AbortWithStatusJSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	c.JSON(http.StatusOK, gin.H{"path": rel})
}

func (s *Server) handleListFiles(c *gin.Context) {
	root := s.cfg.Workspace
	entries, err := os.ReadDir(root)
	if err != nil {
		c.AbortWithStatusJSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	out := make([]FileInfo, 0, len(entries))
	for _, e := range entries {
		fi, err := e.Info()
		if err != nil {
			continue
		}
		out = append(out, FileInfo{
			Name:    e.Name(),
			Path:    e.Name(),
			Size:    fi.Size(),
			ModTime: fi.ModTime(),
			IsDir:   e.IsDir(),
		})
	}
	c.JSON(http.StatusOK, out)
}

func (s *Server) handleGetFile(c *gin.Context) {
	rel := strings.TrimPrefix(c.Param("path"), "/")
	target, err := sanitizePath(s.cfg.Workspace, rel)
	if err != nil {
		c.AbortWithStatusJSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}
	st, err := os.Stat(target)
	if err != nil {
		if os.IsNotExist(err) {
			c.AbortWithStatus(http.StatusNotFound)
			return
		}
		c.AbortWithStatusJSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	if st.IsDir() {
		c.AbortWithStatusJSON(http.StatusBadRequest, gin.H{"error": "path is a directory"})
		return
	}
	c.File(target)
}

func parseRSAPublicKey(pemBytes []byte) (*rsa.PublicKey, error) {
	block, _ := pem.Decode(pemBytes)
	if block == nil {
		return nil, errors.New("invalid PEM")
	}
	pub, err := x509.ParsePKIXPublicKey(block.Bytes)
	if err != nil {
		return nil, err
	}
	rsaPub, ok := pub.(*rsa.PublicKey)
	if !ok {
		return nil, errors.New("not an RSA public key")
	}
	return rsaPub, nil
}

func sanitizePath(workspace, rel string) (string, error) {
	if filepath.IsAbs(rel) {
		return "", errors.New("path must be relative")
	}
	clean := filepath.Clean(rel)
	if clean == ".." || strings.HasPrefix(clean, ".."+string(os.PathSeparator)) {
		return "", errors.New("path escapes workspace")
	}
	absW, err := filepath.Abs(workspace)
	if err != nil {
		return "", err
	}
	target := filepath.Join(absW, clean)
	relW, err := filepath.Rel(absW, target)
	if err != nil || strings.HasPrefix(relW, "..") {
		return "", errors.New("path escapes workspace")
	}
	return target, nil
}

// Run serves until ctx is cancelled.
func (s *Server) Run(ctx context.Context) error {
	errCh := make(chan error, 1)
	go func() {
		klog.InfoS("picod listening", "addr", s.httpServer.Addr)
		err := s.httpServer.ListenAndServe()
		if err != nil && !errors.Is(err, http.ErrServerClosed) {
			errCh <- err
			return
		}
		errCh <- nil
	}()
	select {
	case <-ctx.Done():
		shutdownCtx, cancel := context.WithTimeout(context.Background(), 15*time.Second)
		defer cancel()
		if err := s.httpServer.Shutdown(shutdownCtx); err != nil {
			return fmt.Errorf("picod shutdown: %w", err)
		}
		if err := <-errCh; err != nil {
			return err
		}
		return ctx.Err()
	case err := <-errCh:
		return err
	}
}
