---
sidebar_position: 3
---

# Security

AgentCube layers several mechanisms so **only authorized callers** can create sessions and **only the Router** can drive PicoD execution on behalf of those sessions.

## JWT authentication (Router → PicoD)

1. The Router maintains an RSA key pair in Kubernetes Secret **`picod-router-identity`** (keys `private-key.pem` / `public-key.pem`).
2. When proxying to PicoD, the Router attaches **`Authorization: Bearer <jwt>`** using **RS256** with a short time-to-live.
3. PicoD validates tokens with the **public key** injected as `PICOD_AUTH_PUBLIC_KEY`.

This keeps **signing keys off the data plane** while binding execution to platform-issued credentials.

## Kubernetes API access

The Workload Manager and Router use dedicated **ServiceAccounts** with RBAC scoped to required resources (CRDs, Pods, Services, Secrets for identity management). Helm templates under `manifests/charts/base/templates/rbac*` document the default roles.

Where the platform integrates **`TokenReview`**, validating bearer tokens from external identity providers, wire that at the **Router** or API gateway boundary **before** traffic reaches sandbox invocation paths. AgentCube’s core codebase focuses on service-to-service JWTs for PicoD; cluster admins should still enforce **OIDC** or **mTLS** at the edge for human or multi-tenant API access.

## CodeInterpreter `authMode`

`CodeInterpreter.spec.authMode` supports:

| Value | Use |
|-------|-----|
| `picod` | **Default.** JWT required on PicoD APIs. |
| `none` | Development only — no PicoD JWT gate. |

Production clusters should **always** use `picod`.

## Network and pod hardening

- **NetworkPolicy** — Restrict sandbox egress; allow only Router → sandbox paths required for your topology.
- **Pod Security** — Run interpreter and agent containers as **non-root** where possible; use `runtimeClassName` (gVisor, Kata, Kuasar) for stronger isolation.
- **Secrets** — Mount image pull secrets via CRD templates; never bake registry credentials into images.

## Supply chain

- Build images from pinned base layers; scan in CI.
- Use `helm upgrade` with versioned chart releases in production.

## Further reading

- `docs/design/PicoD-Plain-Authentication-Design.md`
- `pkg/router/jwt.go` and `pkg/picod/server.go`
