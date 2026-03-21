package workloadmanager

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"fmt"
	"os"
	"strings"
	"sync"
	"time"

	"github.com/golang-jwt/jwt/v5"
	lru "github.com/hashicorp/golang-lru/v2"
	apierrors "k8s.io/apimachinery/pkg/api/errors"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/client-go/kubernetes"
	"k8s.io/client-go/rest"
	"k8s.io/klog/v2"
)

const picodIdentitySecret = "picod-router-identity"

// TokenCache caches Kubernetes TokenReview outcomes (5m TTL, max 1000 entries).
type TokenCache struct {
	mu    sync.Mutex
	inner *lru.Cache[string, tokenCacheEntry]
}

type tokenCacheEntry struct {
	ok       bool
	cachedAt time.Time
}

// NewTokenCache builds an LRU-backed token review cache.
func NewTokenCache() (*TokenCache, error) {
	c, err := lru.New[string, tokenCacheEntry](1000)
	if err != nil {
		return nil, err
	}
	return &TokenCache{inner: c}, nil
}

// Get returns (authenticated, hit). When hit is false, the caller should perform TokenReview.
func (t *TokenCache) Get(rawToken string) (ok bool, hit bool) {
	if t == nil {
		return false, false
	}
	t.mu.Lock()
	defer t.mu.Unlock()
	key := hashToken(rawToken)
	e, okLRU := t.inner.Get(key)
	if !okLRU {
		return false, false
	}
	if time.Since(e.cachedAt) > 5*time.Minute {
		t.inner.Remove(key)
		return false, false
	}
	return e.ok, true
}

// Put records a TokenReview result.
func (t *TokenCache) Put(rawToken string, authenticated bool) {
	if t == nil {
		return
	}
	t.mu.Lock()
	defer t.mu.Unlock()
	key := hashToken(rawToken)
	t.inner.Add(key, tokenCacheEntry{ok: authenticated, cachedAt: time.Now()})
}

func hashToken(raw string) string {
	sum := sha256.Sum256([]byte(raw))
	return hex.EncodeToString(sum[:])
}

// clientCacheEntry tracks a Kubernetes clientset until JWT expiry.
type clientCacheEntry struct {
	client *kubernetes.Clientset
	exp    time.Time
}

// ClientCache reuses Kubernetes clients keyed by bearer token until JWT exp.
type ClientCache struct {
	mu    sync.Mutex
	inner *lru.Cache[string, clientCacheEntry]
}

// NewClientCache constructs an LRU for impersonated clients (max 256).
func NewClientCache() (*ClientCache, error) {
	c, err := lru.New[string, clientCacheEntry](256)
	if err != nil {
		return nil, err
	}
	return &ClientCache{inner: c}, nil
}

// ClientForToken returns a clientset using the bearer token, cached until JWT exp (best-effort).
func (c *ClientCache) ClientForToken(base *rest.Config, rawToken string) (*kubernetes.Clientset, error) {
	if base == nil {
		return nil, errors.New("base config is nil")
	}
	exp, ok := jwtExp(rawToken)
	key := hashToken(rawToken)

	c.mu.Lock()
	if ent, hit := c.inner.Get(key); hit && time.Now().Before(ent.exp) {
		c.mu.Unlock()
		return ent.client, nil
	}
	c.mu.Unlock()

	cfg := rest.CopyConfig(base)
	cfg.BearerToken = rawToken
	cs, err := kubernetes.NewForConfig(cfg)
	if err != nil {
		return nil, err
	}
	if !ok {
		exp = time.Now().Add(5 * time.Minute)
	}
	c.mu.Lock()
	defer c.mu.Unlock()
	c.inner.Add(key, clientCacheEntry{client: cs, exp: exp})
	return cs, nil
}

func jwtExp(raw string) (time.Time, bool) {
	claims := &jwt.RegisteredClaims{}
	_, _, err := jwt.NewParser().ParseUnverified(raw, claims)
	if err != nil || claims.ExpiresAt == nil {
		return time.Time{}, false
	}
	return claims.ExpiresAt.Time, true
}

var (
	publicKeyMu     sync.RWMutex
	publicKeyPEM    []byte
	publicKeyLoaded bool
)

// InitPublicKeyCache loads the PicoD / router public key from the picod-router-identity Secret.
func InitPublicKeyCache(ctx context.Context, kube kubernetes.Interface) error {
	ns := strings.TrimSpace(os.Getenv("AGENTCUBE_NAMESPACE"))
	if ns == "" {
		ns = "agentcube-system"
	}
	sec, err := kube.CoreV1().Secrets(ns).Get(ctx, picodIdentitySecret, metav1.GetOptions{})
	if err != nil {
		if apierrors.IsNotFound(err) {
			klog.InfoS("picod identity secret not found; public key cache empty", "namespace", ns)
			return nil
		}
		return fmt.Errorf("load identity secret: %w", err)
	}
	pub := sec.Data["public-key.pem"]
	if len(pub) == 0 {
		return errors.New("identity secret missing public-key.pem")
	}
	publicKeyMu.Lock()
	publicKeyPEM = pub
	publicKeyLoaded = true
	publicKeyMu.Unlock()
	klog.InfoS("loaded PicoD public key from secret", "namespace", ns)
	return nil
}

// PublicKeyPEM returns cached PEM material when initialized.
func PublicKeyPEM() ([]byte, bool) {
	publicKeyMu.RLock()
	defer publicKeyMu.RUnlock()
	if !publicKeyLoaded {
		return nil, false
	}
	return append([]byte(nil), publicKeyPEM...), true
}
