# AgentCube CLI (`kubectl-agentcube`)

Python/Typer CLI for **packing**, **building**, **publishing**, and **invoking** agent workspaces against AgentCube or Kubernetes.

## Install

From this directory:

```bash
pip install -e .
kubectl-agentcube --help
```

Kubernetes helpers require the optional extra:

```bash
pip install -e ".[k8s]"
```

To call the published agent HTTP API you may also install the SDK in the same environment:

```bash
pip install -e ../../sdk-python
```

## Common commands

**Initialize metadata and Dockerfile** in an agent repo:

```bash
kubectl-agentcube pack --workspace ./my-agent --name demo-agent --namespace default
```

**Build** the container image locally (Docker):

```bash
kubectl-agentcube build --workspace ./my-agent --image-prefix registry.example.com/team
```

**Publish** to Kubernetes or the AgentCube control plane (see provider flags in `publish`):

```bash
kubectl-agentcube publish --provider k8s --workspace ./my-agent
```

**Invoke** with a JSON payload:

```bash
kubectl-agentcube invoke --workspace ./my-agent --payload '{"input":"hello"}'
```

**Check status**:

```bash
kubectl-agentcube status --workspace ./my-agent
```

Use `--verbose` / `-v` for structured JSON logging on any command.

## Examples

Under `cmd/cli/examples/`:

- `hello-agent` — minimal HTTP agent
- `math-agent` — sample with richer metadata
