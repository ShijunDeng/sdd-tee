# PCAP Analyzer (AgentCube + FastAPI + LangGraph)

Example API that uploads a capture file into an **AgentCube code interpreter**, runs lightweight CLI analysis (`capinfos` / `tshark` when available), and returns a **plan** plus a **markdown-style report** via a small **LangGraph** pipeline (planner → sandbox tools → reporter).

## Prerequisites

- A reachable AgentCube **control plane / router** URL (same base URL used by the Python SDK).
- A Kubernetes **namespace** where `CodeInterpreter` sessions can be created.
- Interpreter sandbox images that include network tools if you want `tshark` output (otherwise the service falls back to `file`).

## Install

From the repository root (editable SDK):

```bash
cd sdk-python && pip install -e .
cd ../example/pcap-analyzer
pip install -r requirements.txt
```

Or install `agentcube-sdk` from PyPI if published.

## Configuration

| Variable | Description |
|----------|-------------|
| `AGENTCUBE_CONTROL_PLANE_URL` | Required. Router or API base URL. |
| `AGENTCUBE_NAMESPACE` | Namespace for sessions (default `default`). |
| `AGENTCUBE_BEARER_TOKEN` | Optional JWT / API token. |
| `OPENAI_API_KEY` | Optional; without it, planner/reporter use deterministic fallbacks. |
| `OPENAI_MODEL` | Optional OpenAI model id (default `gpt-4o-mini`). |
| `PCAP_SFTP_HOST`, `PCAP_SFTP_USER`, `PCAP_SFTP_PASSWORD`, `PCAP_SFTP_PATH`, `PCAP_SFTP_PORT` | Optional SFTP staging instead of interpreter upload. |

## Run

```bash
export AGENTCUBE_CONTROL_PLANE_URL=https://your-router.example.com
uvicorn pcap_analyzer:app --host 0.0.0.0 --port 8080
```

## Call `/analyze`

Multipart form fields:

- `goal` (string): what you want extracted from the PCAP.
- `file` (file): the `.pcap` / `.pcapng` upload **or**
- `pcap_b64` (string): base64-encoded capture.
- `use_sftp` (bool): when true, writes via Paramiko SFTP to `PCAP_SFTP_PATH` and analyzes that remote path (interpreter must reach the same filesystem, e.g. shared volume).

Example with curl:

```bash
curl -sS -X POST "http://127.0.0.1:8080/analyze" \
  -F 'goal=List TLS SNI hosts if visible' \
  -F 'file=@/path/to/capture.pcap'
```

The JSON body contains `plan`, `raw` (structured command output), and `report`.
