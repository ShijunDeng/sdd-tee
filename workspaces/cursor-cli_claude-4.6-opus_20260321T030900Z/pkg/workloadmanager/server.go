package workloadmanager

import (
	"context"
	"errors"
	"fmt"
	"net/http"
	"strings"
	"time"

	"github.com/gin-gonic/gin"
	commontypes "github.com/volcano-sh/agentcube/pkg/common/types"
	"github.com/volcano-sh/agentcube/pkg/store"
	"golang.org/x/net/http2"
	"golang.org/x/net/http2/h2c"
	authv1 "k8s.io/api/authentication/v1"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/client-go/dynamic"
	"k8s.io/client-go/kubernetes"
	"k8s.io/klog/v2"
)

// APIServer exposes workload-manager REST routes on Gin.
type APIServer struct {
	Config     Config
	Engine     *gin.Engine
	Builder    *SandboxBuilder
	RC         *SandboxReconciler
	Store      store.Store
	Kube       kubernetes.Interface
	Dyn        dynamic.Interface
	tokens     *TokenCache
	httpServer *http.Server
}

// NewAPIServer wires routes, optional auth, and dependencies.
func NewAPIServer(cfg Config, kube kubernetes.Interface, dyn dynamic.Interface, st store.Store, b *SandboxBuilder, rc *SandboxReconciler, tc *TokenCache) *APIServer {
	if cfg.Port <= 0 {
		cfg.Port = 8082
	}
	gin.SetMode(gin.ReleaseMode)
	r := gin.New()
	r.Use(gin.Recovery())
	r.Use(loggingMiddleware())
	s := &APIServer{Config: cfg, Engine: r, Builder: b, RC: rc, Store: st, Kube: kube, Dyn: dyn, tokens: tc}
	if cfg.EnableAuth {
		r.Use(s.tokenReviewMiddleware())
	}
	r.GET("/health", func(c *gin.Context) { c.String(http.StatusOK, "ok") })
	r.POST("/v1/agent-runtime", s.handleAgentRuntimeCreate)
	r.DELETE("/v1/agent-runtime/sessions/:sessionId", s.handleAgentRuntimeDelete)
	r.POST("/v1/code-interpreter", s.handleCodeInterpreterCreate)
	r.DELETE("/v1/code-interpreter/sessions/:sessionId", s.handleCodeInterpreterDelete)
	return s
}

func loggingMiddleware() gin.HandlerFunc {
	return func(c *gin.Context) {
		start := time.Now()
		c.Next()
		klog.InfoS("http", "method", c.Request.Method, "path", c.Request.URL.Path, "status", c.Writer.Status(), "latency", time.Since(start).String())
	}
}

func (s *APIServer) tokenReviewMiddleware() gin.HandlerFunc {
	return func(c *gin.Context) {
		if c.Request.URL.Path == "/health" {
			c.Next()
			return
		}
		h := c.GetHeader("Authorization")
		if !strings.HasPrefix(h, "Bearer ") {
			c.AbortWithStatusJSON(http.StatusUnauthorized, gin.H{"error": "missing bearer token"})
			return
		}
		raw := strings.TrimSpace(strings.TrimPrefix(h, "Bearer "))
		if s.tokens != nil {
			if ok, hit := s.tokens.Get(raw); hit {
				if ok {
					c.Next()
					return
				}
				c.AbortWithStatusJSON(http.StatusUnauthorized, gin.H{"error": "invalid token"})
				return
			}
		}
		tr := &authv1.TokenReview{
			Spec: authv1.TokenReviewSpec{Token: raw},
		}
		res, err := s.Kube.AuthenticationV1().TokenReviews().Create(c.Request.Context(), tr, metav1.CreateOptions{})
		if err != nil {
			klog.ErrorS(err, "TokenReview failed")
			c.AbortWithStatusJSON(http.StatusUnauthorized, gin.H{"error": "token review failed"})
			return
		}
		ok := res.Status.Authenticated
		if s.tokens != nil {
			s.tokens.Put(raw, ok)
		}
		if !ok {
			c.AbortWithStatusJSON(http.StatusUnauthorized, gin.H{"error": "unauthenticated"})
			return
		}
		c.Next()
	}
}

func (s *APIServer) handleAgentRuntimeCreate(c *gin.Context) {
	var req commontypes.CreateSandboxRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.AbortWithStatusJSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}
	req.Kind = commontypes.AgentRuntimeKind
	ctx := c.Request.Context()
	resp, nn, err := s.Builder.BuildSandboxByAgentRuntime(ctx, &req)
	if err != nil {
		klog.ErrorS(err, "build agent runtime sandbox")
		c.AbortWithStatusJSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	if s.RC != nil {
		ch := s.RC.WatchSandboxOnce(nn)
		defer s.RC.UnWatchSandbox(nn)
		select {
		case <-ch:
		case <-time.After(5 * time.Minute):
			c.AbortWithStatusJSON(http.StatusGatewayTimeout, gin.H{"error": "sandbox did not become ready"})
			return
		}
	}
	ip, err := GetSandboxPodIP(ctx, s.Kube, s.Dyn, nn.Namespace, nn.Name)
	if err != nil {
		klog.ErrorS(err, "get sandbox pod ip")
		c.AbortWithStatusJSON(http.StatusBadGateway, gin.H{"error": err.Error()})
		return
	}
	resp.PodIP = ip
	c.JSON(http.StatusOK, resp)
}

func (s *APIServer) handleCodeInterpreterCreate(c *gin.Context) {
	var req commontypes.CreateSandboxRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.AbortWithStatusJSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}
	req.Kind = commontypes.CodeInterpreterKind
	ctx := c.Request.Context()
	resp, nn, err := s.Builder.BuildSandboxByCodeInterpreter(ctx, &req)
	if err != nil {
		klog.ErrorS(err, "build code interpreter sandbox")
		c.AbortWithStatusJSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	if s.RC != nil {
		ch := s.RC.WatchSandboxOnce(nn)
		defer s.RC.UnWatchSandbox(nn)
		select {
		case <-ch:
		case <-time.After(5 * time.Minute):
			c.AbortWithStatusJSON(http.StatusGatewayTimeout, gin.H{"error": "sandbox did not become ready"})
			return
		}
	}
	ip, err := GetSandboxPodIP(ctx, s.Kube, s.Dyn, nn.Namespace, nn.Name)
	if err != nil {
		klog.ErrorS(err, "get sandbox pod ip")
		c.AbortWithStatusJSON(http.StatusBadGateway, gin.H{"error": err.Error()})
		return
	}
	resp.PodIP = ip
	c.JSON(http.StatusOK, resp)
}

func (s *APIServer) handleAgentRuntimeDelete(c *gin.Context) {
	s.deleteSession(c, c.Param("sessionId"), commontypes.AgentRuntimeKind)
}

func (s *APIServer) handleCodeInterpreterDelete(c *gin.Context) {
	s.deleteSession(c, c.Param("sessionId"), commontypes.CodeInterpreterKind)
}

func (s *APIServer) deleteSession(c *gin.Context, sessionID, kind string) {
	ctx := c.Request.Context()
	if s.Store == nil {
		c.AbortWithStatusJSON(http.StatusServiceUnavailable, gin.H{"error": "store not configured"})
		return
	}
	sb, err := s.Store.GetSandboxBySessionID(ctx, sessionID)
	if err != nil {
		if errors.Is(err, store.ErrNotFound) {
			c.Status(http.StatusNoContent)
			return
		}
		c.AbortWithStatusJSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	name := sb.SandboxCRName
	if name == "" {
		c.AbortWithStatusJSON(http.StatusBadRequest, gin.H{"error": "session missing sandbox CR reference"})
		return
	}
	if err := DeleteSandbox(ctx, s.Kube, s.Dyn, sb.Namespace, name); err != nil {
		klog.ErrorS(err, "delete sandbox")
		c.AbortWithStatusJSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	_ = s.Store.DeleteSandboxBySessionID(ctx, sessionID)
	c.Status(http.StatusNoContent)
}

// ListenAndServe starts HTTP/2 without TLS (h2c) or HTTPS when TLS is enabled.
func (s *APIServer) ListenAndServe() error {
	addr := fmt.Sprintf(":%d", s.Config.Port)
	if s.Config.EnableTLS {
		s.httpServer = &http.Server{
			Addr:              addr,
			Handler:           s.Engine,
			ReadHeaderTimeout: 30 * time.Second,
		}
		klog.InfoS("workload-manager API listening (HTTPS)", "addr", addr)
		return s.httpServer.ListenAndServeTLS(s.Config.TLSCert, s.Config.TLSKey)
	}
	h2s := &http2.Server{}
	s.httpServer = &http.Server{
		Addr:              addr,
		Handler:           h2c.NewHandler(s.Engine, h2s),
		ReadHeaderTimeout: 30 * time.Second,
	}
	klog.InfoS("workload-manager API listening (h2c)", "addr", addr)
	return s.httpServer.ListenAndServe()
}

// Shutdown stops the HTTP server started by ListenAndServe.
func (s *APIServer) Shutdown(ctx context.Context) error {
	if s.httpServer == nil {
		return nil
	}
	return s.httpServer.Shutdown(ctx)
}
