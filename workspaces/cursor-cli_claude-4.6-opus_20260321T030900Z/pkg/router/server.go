package router

import (
	"context"
	"errors"
	"fmt"
	"net/http"
	"net/http/httputil"
	"net/url"
	"strconv"
	"strings"
	"time"

	"github.com/gin-gonic/gin"
	commontypes "github.com/volcano-sh/agentcube/pkg/common/types"
	"github.com/volcano-sh/agentcube/pkg/store"
	"golang.org/x/sync/semaphore"
	"k8s.io/klog/v2"
)

// Server is the Gin-backed ingress router with session-aware reverse proxying.
type Server struct {
	cfg        Config
	engine     *gin.Engine
	srv        *http.Server
	SessionMgr *SessionManager
	Store      store.Store
	JWT        *JWTManager
	sem        *semaphore.Weighted
}

// NewServer constructs the router. Identity keys are loaded via JWTManager before serving.
func NewServer(cfg Config, st store.Store, jwt *JWTManager) (*Server, error) {
	if cfg.Port <= 0 {
		return nil, fmt.Errorf("invalid port %d", cfg.Port)
	}
	if cfg.EnableTLS && (cfg.TLSCert == "" || cfg.TLSKey == "") {
		return nil, errors.New("TLS enabled but TLSCert or TLSKey is empty")
	}
	if cfg.Debug {
		gin.SetMode(gin.DebugMode)
	} else {
		gin.SetMode(gin.ReleaseMode)
	}
	sm := NewSessionManager(st)
	r := gin.New()
	r.Use(gin.Recovery())
	r.Use(gin.LoggerWithWriter(gin.DefaultWriter, "/health/live", "/health/ready"))

	s := &Server{
		cfg:        cfg,
		engine:     r,
		SessionMgr: sm,
		Store:      st,
		JWT:        jwt,
		sem:        semaphore.NewWeighted(int64(cfg.maxConcurrent())),
	}
	s.registerRoutes()

	s.srv = &http.Server{
		Addr:              ":" + strconv.Itoa(cfg.Port),
		Handler:           r,
		ReadHeaderTimeout: 30 * time.Second,
	}
	return s, nil
}

func (s *Server) registerRoutes() {
	r := s.engine
	r.Use(s.concurrencyMiddleware())

	r.GET("/health/live", func(c *gin.Context) {
		c.Status(http.StatusOK)
	})
	r.GET("/health/ready", s.readyHandler)

	ar := func(c *gin.Context) { s.invokeHandler(c, commontypes.AgentRuntimeKind) }
	ci := func(c *gin.Context) { s.invokeHandler(c, commontypes.CodeInterpreterKind) }

	r.GET("/v1/namespaces/:namespace/agent-runtimes/:name/invocations/*path", ar)
	r.POST("/v1/namespaces/:namespace/agent-runtimes/:name/invocations/*path", ar)
	r.GET("/v1/namespaces/:namespace/code-interpreters/:name/invocations/*path", ci)
	r.POST("/v1/namespaces/:namespace/code-interpreters/:name/invocations/*path", ci)
}

func (s *Server) concurrencyMiddleware() gin.HandlerFunc {
	return func(c *gin.Context) {
		if !s.sem.TryAcquire(1) {
			c.AbortWithStatusJSON(http.StatusTooManyRequests, gin.H{"error": "max concurrent requests exceeded"})
			return
		}
		defer s.sem.Release(1)
		c.Next()
	}
}

func (s *Server) readyHandler(c *gin.Context) {
	if s.Store == nil {
		c.Status(http.StatusOK)
		return
	}
	ctx, cancel := context.WithTimeout(c.Request.Context(), 3*time.Second)
	defer cancel()
	if err := s.Store.Ping(ctx); err != nil {
		klog.ErrorS(err, "readiness store ping failed")
		c.AbortWithStatus(http.StatusServiceUnavailable)
		return
	}
	c.Status(http.StatusOK)
}

func (s *Server) invokeHandler(c *gin.Context, kind string) {
	ctx := c.Request.Context()
	ns := c.Param("namespace")
	resName := c.Param("name")
	tail := strings.TrimSpace(c.Param("path"))
	if tail == "" {
		tail = "/"
	}
	if !strings.HasPrefix(tail, "/") {
		tail = "/" + tail
	}

	sessionHdr := c.GetHeader(SessionHeader())
	sb, sid, err := s.SessionMgr.GetSandboxBySession(ctx, ns, resName, kind, sessionHdr)
	if err != nil {
		klog.ErrorS(err, "session resolution failed", "namespace", ns, "name", resName)
		c.AbortWithStatusJSON(http.StatusBadGateway, gin.H{"error": err.Error()})
		return
	}
	c.Header(SessionHeader(), sid)

	if sb.PodIP == "" {
		c.AbortWithStatusJSON(http.StatusBadGateway, gin.H{"error": "sandbox pod not ready"})
		return
	}

	port := sb.UpstreamPort
	if port <= 0 {
		port = 8080
	}

	var token string
	if s.JWT != nil {
		var err error
		token, err = s.JWT.GenerateToken(sid)
		if err != nil {
			klog.ErrorS(err, "jwt sign failed")
			c.AbortWithStatusJSON(http.StatusInternalServerError, gin.H{"error": "token issue failed"})
			return
		}
	}

	target := &url.URL{Scheme: "http", Host: fmt.Sprintf("%s:%d", sb.PodIP, port)}
	proxy := httputil.NewSingleHostReverseProxy(target)
	orig := proxy.Director
	proxy.Director = func(req *http.Request) {
		orig(req)
		req.URL.Path = tail
		req.URL.RawQuery = c.Request.URL.RawQuery
		req.Method = c.Request.Method
		req.Header = c.Request.Header.Clone()
		if token != "" {
			req.Header.Set("Authorization", "Bearer "+token)
		}
		req.Host = target.Host
	}
	proxy.ErrorHandler = func(w http.ResponseWriter, r *http.Request, err error) {
		klog.ErrorS(err, "reverse proxy error", "sessionID", sid)
		w.WriteHeader(http.StatusBadGateway)
	}
	proxy.ServeHTTP(c.Writer, c.Request)

	go func() {
		bg, cancel := context.WithTimeout(context.Background(), 3*time.Second)
		defer cancel()
		if s.Store != nil {
			if err := s.Store.UpdateSessionLastActivity(bg, sid, time.Now().Unix()); err != nil {
				klog.V(3).InfoS("update last activity", "err", err, "sessionID", sid)
			}
		}
	}()
}

// Run serves until ctx is cancelled.
func (s *Server) Run(ctx context.Context) error {
	errCh := make(chan error, 1)
	go func() {
		klog.InfoS("router listening", "addr", s.srv.Addr, "tls", s.cfg.EnableTLS)
		var err error
		if s.cfg.EnableTLS {
			err = s.srv.ListenAndServeTLS(s.cfg.TLSCert, s.cfg.TLSKey)
		} else {
			err = s.srv.ListenAndServe()
		}
		if err != nil && !errors.Is(err, http.ErrServerClosed) {
			errCh <- err
			return
		}
		errCh <- nil
	}()

	select {
	case <-ctx.Done():
		shutdownCtx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
		defer cancel()
		if err := s.srv.Shutdown(shutdownCtx); err != nil {
			return fmt.Errorf("router shutdown: %w", err)
		}
		if err := <-errCh; err != nil {
			return err
		}
		return ctx.Err()
	case err := <-errCh:
		return err
	}
}
