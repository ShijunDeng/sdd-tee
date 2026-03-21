"""
FastAPI service that uploads a PCAP into an AgentCube code interpreter, runs analysis
commands, and summarizes results with a small LangGraph planner/reporter flow.
"""

from __future__ import annotations

import base64
import json
import logging
import os
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Annotated, Any, TypedDict

import paramiko
import uvicorn
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import RunnableLambda
from langgraph.graph import END, StateGraph
from pydantic import BaseModel

from agentcube import CodeInterpreterClient

logger = logging.getLogger(__name__)


class AnalyzeResponse(BaseModel):
    """Structured HTTP response for ``/analyze``."""

    plan: str
    raw: dict[str, Any]
    report: str


class PCAPState(TypedDict, total=False):
    """LangGraph state for PCAP analysis."""

    goal: str
    remote_path: str
    plan: str
    raw_output: str
    report: str


@dataclass
class Settings:
    """Service configuration from environment variables."""

    control_plane_url: str = field(default_factory=lambda: os.environ.get("AGENTCUBE_CONTROL_PLANE_URL", ""))
    namespace: str = field(default_factory=lambda: os.environ.get("AGENTCUBE_NAMESPACE", "default"))
    bearer_token: str | None = field(default_factory=lambda: os.environ.get("AGENTCUBE_BEARER_TOKEN"))
    openai_model: str = field(default_factory=lambda: os.environ.get("OPENAI_MODEL", "gpt-4o-mini"))
    sftp_host: str | None = field(default_factory=lambda: os.environ.get("PCAP_SFTP_HOST"))
    sftp_user: str | None = field(default_factory=lambda: os.environ.get("PCAP_SFTP_USER"))
    sftp_password: str | None = field(default_factory=lambda: os.environ.get("PCAP_SFTP_PASSWORD"))
    sftp_path: str = field(default_factory=lambda: os.environ.get("PCAP_SFTP_PATH", "/tmp/uploads"))


SETTINGS = Settings()


def _auth_headers() -> dict[str, str]:
    if SETTINGS.bearer_token:
        return {"Authorization": f"Bearer {SETTINGS.bearer_token}"}
    return {}


class SandboxRunner:
    """Thin helper around ``CodeInterpreterClient`` for PCAP workflows."""

    def __init__(
        self,
        control_plane_url: str,
        namespace: str,
        *,
        headers: dict[str, str] | None = None,
    ) -> None:
        self._control_plane_url = control_plane_url.rstrip("/")
        self._namespace = namespace
        self._headers = dict(headers or {})

    def upload_bytes(self, remote_name: str, data: bytes) -> dict[str, Any]:
        """Write binary data into the remote workspace via the interpreter upload API."""
        with CodeInterpreterClient(
            self._control_plane_url,
            namespace=self._namespace,
            headers=self._headers,
        ) as client:
            path = f"/tmp/{remote_name}"
            return client.upload_file(path, data, filename=remote_name)

    def run_pipeline(self, remote_path: str) -> dict[str, Any]:
        """
        Run a conservative analysis pipeline (capinfos + optional tshark summary).

        Commands are chosen to fail softly if a binary is missing in the sandbox image.
        """
        out: dict[str, Any] = {}
        with CodeInterpreterClient(
            self._control_plane_url,
            namespace=self._namespace,
            headers=self._headers,
        ) as client:
            rc, combined = self._safe_command(
                client,
                f"capinfos -c -I -M '{remote_path}' 2>&1 || file '{remote_path}'",
            )
            out["capinfos_or_file"] = {"exit_code": rc, "output": combined}
            rc2, combined2 = self._safe_command(
                client,
                f"tshark -r '{remote_path}' -q -z io,stat,0 2>&1 | head -n 200",
            )
            out["tshark_summary"] = {"exit_code": rc2, "output": combined2}
        return out

    @staticmethod
    def _safe_command(client: CodeInterpreterClient, cmd: str) -> tuple[int, str]:
        try:
            data = client.execute_command(cmd)
        except Exception as exc:  # noqa: BLE001
            return -1, str(exc)
        stdout = str(data.get("stdout", data.get("output", "")))
        stderr = str(data.get("stderr", ""))
        exit_code = int(data.get("exitCode", data.get("exit_code", 0)))
        return exit_code, (stdout + ("\n" + stderr if stderr else "")).strip()


def _sftp_upload(filename: str, data: bytes) -> str:
    if not SETTINGS.sftp_host or not SETTINGS.sftp_user:
        raise RuntimeError("PCAP_SFTP_HOST and PCAP_SFTP_USER must be set for SFTP ingestion")
    transport = paramiko.Transport((SETTINGS.sftp_host, int(os.environ.get("PCAP_SFTP_PORT", "22"))))
    try:
        transport.connect(username=SETTINGS.sftp_user, password=SETTINGS.sftp_password or None)
        sftp = paramiko.SFTPClient.from_transport(transport)
        if sftp is None:
            raise RuntimeError("SFTP client initialization failed")
        remote = f"{SETTINGS.sftp_path.rstrip('/')}/{filename}"
        with sftp.file(remote, "wb") as remote_file:
            remote_file.write(data)
        return remote
    finally:
        transport.close()


def _llm_chain_planner(goal: str) -> str:
    key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not key:
        return (
            "1. Validate PCAP with capinfos or file(1).\n"
            "2. Summarize traffic with tshark statistics.\n"
            "3. Highlight anomalies based on the goal.\n"
            f"Goal: {goal}"
        )
    try:
        from langchain_openai import ChatOpenAI

        llm = ChatOpenAI(model=SETTINGS.openai_model, temperature=0)
        msg = llm.invoke(
            [
                SystemMessage(
                    content="You are a PCAP analysis planner. Reply with a short numbered plan only."
                ),
                HumanMessage(content=f"Goal:\n{goal}"),
            ]
        )
        return str(msg.content)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Planner LLM failed, using fallback: %s", exc)
        return f"Fallback plan due to LLM error: {exc}\nGoal: {goal}"


def _llm_chain_reporter(goal: str, plan: str, raw: str) -> str:
    key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not key:
        return (
            f"## Summary\nGoal: {goal}\n\n## Plan\n{plan}\n\n## Tool output (truncated)\n"
            f"{raw[:8000]}"
        )
    try:
        from langchain_openai import ChatOpenAI

        llm = ChatOpenAI(model=SETTINGS.openai_model, temperature=0.2)
        msg = llm.invoke(
            [
                SystemMessage(
                    content="You are a security analyst. Produce a concise markdown report from the data."
                ),
                HumanMessage(
                    content=f"Goal:\n{goal}\n\nPlan:\n{plan}\n\nRaw:\n{raw[:12000]}",
                ),
            ]
        )
        return str(msg.content)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Reporter LLM failed, using fallback: %s", exc)
        return f"Reporter fallback ({exc}):\n{raw[:8000]}"


def _build_graph(runner: SandboxRunner) -> StateGraph:
    def planner(state: PCAPState) -> PCAPState:
        plan = _llm_chain_planner(state.get("goal", ""))
        return {**state, "plan": plan}

    def run_tools(state: PCAPState) -> PCAPState:
        path = state.get("remote_path") or ""
        if not path:
            return {**state, "raw_output": "missing remote_path"}
        raw = runner.run_pipeline(path)
        return {**state, "raw_output": json.dumps(raw, indent=2, default=str)}

    def reporter(state: PCAPState) -> PCAPState:
        report = _llm_chain_reporter(
            state.get("goal", ""),
            state.get("plan", ""),
            state.get("raw_output", ""),
        )
        return {**state, "report": report}

    graph = StateGraph(PCAPState)
    graph.add_node("planner", RunnableLambda(planner))
    graph.add_node("run_tools", RunnableLambda(run_tools))
    graph.add_node("reporter", RunnableLambda(reporter))
    graph.set_entry_point("planner")
    graph.add_edge("planner", "run_tools")
    graph.add_edge("run_tools", "reporter")
    graph.add_edge("reporter", END)
    return graph


@asynccontextmanager
async def lifespan(app: FastAPI):
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))
    yield


app = FastAPI(
    title="AgentCube PCAP Analyzer",
    version="0.1.0",
    lifespan=lifespan,
)


@app.post("/analyze", response_model=AnalyzeResponse)
async def analyze(
    goal: Annotated[str, Form(description="What to look for in the capture")],
    file: Annotated[UploadFile | None, File(description="PCAP upload")] = None,
    pcap_b64: Annotated[str | None, Form(description="Base64-encoded PCAP")] = None,
    use_sftp: Annotated[bool, Form(description="Push bytes via SFTP instead of interpreter")] = False,
) -> AnalyzeResponse:
    if not SETTINGS.control_plane_url:
        raise HTTPException(status_code=500, detail="AGENTCUBE_CONTROL_PLANE_URL is not configured")

    raw_bytes: bytes | None = None
    filename = "capture.pcap"
    if file is not None:
        raw_bytes = await file.read()
        if file.filename:
            filename = os.path.basename(file.filename)
    elif pcap_b64:
        try:
            raw_bytes = base64.b64decode(pcap_b64, validate=True)
        except (ValueError, TypeError) as exc:
            raise HTTPException(status_code=400, detail=f"Invalid base64 PCAP: {exc}") from exc
    else:
        raise HTTPException(status_code=400, detail="Provide a PCAP file or pcap_b64")

    assert raw_bytes is not None

    runner = SandboxRunner(SETTINGS.control_plane_url, SETTINGS.namespace, headers=_auth_headers())

    if use_sftp:
        remote_path = _sftp_upload(filename, raw_bytes)
    else:
        runner.upload_bytes(filename, raw_bytes)
        remote_path = f"/tmp/{filename}"

    graph = _build_graph(runner).compile()
    final: PCAPState = graph.invoke(
        {
            "goal": goal,
            "remote_path": remote_path,
        }
    )

    raw_struct: dict[str, Any]
    try:
        raw_struct = json.loads(final.get("raw_output") or "{}")
    except json.JSONDecodeError:
        raw_struct = {"unparsed": final.get("raw_output", "")}

    return AnalyzeResponse(
        plan=final.get("plan", ""),
        raw=raw_struct,
        report=final.get("report", ""),
    )


def main() -> None:
    uvicorn.run(
        "pcap_analyzer:app",
        host=os.environ.get("HOST", "0.0.0.0"),
        port=int(os.environ.get("PORT", "8080")),
        factory=False,
    )


if __name__ == "__main__":
    main()
