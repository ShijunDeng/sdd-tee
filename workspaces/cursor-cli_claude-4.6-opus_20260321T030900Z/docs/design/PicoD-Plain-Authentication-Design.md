# PicoD Plain Authentication Design

PicoD runs **inside** the sandbox and exposes sensitive APIs: arbitrary command execution and file read/write. AgentCube uses **asymmetric JWT authentication** so only the control plane (via the Router) can obtain valid tokens for a given session.

## Threat model (summary)

- Untrusted workloads may run in the same network namespace as PicoD; **network policy** should restrict who can reach PicoD’s listen port.
- Even with network controls, defense in depth requires **cryptographic proof** that a request was authorized by the platform for the current session.

## RSA key pair

1. **Router** owns an **RSA-2048** (or stronger) key pair used to sign short-lived JWTs (`RS256`).
2. Key material is stored in a Kubernetes **Secret** named **`picod-router-identity`** in `AGENTCUBE_NAMESPACE` (default `agentcube-system` if unset).
3. Secret keys:
   - `private-key.pem` — PEM-encoded private key (Router only).
   - `public-key.pem` — PEM-encoded public key (distributed to PicoD).

The `JWTManager` loads existing material or **generates and persists** the Secret on first use (`LoadOrCreateIdentity`).

## JWT tokens

- **Issuer** (`iss`): `agentcube-router`
- **Algorithm**: `RS256`
- **TTL**: short (implementation default **5 minutes**) to limit replay window
- Claims include session-scoping fields as required by the Router/PicoD contract (subject, audience, or custom claims aligned with invocation path — see `pkg/router/jwt.go`).

The Router attaches `Authorization: Bearer <jwt>` when proxying to PicoD-backed endpoints.

## PicoD verification

PicoD **does not** read the Kubernetes Secret directly in the minimal deployment model. Instead:

1. The sandbox Pod is configured with environment variable **`PICOD_AUTH_PUBLIC_KEY`** containing the **PEM public key** string.
2. On startup, `NewServer` parses the key; all `/api/*` routes (except health) go through **JWT middleware**:
   - Require `Bearer` prefix
   - Parse and validate with `RS256` and the public key
   - Reject missing/invalid tokens with `401`

This keeps the **private key off the data plane** entirely.

## Router identity secret operations

- Router ServiceAccount (when RBAC is enabled) needs **get/create/patch** on Secrets for `picod-router-identity` in its namespace.
- Rotation: replace both PEM entries in the Secret and roll Router + interpreter sandboxes so PicoD receives the new public key (or use a coordinated rollout strategy).

## Failure modes

| Symptom | Likely cause |
|---------|----------------|
| PicoD fails to start | `PICOD_AUTH_PUBLIC_KEY` empty or malformed PEM |
| 401 on `/api/execute` | Clock skew, expired JWT, wrong public key, token not RS256 |
| Router cannot sign | Secret missing keys, insufficient RBAC |

## Auth mode `none` (CodeInterpreter)

`CodeInterpreter.spec.authMode` may be set to `none` for **development only**. Production clusters should use **`picod`** so every data-plane call is JWT-gated.

## References

- `pkg/router/jwt.go` — identity Secret, signing
- `pkg/picod/server.go` — `PICOD_AUTH_PUBLIC_KEY`, middleware
