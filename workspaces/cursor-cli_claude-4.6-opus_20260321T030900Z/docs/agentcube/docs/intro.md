---
sidebar_position: 1
---

# Introduction

**AgentCube** is a Kubernetes-native platform for **AI agent workloads**, developed as a subproject of [Volcano](https://github.com/volcano-sh/volcano). It focuses on problems that generic controllers under-solve: **where** agent sandboxes run, **how long** they live, **how** traffic reaches them safely, and **how** in-sandbox execution stays authenticated.

## What AgentCube provides

- **Custom resources** — `AgentRuntime` describes reusable sandbox templates (pod shape, HTTP(S) routing metadata, session timeouts). `CodeInterpreter` describes managed interpreter pools with optional **warm pools** and PicoD-friendly auth modes.
- **Control plane services** — The **Router** fronts session-aware HTTP traffic and issues short-lived JWTs for PicoD. The **Workload Manager** reconciles CRDs against the Kubernetes API and coordinates session state with **Redis** or **Valkey**.
- **In-sandbox daemon** — **PicoD** exposes execution and file APIs inside the sandbox, validating RS256 tokens from the Router.
- **Developer tooling** — Python SDK (`sdk-python`) and CLI (`kubectl-agentcube`) for packaging, building, publishing, and invoking agents.

## When to use AgentCube

Choose AgentCube when you need **multi-tenant agent sandboxes** on Kubernetes with:

- Declarative **runtime templates** shared across teams
- **Session lifecycle** policy (idle timeout, max duration)
- **Edge routing** that understands agent and interpreter invocations
- Integration with **Volcano** scheduling for queue-aware placement

## Next steps

- [Getting started](./getting-started.md) — install CRDs, Redis, and the Helm chart
- [Architecture overview](./architecture/overview.md) — control plane vs data plane
- [First agent tutorial](./tutorials/first-agent.md) — end-to-end hello world

Design proposals and deep dives live in the repository under `docs/design/`.
