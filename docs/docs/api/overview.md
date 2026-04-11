---
title: API Overview
sidebar_label: Overview
---

# API Overview

This document provides an overview of the AgentCube APIs, including versioning, authentication, common patterns, and error handling.

## API Versions

AgentCube follows semantic versioning for APIs:

- **Current Version**: v1.0
- **Supported Versions**: v1.0, v0.9
- **Deprecated Versions**: None

### Versioning Strategy

- **Major Version**: Breaking changes to API structure
- **Minor Version**: New features, backward compatible
- **Patch Version**: Bug fixes, backward compatible

### API Paths

```
/v1.0/...  # Current stable API
/v0.9/...  # Previous stable version
```

## Authentication

All API requests require authentication unless explicitly documented otherwise.

### Authentication Methods

#### 1. Bearer Token (JWT)

Include JWT token in the `Authorization` header:

```http
GET /v1/sessions/default/CodeInterpreter/my-interpreter
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

#### 2. Kubernetes Service Account Token

Include K8s token in the `Authorization` header:

```http
GET /v1/sessions/default/CodeInterpreter/my-interpreter
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

#### 3. Session Token

Some operations require session-specific tokens:

```http
POST /api/execute
x-agentcube-session-id: 550e8400-e29b-41d4-a716-446655440000
```

### Authentication Flow

```mermaid
sequenceDiagram
    participant C as Client
    participant R as Router
    participant A as Auth Service
    participant K as Kubernetes

    C->>R: Request with token
    R->>R: Extract token
    alt JWT Token
        R->>R: Validate signature
        R-->>R: User claims
    else K8s Token
        R->>K: TokenReview API
        K-->>R: User info
    end
    R->>A: Check authorization
    A-->>R: Authorized/Denied
    alt Authorized
        R->>R: Process request
        R-->>C: Response
    else Denied
        R-->>C: 403 Forbidden
    end
```

## Common Request/Response Formats

### Request Format

All requests use JSON format unless otherwise specified:

```http
POST /v1/sessions/default/CodeInterpreter/my-interpreter
Content-Type: application/json
Authorization: Bearer <token>

{
  "ttl": 3600,
  "metadata": {
    "user": "example-user",
    "environment": "production"
  }
}
```

### Response Format

All responses use JSON format:

```json
{
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "token": "session-token-here",
  "pod_name": "my-interpreter-abc123",
  "pod_ip": "10.244.1.5",
  "pod_port": 2222,
  "created_at": "2024-01-01T00:00:00Z",
  "expires_at": "2024-01-01T01:00:00Z",
  "metadata": {
    "user": "example-user",
    "environment": "production"
  }
}
```

### Pagination

List APIs support pagination:

```http
GET /v1/sessions?limit=50&offset=0&sort=created_at:desc
```

**Response**:
```json
{
  "items": [...],
  "total": 100,
  "limit": 50,
  "offset": 0,
  "has_more": true
}
```

### Filtering

List APIs support filtering:

```http
GET /v1/sessions?namespace=default&kind=CodeInterpreter&status=active
```

## Error Handling

### Error Response Format

All errors follow this format:

```json
{
  "error": {
    "code": "SESSION_NOT_FOUND",
    "message": "Session with ID '550e8400-e29b-41d4-a716-446655440000' not found",
    "details": {
      "session_id": "550e8400-e29b-41d4-a716-446655440000"
    },
    "request_id": "req-abc123",
    "timestamp": "2024-01-01T00:00:00Z"
  }
}
```

### HTTP Status Codes

| Status Code | Description |
|-------------|-------------|
| 200 | Success |
| 201 | Created |
| 204 | No Content |
| 400 | Bad Request |
| 401 | Unauthorized |
| 403 | Forbidden |
| 404 | Not Found |
| 409 | Conflict |
| 422 | Unprocessable Entity |
| 429 | Too Many Requests |
| 500 | Internal Server Error |
| 503 | Service Unavailable |

### Error Codes

| Code | HTTP Status | Description |
|------|-------------|-------------|
| INVALID_REQUEST | 400 | Invalid request parameters |
| UNAUTHORIZED | 401 | Authentication failed |
| FORBIDDEN | 403 | Authorization failed |
| NOT_FOUND | 404 | Resource not found |
| SESSION_NOT_FOUND | 404 | Session not found |
| CR_NOT_FOUND | 404 | Custom Resource not found |
| CONFLICT | 409 | Resource conflict |
| SESSION_EXPIRED | 410 | Session has expired |
| RATE_LIMIT_EXCEEDED | 429 | Rate limit exceeded |
| INTERNAL_ERROR | 500 | Internal server error |
| SERVICE_UNAVAILABLE | 503 | Service temporarily unavailable |

### Error Handling Example

```python
import requests
from agentcube.exceptions import AgentCubeError

try:
    response = requests.post(
        "http://localhost:8080/v1/sessions/default/CodeInterpreter/my-interpreter",
        json={"ttl": 3600},
        headers={"Authorization": "Bearer <token>"}
    )
    response.raise_for_status()
    return response.json()
except requests.exceptions.HTTPError as e:
    if e.response.status_code == 404:
        raise AgentCubeError("Session not found")
    elif e.response.status_code == 401:
        raise AgentCubeError("Authentication failed")
    else:
        raise AgentCubeError(f"API error: {e}")
except requests.exceptions.RequestException as e:
    raise AgentCubeError(f"Request failed: {e}")
```

## API Types

### 1. REST API

RESTful HTTP API for session management and operations.

**Base URL**: `http://localhost:8080/v1`

**Features**:
- Session management (create, get, delete)
- Resource proxying
- File operations
- Health checks

**Documentation**: [REST API Reference](rest.md)

### 2. gRPC API

High-performance RPC API for advanced use cases.

**Endpoint**: `localhost:8080`

**Features**:
- Bidirectional streaming
- Low latency
- Type-safe interfaces
- Efficient serialization

**Documentation**: [gRPC API Reference](grpc.md)

### 3. CRD API

Kubernetes Custom Resource API for declarative configuration.

**Resources**:
- `AgentRuntime` (runtime.agentcube.volcano.sh/v1alpha1)
- `CodeInterpreter` (runtime.agentcube.volcano.sh/v1alpha1)

**Documentation**: [CRD API Reference](crd.md)

### 4. SDK

Client libraries for popular languages.

**Languages**:
- Python (agentcube-sdk)
- Go (client-go)

**Documentation**: [SDK Reference](sdk.md)

## Rate Limiting

### Rate Limit Headers

```http
X-RateLimit-Limit: 1000
X-RateLimit-Remaining: 999
X-RateLimit-Reset: 1609459200
```

### Rate Limits

| Endpoint | Limit | Window |
|----------|-------|--------|
| Session Management | 100 requests | 1 minute |
| Command Execution | 1000 requests | 1 minute |
| File Operations | 500 requests | 1 minute |

## Request ID Correlation

Every request/response includes a `X-Request-ID` header for tracing:

```http
X-Request-ID: req-abc123
```

Include this header in support requests for faster troubleshooting.

## Compression

API supports gzip compression:

```http
Accept-Encoding: gzip
```

## CORS

Cross-Origin Resource Sharing is configured for web clients:

```http
Access-Control-Allow-Origin: *
Access-Control-Allow-Methods: GET, POST, PUT, DELETE, OPTIONS
Access-Control-Allow-Headers: Content-Type, Authorization, X-Agentcube-Session-Id
```

## Webhooks

### Webhook Events

AgentCube can send webhook notifications for various events:

| Event | Description |
|-------|-------------|
| session.created | Session created |
| session.deleted | Session deleted |
| session.expired | Session expired |
| pod.failed | Pod creation failed |

### Webhook Configuration

Configure webhooks via CRD:

```yaml
apiVersion: runtime.agentcube.volcano.sh/v1alpha1
kind: CodeInterpreter
metadata:
  name: my-interpreter
spec:
  webhooks:
    - url: https://example.com/webhooks
      secret: webhook-secret
      events:
        - session.created
        - session.deleted
```

## API Examples

### Python

```python
from agentcube import CodeInterpreterClient

with CodeInterpreterClient(
    router_url="http://localhost:8080",
    workload_manager_url="http://localhost:8080",
    name="my-interpreter",
    namespace="default"
) as client:
    # Execute code
    result = client.run_code("print('Hello, AgentCube!')")
    print(result["stdout"])
```

### Go

```go
package main

import (
    "context"
    "fmt"
    client "github.com/volcano-sh/agentcube/client-go"
)

func main() {
    c, err := client.NewClient(client.Config{
        RouterURL: "http://localhost:8080",
    })
    if err != nil {
        panic(err)
    }

    session, err := c.CreateSession(context.Background(), client.SessionRequest{
        Namespace: "default",
        Kind:      "CodeInterpreter",
        Name:      "my-interpreter",
        TTL:       3600,
    })
    if err != nil {
        panic(err)
    }

    fmt.Printf("Session ID: %s\n", session.ID)
}
```

### cURL

```bash
# Create session
curl -X POST "http://localhost:8080/v1/sessions/default/CodeInterpreter/my-interpreter" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <token>" \
  -d '{"ttl": 3600}'

# Execute command
curl -X POST "http://localhost:8080/api/execute" \
  -H "Content-Type: application/json" \
  -H "x-agentcube-session-id: <session-id>" \
  -d '{"command": ["echo", "Hello"], "timeout": "30s"}'
```

## Best Practices

### 1. Error Handling

- Always check HTTP status codes
- Handle errors gracefully
- Implement retry logic for transient failures
- Log errors with context

### 2. Session Management

- Reuse sessions when possible
- Clean up sessions when done
- Monitor session expiration
- Use warm pools for performance

### 3. Resource Management

- Set appropriate timeouts
- Use connection pooling
- Monitor resource usage
- Respect rate limits

### 4. Security

- Never log sensitive data
- Validate all inputs
- Use HTTPS in production
- Rotate credentials regularly

## Next Steps

- [REST API](rest.md): Detailed REST API documentation
- [gRPC API](grpc.md): gRPC service definitions
- [CRD API](crd.md): Custom Resource specifications
- [SDK Reference](sdk.md): Client library documentation