package router

// LastActivityAnnotationKey is propagated to sandbox workloads for idle tracking.
const LastActivityAnnotationKey = "agentcube.volcano.sh/last-activity"

// Config holds HTTP listener and TLS settings for the router.
type Config struct {
	Port                  int
	Debug                 bool
	EnableTLS             bool
	TLSCert               string
	TLSKey                string
	MaxConcurrentRequests int
}

// DefaultMaxConcurrentRequests is applied when Config.MaxConcurrentRequests is zero.
const DefaultMaxConcurrentRequests = 1000

func (c *Config) maxConcurrent() int {
	if c == nil || c.MaxConcurrentRequests <= 0 {
		return DefaultMaxConcurrentRequests
	}
	return c.MaxConcurrentRequests
}
