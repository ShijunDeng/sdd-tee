package router

import (
	"context"
	"crypto/rand"
	"crypto/rsa"
	"crypto/x509"
	"encoding/pem"
	"errors"
	"fmt"
	"os"
	"strings"
	"sync"
	"time"

	"github.com/golang-jwt/jwt/v5"
	corev1 "k8s.io/api/core/v1"
	apierrors "k8s.io/apimachinery/pkg/api/errors"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/client-go/kubernetes"
	"k8s.io/klog/v2"
)

const (
	identitySecretName = "picod-router-identity"
	issuer             = "agentcube-router"
	tokenTTL           = 5 * time.Minute
	privKeyPEMKey      = "private-key.pem"
	pubKeyPEMKey       = "public-key.pem"
)

// Identity holds the RSA signing keypair used for upstream JWT auth.
type Identity struct {
	PrivateKey *rsa.PrivateKey
	PublicKey  *rsa.PublicKey
	mu         sync.RWMutex
}

// JWTManager issues short-lived RS256 tokens for session-scoped upstream calls.
type JWTManager struct {
	ns      string
	client  kubernetes.Interface
	id      *Identity
	once    sync.Once
	initMu  sync.Mutex
	initErr error
}

// NewJWTManager loads or creates the picod-router-identity Secret in AGENTCUBE_NAMESPACE.
func NewJWTManager(client kubernetes.Interface) *JWTManager {
	ns := strings.TrimSpace(os.Getenv("AGENTCUBE_NAMESPACE"))
	if ns == "" {
		ns = "agentcube-system"
	}
	return &JWTManager{ns: ns, client: client}
}

// LoadOrCreateIdentity ensures RSA-2048 material exists in the cluster Secret.
func (m *JWTManager) LoadOrCreateIdentity(ctx context.Context) error {
	m.initMu.Lock()
	defer m.initMu.Unlock()
	m.once.Do(func() {
		m.initErr = m.loadOrCreate(ctx)
	})
	return m.initErr
}

func (m *JWTManager) loadOrCreate(ctx context.Context) error {
	if m.client == nil {
		return errors.New("kubernetes client is nil")
	}
	sec, err := m.client.CoreV1().Secrets(m.ns).Get(ctx, identitySecretName, metav1.GetOptions{})
	if err == nil {
		id, derr := identityFromSecret(sec)
		if derr != nil {
			return derr
		}
		m.id = id
		klog.InfoS("loaded router JWT identity", "namespace", m.ns, "secret", identitySecretName)
		return nil
	}
	if !apierrors.IsNotFound(err) {
		return fmt.Errorf("get identity secret: %w", err)
	}

	priv, err := rsa.GenerateKey(rand.Reader, 2048)
	if err != nil {
		return fmt.Errorf("generate rsa key: %w", err)
	}
	privDER := x509.MarshalPKCS1PrivateKey(priv)
	privPEM := pem.EncodeToMemory(&pem.Block{Type: "RSA PRIVATE KEY", Bytes: privDER})
	pubDER, err := x509.MarshalPKIXPublicKey(&priv.PublicKey)
	if err != nil {
		return err
	}
	pubPEM := pem.EncodeToMemory(&pem.Block{Type: "PUBLIC KEY", Bytes: pubDER})

	newSec := &corev1.Secret{
		ObjectMeta: metav1.ObjectMeta{
			Name:      identitySecretName,
			Namespace: m.ns,
			Labels: map[string]string{
				"app.kubernetes.io/name": "agentcube-router",
			},
		},
		Type: corev1.SecretTypeOpaque,
		Data: map[string][]byte{
			privKeyPEMKey: privPEM,
			pubKeyPEMKey:  pubPEM,
		},
	}
	if _, err := m.client.CoreV1().Secrets(m.ns).Create(ctx, newSec, metav1.CreateOptions{}); err != nil {
		if apierrors.IsAlreadyExists(err) {
			return m.reloadIdentity(ctx)
		}
		return fmt.Errorf("create identity secret: %w", err)
	}
	m.id = &Identity{PrivateKey: priv, PublicKey: &priv.PublicKey}
	klog.InfoS("created router JWT identity", "namespace", m.ns, "secret", identitySecretName)
	return nil
}

func (m *JWTManager) reloadIdentity(ctx context.Context) error {
	sec, err := m.client.CoreV1().Secrets(m.ns).Get(ctx, identitySecretName, metav1.GetOptions{})
	if err != nil {
		return fmt.Errorf("reload identity secret: %w", err)
	}
	id, err := identityFromSecret(sec)
	if err != nil {
		return err
	}
	m.id = id
	return nil
}

func identityFromSecret(sec *corev1.Secret) (*Identity, error) {
	privBytes := sec.Data[privKeyPEMKey]
	pubBytes := sec.Data[pubKeyPEMKey]
	if len(privBytes) == 0 || len(pubBytes) == 0 {
		return nil, fmt.Errorf("identity secret missing %s or %s", privKeyPEMKey, pubKeyPEMKey)
	}
	privBlock, _ := pem.Decode(privBytes)
	if privBlock == nil {
		return nil, errors.New("invalid private key PEM")
	}
	var privKey *rsa.PrivateKey
	if pk, err := x509.ParsePKCS1PrivateKey(privBlock.Bytes); err == nil {
		privKey = pk
	} else {
		any, err2 := x509.ParsePKCS8PrivateKey(privBlock.Bytes)
		if err2 != nil {
			return nil, fmt.Errorf("parse private key: %w", err)
		}
		var ok bool
		privKey, ok = any.(*rsa.PrivateKey)
		if !ok {
			return nil, errors.New("private key is not RSA")
		}
	}
	pubBlock, _ := pem.Decode(pubBytes)
	if pubBlock == nil {
		return nil, errors.New("invalid public key PEM")
	}
	pubAny, err := x509.ParsePKIXPublicKey(pubBlock.Bytes)
	if err != nil {
		return nil, err
	}
	pubRSA, ok := pubAny.(*rsa.PublicKey)
	if !ok {
		return nil, errors.New("public key is not RSA")
	}
	return &Identity{PrivateKey: privKey, PublicKey: pubRSA}, nil
}

// GenerateToken returns a JWT bound to sessionID with RS256, 5m expiry.
func (m *JWTManager) GenerateToken(sessionID string) (string, error) {
	if m.id == nil {
		return "", errors.New("identity not loaded")
	}
	m.id.mu.RLock()
	defer m.id.mu.RUnlock()
	now := time.Now()
	claims := jwt.RegisteredClaims{
		Subject:   sessionID,
		Issuer:    issuer,
		IssuedAt:  jwt.NewNumericDate(now),
		ExpiresAt: jwt.NewNumericDate(now.Add(tokenTTL)),
	}
	t := jwt.NewWithClaims(jwt.SigningMethodRS256, claims)
	return t.SignedString(m.id.PrivateKey)
}
