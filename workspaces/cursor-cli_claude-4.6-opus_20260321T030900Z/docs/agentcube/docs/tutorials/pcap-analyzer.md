---
sidebar_position: 3
---

# PCAP analyzer in a CodeInterpreter sandbox

This tutorial sketches a **safe network forensics** workflow: upload a `.pcap` into an isolated **CodeInterpreter** sandbox, run **tshark** or **Scapy** analysis, and download artifacts—without executing untrusted tools on your laptop.

## Prerequisites

- A `CodeInterpreter` CR pointing to an image with **PicoD** and analysis tools (or install them at session start via `execute_command`)
- Router URL reachable from your workstation or a bastion pod
- Python SDK installed (`pip install -e ./sdk-python`)

## 1. Create a CodeInterpreter resource

Example (adjust image, namespace, and resources):

```yaml
apiVersion: runtime.agentcube.volcano.sh/v1alpha1
kind: CodeInterpreter
metadata:
  name: pcap-ci
  namespace: default
spec:
  authMode: picod
  warmPoolSize: 1
  ports:
    - name: http
      pathPrefix: /
      port: 8080
      protocol: HTTP
  template:
    image: ghcr.io/example/pcap-interpreter:latest
    resources:
      requests:
        cpu: "500m"
        memory: 512Mi
```

Apply with `kubectl apply -f codeinterpreter-pcap.yaml`.

## 2. Upload and analyze with the SDK

```python
from pathlib import Path

from agentcube.code_interpreter import CodeInterpreterClient

ROUTER = "http://agentcube-router.agentcube.svc.cluster.local:8080"
NS = "default"

with CodeInterpreterClient(
    control_plane_url=ROUTER,
    namespace=NS,
    create_body={"codeInterpreter": "pcap-ci"},
) as ci:
    pcap = Path("capture.pcap").read_bytes()
    ci.upload_file("/workspace/capture.pcap", pcap)
    summary = ci.execute_command(
        "tshark -r /workspace/capture.pcap -q -z io,stat,1",
        cwd="/workspace",
    )
    print(summary)
```

Replace `create_body` with the JSON your Router expects for session creation.

## 3. Download reports

```python
report = ci.download_file("/workspace/report.txt")
Path("report.txt").write_bytes(report)
```

## Hardening notes

- Keep **PCAPs that may contain secrets** inside tenant-isolated namespaces.
- Use **NetworkPolicy** to block sandbox egress except DNS and required endpoints.
- Set conservative **`maxSessionDuration`** on the CRD so long-running analysis cannot linger indefinitely.

## Stretch goals

- Wrap the SDK in a **LangChain** tool (see `docs/devguide/code-interpreter-using-langchain.md` in the repository).
- Pre-build images with **pinned** tool versions for reproducible reports.
