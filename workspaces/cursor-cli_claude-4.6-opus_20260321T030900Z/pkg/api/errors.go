package api

import (
	"errors"
	"fmt"
	"net/http"

	apierrors "k8s.io/apimachinery/pkg/api/errors"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/runtime/schema"
)

// Sentinel errors for domain checks and shared handlers.
var (
	ErrAgentRuntimeNotFound    = errors.New("agent runtime not found")
	ErrCodeInterpreterNotFound = errors.New("code interpreter not found")
	ErrTemplateMissing         = errors.New("sandbox template is missing")
	ErrPublicKeyMissing        = errors.New("public key is missing")
)

var sessionResource = schema.GroupResource{Group: "agentcube.volcano.sh", Resource: "sessions"}
var sandboxTemplateResource = schema.GroupResource{Group: "agentcube.volcano.sh", Resource: "sandboxtemplates"}

// NewSessionNotFoundError builds a NotFound StatusError for a session identifier.
func NewSessionNotFoundError(sessionID string) error {
	return apierrors.NewNotFound(sessionResource, sessionID)
}

// NewSandboxTemplateNotFoundError builds a NotFound StatusError for a template reference.
func NewSandboxTemplateNotFoundError(name string) error {
	return apierrors.NewNotFound(sandboxTemplateResource, name)
}

// NewInternalError wraps an error as an InternalError StatusError.
func NewInternalError(err error) error {
	return apierrors.NewInternalError(err)
}

// NewUpstreamUnavailableError returns a 503-style error for dependency failures.
func NewUpstreamUnavailableError(reason string) *apierrors.StatusError {
	return &apierrors.StatusError{
		ErrStatus: metav1.Status{
			Status:  metav1.StatusFailure,
			Code:    http.StatusServiceUnavailable,
			Reason:  metav1.StatusReasonServiceUnavailable,
			Message: fmt.Sprintf("upstream unavailable: %s", reason),
		},
	}
}
