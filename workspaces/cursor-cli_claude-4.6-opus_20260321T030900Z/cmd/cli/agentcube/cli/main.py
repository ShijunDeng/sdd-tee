"""Typer entrypoint for AgentCube CLI."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, Any

import typer
from rich.console import Console
from rich.traceback import install as rich_traceback_install

from agentcube import __version__
from agentcube.runtime import (
    BuildRuntime,
    InvokeRuntime,
    PackRuntime,
    PublishRuntime,
    StatusRuntime,
)

app = typer.Typer(
    name="kubectl-agentcube",
    help="AgentCube — pack, build, publish, and invoke agents.",
    no_args_is_help=True,
)
console = Console()
state: dict[str, Any] = {"verbose": False}


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(__version__)
        raise typer.Exit()


@app.callback()
def main(
    version: Annotated[
        bool,
        typer.Option("--version", callback=_version_callback, is_eager=True, help="Print version and exit."),
    ] = False,
    verbose: Annotated[bool, typer.Option("--verbose", "-v", help="Enable verbose logging.")] = False,
) -> None:
    """Global options."""
    state["verbose"] = verbose
    if verbose:
        rich_traceback_install(show_locals=False)


def _merge_verbose(cmd_verbose: bool) -> bool:
    return bool(state.get("verbose") or cmd_verbose)


@app.command()
def pack(
    workspace: Annotated[Path, typer.Option("--workspace", "-f", help="Agent workspace root.")] = Path("."),
    provider: Annotated[
        str | None,
        typer.Option("--provider", help="Reserved for future remote pack targets."),
    ] = None,
    verbose: Annotated[bool, typer.Option("--verbose", "-v", help="Verbose output for this command.")] = False,
    name: Annotated[str, typer.Option("--name", help="Agent name.")] = "agent",
    version: Annotated[str, typer.Option("--agent-version", help="Initial semver version.")] = "0.1.0",
    description: Annotated[str, typer.Option("--description", help="Short description.")] = "",
    author: Annotated[str, typer.Option("--author", help="Author or team.")] = "",
    base_image: Annotated[str, typer.Option("--base-image", help="Base image for generated Dockerfile.")] = "python:3.11-slim",
    port: Annotated[int, typer.Option("--port", help="Container listen port.")] = 8080,
    namespace: Annotated[str, typer.Option("--namespace", help="Default Kubernetes namespace.")] = "default",
) -> None:
    """Generate Dockerfile (if missing) and agent_metadata.yaml."""
    rt = PackRuntime()
    opts: dict[str, Any] = {
        "name": name,
        "version": version,
        "description": description,
        "author": author,
        "base_image": base_image,
        "port": port,
        "namespace": namespace,
    }
    if provider:
        opts["labels"] = {"pack_provider": provider}
    result = rt.pack(workspace, **opts)
    if _merge_verbose(verbose):
        console.print_json(data=result)
    else:
        console.print(f"[green]Packed[/green] {result['workspace']}")


@app.command()
def build(
    workspace: Annotated[Path, typer.Option("--workspace", "-f", help="Agent workspace root.")] = Path("."),
    provider: Annotated[
        str | None,
        typer.Option("--provider", help="Build backend hint (default: local docker)."),
    ] = None,
    verbose: Annotated[bool, typer.Option("--verbose", "-v", help="Verbose output for this command.")] = False,
    image_prefix: Annotated[str | None, typer.Option("--image-prefix", help="Image repository prefix.")] = None,
    tag_as_latest: Annotated[bool, typer.Option("--tag-latest", help="Also tag image as latest.")] = False,
) -> None:
    """Build container image and bump patch version."""
    rt = BuildRuntime()
    opts: dict[str, Any] = {"tag_as_latest": tag_as_latest}
    if image_prefix:
        opts["image_prefix"] = image_prefix
    if provider:
        opts["provider"] = provider
    result = rt.build(workspace, **opts)
    if _merge_verbose(verbose):
        console.print_json(data={k: v for k, v in result.items() if k != "logs"})
        for line in result.get("logs", []):
            console.print(line)
    else:
        console.print(f"[green]Built[/green] {result['image']} ({result['version']})")


@app.command()
def publish(
    provider: Annotated[str, typer.Option("--provider", help="Publish target: agentcube | k8s.")],
    workspace: Annotated[Path, typer.Option("--workspace", "-f", help="Agent workspace root.")] = Path("."),
    verbose: Annotated[bool, typer.Option("--verbose", "-v", help="Verbose output for this command.")] = False,
    wait: Annotated[bool, typer.Option("--wait/--no-wait", help="Wait for Deployment ready (k8s).")] = True,
    kube_context: Annotated[str | None, typer.Option("--kube-context", help="Kubeconfig context.")] = None,
) -> None:
    """Publish to AgentRuntime CR or Kubernetes Deployment."""
    rt = PublishRuntime()
    result = rt.publish(workspace, provider=provider, wait=wait, kube_context=kube_context)
    if _merge_verbose(verbose):
        console.print_json(data=result)
    else:
        console.print(f"[green]Published[/green] via {result['provider']}")


@app.command()
def invoke(
    workspace: Annotated[Path, typer.Option("--workspace", "-f", help="Agent workspace root.")] = Path("."),
    provider: Annotated[
        str | None,
        typer.Option("--provider", help="Optional routing hint (stored in payload metadata only)."),
    ] = None,
    verbose: Annotated[bool, typer.Option("--verbose", "-v", help="Verbose output for this command.")] = False,
    payload: Annotated[str | None, typer.Option("--payload", "-p", help="JSON body as string.")] = None,
    payload_file: Annotated[Path | None, typer.Option("--payload-file", help="JSON file for body.")] = None,
) -> None:
    """POST a JSON payload to the configured agent endpoint."""
    body: dict[str, Any]
    if payload_file:
        body = json.loads(payload_file.read_text(encoding="utf-8"))
    elif payload:
        body = json.loads(payload)
    else:
        body = {"input": ""}
    if provider:
        body.setdefault("_meta", {})["provider"] = provider
    rt = InvokeRuntime()
    try:
        out = rt.invoke(workspace, body)
    except Exception as exc:  # noqa: BLE001
        console.print(f"[red]Invoke failed:[/red] {exc}")
        raise typer.Exit(code=1) from exc
    if _merge_verbose(verbose):
        console.print_json(data=out if isinstance(out, dict) else {"result": out})
    else:
        console.print(out)


@app.command()
def status(
    workspace: Annotated[Path, typer.Option("--workspace", "-f", help="Agent workspace root.")] = Path("."),
    provider: Annotated[str | None, typer.Option("--provider", help="agentcube | k8s (default: from metadata).")] = None,
    verbose: Annotated[bool, typer.Option("--verbose", "-v", help="Verbose output for this command.")] = False,
) -> None:
    """Show deployment status for the workspace agent."""
    rt = StatusRuntime()
    try:
        result = rt.get_status(workspace, provider=provider)
    except Exception as exc:  # noqa: BLE001
        console.print(f"[red]Status failed:[/red] {exc}")
        raise typer.Exit(code=1) from exc
    if _merge_verbose(verbose):
        console.print_json(data=result)
    else:
        console.print_json(data=result)


if __name__ == "__main__":
    app()
