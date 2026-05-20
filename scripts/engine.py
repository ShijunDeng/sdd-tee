#!/usr/bin/env python3
"""
SDD-TEE v5.1 Benchmark Engine

Drives the full 8-stage SDD workflow (ST-0 to ST-7) for each AR,
with accurate per-stage token tracking via LiteLLM Proxy.

Token data flow:
  1. Engine starts LiteLLM Proxy (or uses existing one)
  2. For each AR × stage: adapter runs CLI tool, CLI routes through proxy
  3. Engine records stage start/end timestamps
  4. Auditor filters LiteLLM JSONL log by time window → exact per-stage tokens
  5. Output is a schema-compliant _full.json with real token data

Usage:
  # Run with LiteLLM proxy (recommended — accurate token data)
  python3 scripts/engine.py --tool claude-code --model claude-sonnet-4 \
    --api-base http://localhost:4000 --specs-dir specs/

  # Run without proxy (token data depends on CLI tool native support)
  python3 scripts/engine.py --tool claude-code --model claude-sonnet-4 \
    --specs-dir specs/

  # Test with single AR (no real API calls)
  python3 scripts/engine.py --tool claude-code --model claude-sonnet-4 \
    --ar-limit 1 --dry-run-prompts
"""

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# ─── Setup paths ──────────────────────────────────────────────────────────

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE / "scripts"))

from schema import STAGES
from auditor import TokenAuditor, get_pricing, compute_token_cost
from equivalence import EquivalenceChecker, EquivalenceResult

# ─── AR catalog ───────────────────────────────────────────────────────────

# Import from report.py (the canonical source of AR catalog)
_mod = __import__("report")
AR_CATALOG = _mod.AR_CATALOG

STAGE_NAMES_MAP = {
    "ST-0": "AR 输入",
    "ST-1": "需求澄清",
    "ST-2": "Spec 增量设计",
    "ST-3": "Design 增量设计",
    "ST-4": "任务拆解",
    "ST-5": "开发实现",
    "ST-6": "一致性验证",
    "ST-6.5": "原始代码等价性验证",
    "ST-7": "合并归档",
}

DEFAULT_ORIGINAL_REPO = "https://github.com/ShijunDeng/agentcube.git"

SOURCE_EXTS_BY_LANG = {
    "Go": {".go", ".mod", ".sum"},
    "Python": {".py", ".toml", ".txt", ".yaml", ".yml"},
    "YAML": {".yaml", ".yml"},
    "Dockerfile": {".dockerfile"},
    "Makefile": {".mk"},
    "TypeScript": {".ts", ".tsx", ".js", ".jsx", ".json", ".md", ".mdx"},
    "Markdown": {".md", ".mdx"},
}

SKIP_SCAN_DIRS = {
    ".git", "__pycache__", ".mypy_cache", "vendor", "node_modules",
    "agentcube-src", ".pytest_cache", ".opencode",
}

PLACEHOLDER_PATTERNS = [
    "TODO", "FIXME", "XXX", "NotImplementedError", "pass  #",
    "placeholder", "stub", "mock implementation", "dummy implementation",
    "panic(\"TODO", "panic(\"not implemented",
]

CHANGE_DOC_EXTS = {".md", ".yaml", ".yml", ".json", ".txt"}
CHANGE_DOC_NAMES = {".openspec.yaml", "README.md", "proposal.md", "delta-spec.md",
                    "design.md", "tasks.md", "implementation.md", "verification.md"}

SPEC_KEYWORDS_BY_MODULE = {
    "pkg/apis": ["project", "sandbox-orchestration", "deployment/client-go"],
    "pkg/workloadmanager": ["project", "sandbox-orchestration"],
    "pkg/router": ["project", "session-routing"],
    "pkg/store": ["project", "session-store"],
    "pkg/picod": ["project", "code-execution"],
    "pkg/agentd": ["project", "idle-cleanup"],
    "cmd/cli": ["project", "cli-toolkit"],
    "cmd": ["project", "cli-toolkit"],
    "sdk-python": ["project", "python-sdk"],
    "manifests": ["project", "deployment"],
    "docker": ["project", "deployment"],
    ".github": ["project", "ci-cd"],
    "client-go": ["project", "deployment/client-go"],
    "integrations": ["project", "integrations"],
    "example": ["project", "integrations"],
    "docs": ["project"],
}


# ─── Adapter factory ─────────────────────────────────────────────────────

from adapters.base import BaseAdapter, StageRecord
from adapters.claude_code import ClaudeCodeAdapter
from adapters.gemini_cli import GeminiCliAdapter
from adapters.cursor_cli import CursorCliAdapter
from adapters.opencode_cli import OpenCodeCliAdapter


def create_adapter(tool: str, model: str, api_base: Optional[str] = None) -> BaseAdapter:
    """Factory: create the right adapter for the given CLI tool."""
    factories = {
        "claude-code": lambda: ClaudeCodeAdapter(model, api_base),
        "gemini-cli": lambda: GeminiCliAdapter(model),
        "cursor-cli": lambda: CursorCliAdapter(model, api_base),
        "opencode-cli": lambda: OpenCodeCliAdapter(model),
    }
    if tool not in factories:
        raise ValueError(f"Unknown tool: {tool}. Supported: {', '.join(factories.keys())}")
    return factories[tool]()


def reconcile_stage_records(adapter, log_dir: str, stage_records: dict, ar_id: str) -> dict:
    """Re-parse all log files to get authoritative api_calls/iterations counts.

    This corrects any parser-induced inflation of call counts from the live run.
    Token values (input/output/cache) are preserved as-is since they were already
    correctly extracted — the bug only affected api_calls counting.
    """
    log_path = Path(log_dir)
    if not log_path.exists():
        return stage_records

    for stage_id, record in stage_records.items():
        if getattr(record, "data_source", "") == "litellm_proxy" or getattr(record, "attempts", 1) > 1:
            continue
        log_file = log_path / f"{ar_id}_{stage_id}.log"
        if not log_file.exists():
            continue

        log_text = log_file.read_text(encoding="utf-8")
        verified = adapter.parse_native_output(log_text)
        if verified.api_calls > 0:
            # Only update api_calls/iterations, preserve token values
            record.api_calls = verified.api_calls
            record.iterations = verified.api_calls

    return stage_records


# ─── Prompt builder ──────────────────────────────────────────────────────

def load_specs(specs_dir: str) -> dict:
    """Load all .md files from specs directory."""
    specs = Path(specs_dir)
    content = {}
    for sf in sorted(specs.rglob("*.md")):
        rel = str(sf.relative_to(specs))
        content[rel] = sf.read_text(encoding="utf-8", errors="replace")
    return content


def _spec_keywords_for_ar(ar: dict) -> list[str]:
    module = ar["module"].strip("/")
    matches = []
    for prefix, keywords in SPEC_KEYWORDS_BY_MODULE.items():
        if module == prefix or module.startswith(prefix + "/"):
            matches.extend(keywords)
            break
    if not matches:
        matches.append("project")
        leaf = module.split("/")[-1]
        if leaf:
            matches.append(leaf)
    if ar["type"] == "测试":
        matches.append("testing")
    return list(dict.fromkeys(matches))


def build_stage_prompt(ar: dict, stage_id: str, specs_content: dict, prev_outputs: dict,
                       original_snippets: str = "") -> str:
    """Build prompt for a specific AR × stage.

    Prompts reference the actual agentcube specs.
    """
    ar_desc = (
        f"AR: {ar['id']} — {ar['name']}\n"
        f"Module: {ar['module']}\n"
        f"Language: {ar['lang']}\n"
        f"Size: {ar['size']}"
    )

    # Find relevant specs. Do not match on generic language names such as
    # "Go"; that pulls unrelated specs like deployment/client-go into every
    # Go AR and corrupts the benchmark prompts.
    relevant = []
    keywords = _spec_keywords_for_ar(ar)
    for name, text in specs_content.items():
        name_lower = name.lower()
        if any(kw.lower() in name_lower for kw in keywords):
            relevant.append(f"--- {name} ---\n{text}")

    spec_ctx = "\n\n".join(relevant[:5]) if relevant else "(No directly matching specs)"
    change_dir = f"changes/{ar['id']}"
    previous_ctx = "\n\n".join(
        f"--- {name} ---\n{text[:6000]}" for name, text in prev_outputs.items() if text
    ) or "(No previous stage artifacts yet)"
    common = (
        "You are reconstructing the real open-source project agentcube from an empty workspace "
        "through a Specification-Driven Development benchmark.\n"
        "The Go module path MUST be `github.com/volcano-sh/agentcube`.\n"
        "This is an execution task, not a discussion. Use filesystem tools to write the requested files.\n"
        "Do not invent benchmark metrics, token counts, costs, or test results.\n"
        "Do not leave placeholders, TODOs, stubs, or empty implementations.\n"
        f"All SDD change artifacts for this AR must live under {change_dir}/.\n"
        f"The {change_dir}/ directory is for SDD documents only. Never write source code, packages, "
        f"tests, generated clients, or implementation trees under {change_dir}/. "
        f"Any source file under {change_dir}/ will be deleted and counted as a benchmark failure.\n"
    )

    prompts = {
        "ST-0": (
            f"{common}\n"
            f"Initialize a new OpenSpec change for the agentcube project:\n\n"
            f"{ar_desc}\n\n"
            f"Create this exact scaffold:\n"
            f"- {change_dir}/.openspec.yaml\n"
            f"- {change_dir}/README.md\n"
            f"- {change_dir}/changelog/entries.md\n\n"
            f"Do NOT write implementation code yet."
        ),
        "ST-1": (
            f"{common}\n"
            f"Write proposal.md for the agentcube project:\n\n"
            f"{ar_desc}\n\n"
            f"Relevant specs:\n{spec_ctx}\n\n"
            f"Write exactly: {change_dir}/proposal.md\n"
            f"Include: purpose, scope, impact analysis, alternatives considered, acceptance criteria."
        ),
        "ST-2": (
            f"{common}\n"
            f"Write delta-spec.md (GIVEN/WHEN/THEN scenarios) for the agentcube project:\n\n"
            f"{ar_desc}\n\n"
            f"Base specs:\n{spec_ctx}\n\n"
            f"Previous artifacts:\n{previous_ctx[:8000]}\n\n"
            f"Write exactly: {change_dir}/delta-spec.md\n"
            f"Use OpenSpec format. Each requirement must have acceptance scenarios."
        ),
        "ST-3": (
            f"{common}\n"
            f"Write design.md with technical implementation details for the agentcube project:\n\n"
            f"{ar_desc}\n\n"
            f"Specs:\n{spec_ctx}\n\n"
            f"Previous artifacts:\n{previous_ctx[:8000]}\n\n"
            f"Write exactly: {change_dir}/design.md\n"
            f"Include: architecture, data structures, API contracts, error handling, testing strategy."
        ),
        "ST-4": (
            f"{common}\n"
            f"Write tasks.md checklist for the agentcube project:\n\n"
            f"{ar_desc}\n\n"
            f"Previous artifacts:\n{previous_ctx[:8000]}\n\n"
            f"Write exactly: {change_dir}/tasks.md\n"
            f"Break into atomic, independently verifiable implementation and test tasks."
        ),
        "ST-5": (
            f"{common}\n"
            f"Implement ALL code for the agentcube project. Write COMPLETE, working code.\n\n"
            f"{ar_desc}\n\n"
            f"Previous SDD artifacts:\n{previous_ctx[:12000]}\n\n"
            f"ORIGINAL CODE REFERENCE (ground truth — match these interfaces and behaviors):\n"
            f"{original_snippets[:12000] if original_snippets else '(No original code available — follow specs strictly)'}\n\n"
            f"Target implementation area: {ar['module']}/ or the closest matching project path.\n"
            f"Implementation code MUST be written under the project root target paths, for example "
            f"`{ar['module']}/...`, not under `{change_dir}/`.\n"
            f"Do NOT create or modify source files outside `{ar['module']}/...` for this AR. "
            f"Only dependency metadata such as go.mod/go.sum may be adjusted outside the target module.\n"
            f"The `{change_dir}/` directory is only for SDD documents and notes.\n"
            f"Record what you changed in {change_dir}/implementation.md.\n\n"
            f"CRITICAL:\n"
            f"1. Write COMPLETE, working code — no placeholders, no TODOs, no stubs\n"
            f"2. Write unit tests for every component\n"
            f"3. Follow Go/Python best practices\n"
            f"4. Handle errors properly\n"
            f"5. You MUST use tool calls to WRITE files to disk\n"
            f"6. Match the original code's API contracts, function signatures, and behavior\n"
            f"7. Do not report completion unless files were actually created or modified"
        ),
        "ST-6": (
            f"{common}\n"
            f"Verify implementation against spec for the agentcube project:\n\n"
            f"{ar_desc}\n\n"
            f"Spec:\n{spec_ctx[:3000]}\n\n"
            f"Write exactly: {change_dir}/verification.md\n"
            f"Check: Are all requirements met? Are tests passing?\n"
            f"Do NOT run shell commands. The benchmark harness runs local checks separately. "
            f"Inspect the files already in the workspace and write a concise verification report with explicit unknowns. "
            f"Do not fabricate passing tests."
        ),
        "ST-6.5": (
            f"Compare your generated code against the original agentcube source code.\n\n"
            f"{ar_desc}\n\n"
            f"Report:\n"
            f"1. Which original files have corresponding generated files?\n"
            f"2. Are all function signatures and API endpoints preserved?\n"
            f"3. Are there any behavioral differences?\n"
            f"4. What is missing or different?\n\n"
            f"Output a brief equivalence report."
        ),
        "ST-7": (
            f"{common}\n"
            f"Archive change for the agentcube project:\n\n"
            f"{ar_desc}\n\n"
            f"Append archive notes to {change_dir}/changelog/entries.md and update {change_dir}/README.md.\n"
            f"Do NOT modify project source code during archive.\n"
            f"Summarize: What was completed, what was deferred, and validation status."
        ),
    }
    return prompts.get(stage_id, f"Process {stage_id} for {ar_desc}")


def _is_source_like(path: Path, lang: str) -> bool:
    name = path.name
    suffix = path.suffix.lower()
    if name in {"Dockerfile", "Makefile", "requirements.txt", "pyproject.toml"}:
        return True
    if name.startswith("Dockerfile.") or suffix == ".dockerfile":
        return True
    return suffix in SOURCE_EXTS_BY_LANG.get(lang, {".go", ".py", ".yaml", ".yml", ".md"})


def _is_project_implementation_file(rel: str, path: Path, lang: str) -> bool:
    if rel.startswith("changes/"):
        return False
    if rel in {"go.mod", "go.sum", "requirements.txt", "pyproject.toml"}:
        return False
    if not _is_source_like(path, lang):
        return False
    suffix = path.suffix.lower()
    name = path.name
    if lang == "Go":
        return suffix == ".go" or name in {"go.mod", "go.sum"}
    if lang == "Python":
        return suffix == ".py"
    if lang == "YAML":
        return suffix in {".yaml", ".yml"}
    if lang == "Dockerfile":
        return name == "Dockerfile" or name.startswith("Dockerfile.") or suffix == ".dockerfile"
    if lang == "Makefile":
        return name == "Makefile" or suffix == ".mk"
    if lang == "TypeScript":
        return suffix in {".ts", ".tsx", ".js", ".jsx", ".json"}
    if lang == "Markdown":
        return suffix in {".md", ".mdx"}
    return True


def _snapshot_workspace(workspace: Path, lang: str) -> dict[str, dict]:
    """Return hash/LOC snapshot for generated files in the workspace."""
    snap: dict[str, dict] = {}
    for dirpath, dirnames, filenames in os.walk(workspace):
        dirnames[:] = [d for d in dirnames if d not in SKIP_SCAN_DIRS]
        for fn in filenames:
            path = Path(dirpath) / fn
            rel = str(path.relative_to(workspace))
            if rel == ".sdd_prompt.md" or rel.startswith("specs/"):
                continue
            if not _is_source_like(path, lang) and not rel.startswith("changes/"):
                continue
            try:
                data = path.read_bytes()
            except OSError:
                continue
            text = data.decode("utf-8", errors="replace")
            snap[rel] = {
                "hash": hashlib.sha256(data).hexdigest(),
                "loc": len(text.splitlines()),
                "source": _is_source_like(path, lang),
                "implementation": _is_project_implementation_file(rel, path, lang),
                "data": data,
            }
    return snap


def _snapshot_delta(before: dict[str, dict], after: dict[str, dict]) -> dict:
    added = [p for p in after if p not in before]
    modified = [p for p in after if p in before and after[p]["hash"] != before[p]["hash"]]
    changed = sorted(added + modified)
    source_changed = [p for p in changed if after[p].get("source")]
    implementation_changed = [p for p in changed if after[p].get("implementation")]
    loc_delta = 0
    for p in implementation_changed:
        old_loc = before.get(p, {}).get("loc", 0)
        loc_delta += max(0, after[p]["loc"] - old_loc)
    return {
        "added": sorted(added),
        "modified": sorted(modified),
        "changed": changed,
        "source_changed": sorted(source_changed),
        "implementation_changed": sorted(implementation_changed),
        "loc_delta": loc_delta,
    }


def _restore_workspace_files(workspace: Path, before: dict[str, dict], rel_files: list[str]) -> int:
    restored = 0
    for rel in rel_files:
        path = workspace / rel
        if rel in before:
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(before[rel]["data"])
                restored += 1
            except OSError:
                pass
        else:
            try:
                path.unlink()
                restored += 1
            except FileNotFoundError:
                restored += 1
            except OSError:
                pass
    return restored


def _forbidden_change_source_files(ar: dict, rel_files: list[str]) -> list[str]:
    prefix = f"changes/{ar['id']}/"
    forbidden: list[str] = []
    for rel in rel_files:
        if not rel.startswith(prefix):
            continue
        name = Path(rel).name
        suffix = Path(rel).suffix.lower()
        if name in CHANGE_DOC_NAMES or suffix in CHANGE_DOC_EXTS:
            continue
        forbidden.append(rel)
    return sorted(forbidden)


def _in_scope_implementation_files(ar: dict, rel_files: list[str]) -> tuple[list[str], list[str]]:
    module = ar["module"].strip("/")
    in_scope: list[str] = []
    out_scope: list[str] = []
    for rel in rel_files:
        if not module or module == "root":
            ok = "/" not in rel
        elif module.startswith("."):
            ok = rel == module or rel.startswith(module + "/")
        else:
            ok = rel == module or rel.startswith(module + "/")
        if ok:
            in_scope.append(rel)
        else:
            out_scope.append(rel)
    return sorted(in_scope), sorted(out_scope)


def _loc_delta_for_files(before: dict[str, dict], after: dict[str, dict], rel_files: list[str]) -> int:
    total = 0
    for rel in rel_files:
        if rel not in after:
            continue
        old_loc = before.get(rel, {}).get("loc", 0)
        total += max(0, after[rel]["loc"] - old_loc)
    return total


def _read_stage_artifacts(workspace: Path, ar_id: str) -> dict[str, str]:
    change_dir = workspace / "changes" / ar_id
    files = {
        "proposal.md": change_dir / "proposal.md",
        "delta-spec.md": change_dir / "delta-spec.md",
        "design.md": change_dir / "design.md",
        "tasks.md": change_dir / "tasks.md",
        "implementation.md": change_dir / "implementation.md",
        "verification.md": change_dir / "verification.md",
    }
    out = {}
    for name, path in files.items():
        if path.exists():
            out[name] = path.read_text(encoding="utf-8", errors="replace")
    return out


def _validate_stage_output(
    workspace: Path,
    ar: dict,
    stage_id: str,
    delta: dict,
    in_scope_impl: list[str] | None = None,
    out_scope_impl: list[str] | None = None,
    scoped_loc_delta: int | None = None,
) -> list[str]:
    """Detect empty stages, missing artifacts, and hollow implementations."""
    errors: list[str] = []
    change_dir = workspace / "changes" / ar["id"]
    required = {
        "ST-0": [change_dir / ".openspec.yaml", change_dir / "README.md"],
        "ST-1": [change_dir / "proposal.md"],
        "ST-2": [change_dir / "delta-spec.md"],
        "ST-3": [change_dir / "design.md"],
        "ST-4": [change_dir / "tasks.md"],
        "ST-5": [change_dir / "implementation.md"],
        "ST-6": [change_dir / "verification.md"],
        "ST-7": [change_dir / "changelog" / "entries.md"],
    }
    for path in required.get(stage_id, []):
        if not path.exists():
            errors.append(f"missing required artifact: {path.relative_to(workspace)}")
        elif path.stat().st_size < 80:
            errors.append(f"artifact too small: {path.relative_to(workspace)}")

    if stage_id in {"ST-0", "ST-1", "ST-2", "ST-3", "ST-4", "ST-6", "ST-7"} and not delta["changed"]:
        errors.append("no files were created or modified")

    if stage_id == "ST-5":
        source_changed = in_scope_impl if in_scope_impl is not None else delta["implementation_changed"]
        out_scope = out_scope_impl if out_scope_impl is not None else []
        loc_delta = scoped_loc_delta if scoped_loc_delta is not None else delta["loc_delta"]
        if out_scope:
            errors.append(
                "implementation modified files outside target module "
                f"{ar['module']}: " + ", ".join(out_scope[:10])
            )
        if not source_changed:
            errors.append("implementation stage did not create or modify project source files outside changes/")
        min_loc = 10 if ar["type"] in {"测试"} else min(30, max(10, ar.get("est_loc", 50) // 6))
        if loc_delta < min_loc:
            errors.append(f"implementation LOC delta below minimum: {loc_delta} < {min_loc}")

        placeholder_hits = _scan_placeholder_hits(workspace, source_changed + out_scope)
        if placeholder_hits:
            preview = ", ".join(placeholder_hits[:5])
            errors.append(f"placeholder/stub markers found: {preview}")

    return errors


def _scan_placeholder_hits(workspace: Path, rel_files: list[str]) -> list[str]:
    hits = []
    for rel in rel_files:
        path = workspace / rel
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            lower = line.lower()
            for pat in PLACEHOLDER_PATTERNS:
                if pat.lower() in lower:
                    hits.append(f"{rel}:{lineno}:{pat}")
                    break
    return hits


def _run_local_checks(workspace: Path, ar: dict) -> list[dict]:
    """Run bounded, deterministic checks for the AR module."""
    checks: list[dict] = []

    cmd: list[str] | None = None
    if ar["lang"] == "Go":
        module = ar["module"].strip("/")
        cmd = ["go", "test", f"./{module}/..."] if module else ["go", "test", "./..."]
    elif ar["lang"] == "Python":
        module = ar["module"].strip("/")
        if (workspace / module).exists():
            cmd = [sys.executable, "-m", "compileall", "-q", module]
    elif ar["lang"] in {"YAML", "Dockerfile", "Makefile", "Markdown", "TypeScript"}:
        cmd = None

    if cmd:
        start = time.time()
        try:
            result = subprocess.run(
                cmd,
                cwd=workspace,
                capture_output=True,
                text=True,
                timeout=90,
            )
            checks.append({
                "command": " ".join(cmd),
                "exit_code": result.returncode,
                "duration_seconds": round(time.time() - start, 2),
                "stdout": result.stdout[-4000:],
                "stderr": result.stderr[-4000:],
            })
        except subprocess.TimeoutExpired as e:
            out = e.output or ""
            err = e.stderr or ""
            if isinstance(out, bytes):
                out = out.decode("utf-8", errors="replace")
            if isinstance(err, bytes):
                err = err.decode("utf-8", errors="replace")
            checks.append({
                "command": " ".join(cmd),
                "exit_code": "timeout",
                "duration_seconds": 90,
                "stdout": out[-4000:],
                "stderr": err[-4000:],
            })

    return checks


def _write_programmatic_verification(
    workspace: Path,
    ar: dict,
    reasons: list[str],
    checks: list[dict] | None = None,
) -> list[dict]:
    """Write an honest fallback verification artifact."""
    change_dir = workspace / "changes" / ar["id"]
    change_dir.mkdir(parents=True, exist_ok=True)
    if checks is None:
        checks = _run_local_checks(workspace, ar)

    lines = [
        f"# Verification Report — {ar['id']}",
        "",
        "Generated by the benchmark harness because model-driven ST-6 verification did not produce a valid artifact.",
        "",
        "## Model Verification Failure",
    ]
    for reason in reasons:
        lines.append(f"- {reason}")
    lines.extend(["", "## Local Checks"])
    if checks:
        for check in checks:
            lines.append(f"- Command: `{check['command']}`")
            lines.append(f"  - Exit code: `{check['exit_code']}`")
            lines.append(f"  - Duration: `{check['duration_seconds']}s`")
            if check.get("stdout"):
                lines.extend(["", "```text", check["stdout"].rstrip(), "```"])
            if check.get("stderr"):
                lines.extend(["", "```text", check["stderr"].rstrip(), "```"])
    else:
        lines.append("- No bounded local check is configured for this AR language/module.")

    lines.extend([
        "",
        "## Result",
        "This report is a fallback verification artifact. It must not be treated as a model-authored pass.",
        "",
    ])
    (change_dir / "verification.md").write_text("\n".join(lines), encoding="utf-8")
    return checks


def _failed_local_checks(checks: list[dict]) -> list[str]:
    failed: list[str] = []
    for check in checks:
        exit_code = check.get("exit_code")
        if exit_code not in (0, "0"):
            failed.append(f"{check.get('command', '<unknown>')} exit={exit_code}")
    return failed


def _write_programmatic_archive(workspace: Path, ar: dict, reasons: list[str]) -> None:
    change_dir = workspace / "changes" / ar["id"]
    changelog = change_dir / "changelog" / "entries.md"
    readme = change_dir / "README.md"
    changelog.parent.mkdir(parents=True, exist_ok=True)
    note = [
        "",
        "## Harness Archive Fallback",
        "",
        "Model-driven archive did not complete cleanly. The benchmark harness recorded this fallback instead.",
        "",
        "Reasons:",
    ]
    note.extend(f"- {reason}" for reason in reasons)
    note.extend([
        "",
        f"AR: {ar['id']} — {ar['name']}",
        f"Module: {ar['module']}",
        "",
    ])
    with changelog.open("a", encoding="utf-8") as f:
        f.write("\n".join(note))
    if readme.exists():
        with readme.open("a", encoding="utf-8") as f:
            f.write("\n".join(note))
    else:
        readme.write_text("\n".join([f"# {ar['id']} {ar['name']}"] + note), encoding="utf-8")


def _merge_stage_record(total: StageRecord, part: StageRecord) -> StageRecord:
    total.input_tokens += part.input_tokens
    total.output_tokens += part.output_tokens
    total.cache_read_tokens += part.cache_read_tokens
    total.cache_write_tokens += part.cache_write_tokens
    total.iterations += part.iterations
    total.api_calls += part.api_calls
    total.cost_usd += part.cost_usd
    total.duration_seconds += part.duration_seconds
    total.attempts += max(0, part.attempts)
    if part.error:
        total.error = part.error if not total.error else f"{total.error}; {part.error}"
    if part.data_source != "none":
        total.data_source = part.data_source
    if part.exit_code is not None:
        total.exit_code = part.exit_code
    return total


def _stage_timeout(stage_id: str) -> int:
    if stage_id == "ST-5":
        return 900
    if stage_id == "ST-6":
        return 180
    if stage_id == "ST-7":
        return 180
    return 420


def _repair_prompt(ar: dict, stage_id: str, original_prompt: str, errors: list[str]) -> str:
    return (
        f"The previous attempt for {ar['id']} {stage_id} failed benchmark validation.\n"
        f"Validation errors:\n- " + "\n- ".join(errors) + "\n\n"
        f"Fix the workspace now. You must write the missing or incomplete files to disk. "
        f"Do not provide a narrative-only answer.\n\n"
        f"Important: `changes/{ar['id']}/` is only for SDD markdown/yaml artifacts. "
        f"Do not write any .go/.py/source implementation files under `changes/{ar['id']}/`. "
        f"Implementation source belongs under `{ar['module']}/...` at the project root.\n\n"
        f"Original instructions:\n{original_prompt}"
    )


# ─── Engine ───────────────────────────────────────────────────────────────

def run_benchmark(
    tool: str,
    model: str,
    specs_dir: str,
    api_base: Optional[str] = None,
    ar_limit: Optional[int] = None,
    ar_offset: int = 0,
    dry_run_prompts: bool = False,
    original_repo: Optional[str] = None,
) -> dict:
    """Execute the SDD-TEE benchmark.

    Args:
        tool: CLI tool name (claude-code, gemini-cli, cursor-cli, opencode-cli).
        model: Model identifier.
        specs_dir: Path to specs directory.
        api_base: LiteLLM Proxy URL (e.g. http://localhost:4000).
        ar_limit: Only run N ARs (for testing).
        ar_offset: Skip the first N ARs before applying ar_limit.
        dry_run_prompts: Print prompts without executing (testing only).
        original_repo: Path or URL to original agentcube source for equivalence verification.

    Returns:
        Complete results dict matching SDD-TEE schema.
    """
    # Setup
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_id = f"{tool}_{model.replace('/', '-')}_{ts}"
    workspace = BASE / "workspaces" / "v5.1" / run_id
    log_dir = BASE / "results" / "runs" / "v5.1" / f"{run_id}_logs"
    workspace.mkdir(parents=True, exist_ok=True)
    log_dir.mkdir(parents=True, exist_ok=True)

    # Always try to use the original agentcube source as the verification baseline.
    # This benchmark is meant to reconstruct that project, so running without a
    # baseline silently produces weak quality data.
    if not original_repo:
        original_repo = os.environ.get("SDD_TEE_ORIGINAL_REPO", DEFAULT_ORIGINAL_REPO)

    # Clone original repo if specified
    original_repo_path: Optional[Path] = None
    if original_repo:
        original_repo_path = _ensure_original_repo(original_repo, workspace)
        if original_repo_path:
            print(f"[OK] Original code reference: {original_repo_path}")

    # Copy specs to workspace
    specs_src = Path(specs_dir)
    if specs_src.exists():
        for item in specs_src.iterdir():
            if item.is_dir():
                dst = workspace / item.name
                if not dst.exists():
                    shutil.copytree(item, dst)
            else:
                shutil.copy2(item, workspace / item.name)

    # Limit ARs
    if ar_offset < 0:
        raise ValueError("--ar-offset must be >= 0")
    ars = AR_CATALOG[ar_offset:]
    if ar_limit:
        ars = ars[:ar_limit]

    print(f"\n{'='*70}")
    print(f"SDD-TEE v5.1 Benchmark: {tool} / {model}")
    print(f"Run ID:   {run_id}")
    print(f"Workspace: {workspace}")
    print(f"AR count: {len(ars)}")
    print(f"AR offset: {ar_offset}")
    print(f"Proxy:    {api_base or 'none (native only)'}")
    print(f"Dry run:  {dry_run_prompts}")
    print(f"Original: {original_repo or 'not specified'}")
    print(f"{'='*70}")

    # Init adapter + auditor
    adapter = create_adapter(tool, model, api_base)
    specs_content = load_specs(specs_dir)
    print(f"Loaded {len(specs_content)} spec files")

    # LiteLLM proxy log path
    litellm_log = BASE / "results" / "litellm_requests.jsonl"
    auditor = TokenAuditor(str(litellm_log)) if api_base else None

    run_start = time.time()
    ar_results = []
    _eq_result = EquivalenceResult()  # default

    for i, ar in enumerate(ars):
        print(f"\n  [{i+1}/{len(ars)}] {ar['id']} {ar['name']} ({ar['size']})")
        ar_start = time.time()
        prev_outputs = {}
        stage_records = {}

        # Gather original code snippets for this AR's module (for ST-5 prompt)
        original_snippets = ""
        if original_repo_path:
            original_snippets = _gather_original_snippets(original_repo_path, ar["module"], ar["lang"])

        for stage_id in STAGES:
            # ST-6.5 is programmatic verification, not a CLI stage
            if stage_id == "ST-6.5":
                stage_name = STAGE_NAMES_MAP[stage_id]
                if original_repo_path and not dry_run_prompts:
                    print(f"    {stage_id}: running equivalence check...")
                    eq_start = time.time()
                    checker = EquivalenceChecker(
                        str(original_repo_path), str(workspace), ar["lang"]
                    )
                    eq_result = checker.verify(
                        ar_id=ar["id"],
                        ar_module=ar["module"],
                        module_filter=ar["module"].split("/")[-1],
                    )
                    eq_end = time.time()
                    rec = StageRecord(stage=stage_id, stage_name=stage_name)
                    rec.duration_seconds = eq_end - eq_start
                    rec.data_source = "equivalence_check"
                    if eq_result.notes:
                        rec.validation_errors = [eq_result.notes]
                        rec.error = eq_result.notes
                    # Store equivalence result for quality metrics
                    _eq_result = eq_result
                    print(
                        f"      Coverage: {eq_result.file_coverage_pct}% | "
                        f"API: {eq_result.api_compliance_pct}% | "
                        f"Similarity: {eq_result.line_similarity_pct}% | "
                        f"Score: {eq_result.overall_score}"
                    )
                else:
                    rec = StageRecord(stage=stage_id, stage_name=STAGE_NAMES_MAP[stage_id])
                    rec.data_source = "none" if not original_repo_path else "dry_run"
                    _eq_result = EquivalenceResult()
                    if dry_run_prompts:
                        print(f"    [DRY] {stage_id}: skipped (no original repo in dry-run)")
                stage_records[stage_id] = rec
                prev_outputs[stage_id] = f"[Stage {stage_id} completed]"
                continue

            prompt = build_stage_prompt(ar, stage_id, specs_content, prev_outputs, original_snippets)
            log_file = log_dir / f"{ar['id']}_{stage_id}.log"
            stage_name = STAGE_NAMES_MAP[stage_id]

            if dry_run_prompts:
                print(f"    [DRY] {stage_id}: prompt length={len(prompt)}")
                rec = StageRecord(stage=stage_id, stage_name=stage_name)
                rec.data_source = "dry_run"
            else:
                print(f"    {stage_id}: executing...")
                stage_start = time.time()
                before_stage = _snapshot_workspace(workspace, ar["lang"])
                rec = StageRecord(stage=stage_id, stage_name=stage_name)
                rec.attempts = 0
                validation_errors: list[str] = []
                stage_restored_files = 0
                stage_out_of_scope_files: set[str] = set()

                # Run CLI tool and one repair attempt if required artifacts are
                # missing. This keeps hollow runs visible and gives the agent one
                # realistic chance to correct its work, with all tokens counted.
                current_prompt = prompt
                max_stage_attempts = 1 if stage_id == "ST-6" else 2
                for attempt in range(1, max_stage_attempts + 1):
                    attempt_log = log_file if attempt == 1 else log_dir / f"{ar['id']}_{stage_id}.attempt{attempt}.log"
                    part = adapter.run(
                        prompt=current_prompt,
                        workspace=str(workspace),
                        log_path=str(attempt_log),
                        stage=stage_id,
                        stage_name=stage_name,
                        timeout=_stage_timeout(stage_id),
                        max_retries=1,
                    )
                    part.attempts = 1
                    _merge_stage_record(rec, part)

                    after_attempt = _snapshot_workspace(workspace, ar["lang"])
                    delta = _snapshot_delta(before_stage, after_attempt)
                    forbidden_change_sources = _forbidden_change_source_files(
                        ar, delta["source_changed"]
                    )
                    forbidden_error = ""
                    if forbidden_change_sources:
                        _restore_workspace_files(workspace, before_stage, forbidden_change_sources)
                        after_attempt = _snapshot_workspace(workspace, ar["lang"])
                        delta = _snapshot_delta(before_stage, after_attempt)
                        forbidden_error = (
                            "source files written under changes/ and restored: "
                            + ", ".join(forbidden_change_sources[:10])
                        )
                    in_scope_impl, out_scope_impl = _in_scope_implementation_files(
                        ar, delta["implementation_changed"]
                    )
                    if stage_id == "ST-5" and out_scope_impl:
                        stage_out_of_scope_files.update(out_scope_impl)
                        stage_restored_files += _restore_workspace_files(
                            workspace, before_stage, out_scope_impl
                        )
                        after_attempt = _snapshot_workspace(workspace, ar["lang"])
                        delta = _snapshot_delta(before_stage, after_attempt)
                        in_scope_impl, _ = _in_scope_implementation_files(
                            ar, delta["implementation_changed"]
                        )
                    scoped_loc_delta = _loc_delta_for_files(
                        before_stage, after_attempt, in_scope_impl
                    )
                    validation_errors = _validate_stage_output(
                        workspace, ar, stage_id, delta,
                        in_scope_impl=in_scope_impl,
                        out_scope_impl=out_scope_impl,
                        scoped_loc_delta=scoped_loc_delta,
                    )
                    if forbidden_error:
                        validation_errors.append(forbidden_error)
                    if not validation_errors:
                        break
                    if attempt >= max_stage_attempts:
                        break
                    print(f"      validation failed; repair attempt {attempt}: {'; '.join(validation_errors[:3])}")
                    current_prompt = _repair_prompt(ar, stage_id, prompt, validation_errors)

                stage_end = time.time()
                rec.duration_seconds = stage_end - stage_start
                after_stage = _snapshot_workspace(workspace, ar["lang"])
                delta = _snapshot_delta(before_stage, after_stage)
                forbidden_change_sources = _forbidden_change_source_files(
                    ar, delta["source_changed"]
                )
                forbidden_error = ""
                forbidden_restored = 0
                if forbidden_change_sources:
                    forbidden_restored = _restore_workspace_files(workspace, before_stage, forbidden_change_sources)
                    after_stage = _snapshot_workspace(workspace, ar["lang"])
                    delta = _snapshot_delta(before_stage, after_stage)
                    forbidden_error = (
                        "source files written under changes/ and restored: "
                        + ", ".join(forbidden_change_sources[:10])
                    )
                in_scope_impl, out_scope_impl = _in_scope_implementation_files(
                    ar, delta["implementation_changed"]
                )
                if stage_id == "ST-5" and out_scope_impl:
                    stage_out_of_scope_files.update(out_scope_impl)
                    stage_restored_files += _restore_workspace_files(
                        workspace, before_stage, out_scope_impl
                    )
                    after_stage = _snapshot_workspace(workspace, ar["lang"])
                    delta = _snapshot_delta(before_stage, after_stage)
                    in_scope_impl, out_scope_impl = _in_scope_implementation_files(
                        ar, delta["implementation_changed"]
                    )
                scoped_loc_delta = _loc_delta_for_files(before_stage, after_stage, in_scope_impl)
                non_impl_source_changes: list[str] = []
                if stage_id != "ST-5" and delta["implementation_changed"]:
                    non_impl_source_changes = delta["implementation_changed"]
                    rec.restored_files = _restore_workspace_files(
                        workspace, before_stage, non_impl_source_changes
                    )
                    after_stage = _snapshot_workspace(workspace, ar["lang"])
                    delta = _snapshot_delta(before_stage, after_stage)
                    in_scope_impl, out_scope_impl = _in_scope_implementation_files(
                        ar, delta["implementation_changed"]
                    )
                    scoped_loc_delta = _loc_delta_for_files(before_stage, after_stage, in_scope_impl)
                rec.changed_files = len(delta["changed"])
                rec.source_changed_files = len(in_scope_impl)
                rec.out_of_scope_files = max(len(out_scope_impl), len(stage_out_of_scope_files))
                rec.added_files = len(delta["added"])
                rec.restored_files += forbidden_restored + stage_restored_files
                rec.loc_delta = scoped_loc_delta
                if non_impl_source_changes:
                    validation_errors.append(
                        "project source modified outside ST-5 and restored: "
                        + ", ".join(non_impl_source_changes[:8])
                    )
                if forbidden_error:
                    validation_errors.append(forbidden_error)
                if stage_id == "ST-6" and any("verification.md" in e for e in validation_errors):
                    checks = _run_local_checks(workspace, ar)
                    checks = _write_programmatic_verification(workspace, ar, validation_errors, checks)
                    rec.local_checks = checks
                    after_stage = _snapshot_workspace(workspace, ar["lang"])
                    delta = _snapshot_delta(before_stage, after_stage)
                    validation_errors = [
                        "model verification failed; harness generated verification.md"
                    ]
                if stage_id == "ST-6":
                    if not rec.local_checks:
                        rec.local_checks = _run_local_checks(workspace, ar)
                    local_failures = _failed_local_checks(rec.local_checks)
                    if local_failures:
                        validation_errors.append(
                            "local checks failed: " + "; ".join(local_failures[:3])
                        )
                if stage_id == "ST-7" and validation_errors:
                    _write_programmatic_archive(workspace, ar, validation_errors)
                    after_stage = _snapshot_workspace(workspace, ar["lang"])
                    delta = _snapshot_delta(before_stage, after_stage)
                    validation_errors = [
                        "model archive failed; harness generated archive notes"
                    ]
                in_scope_impl, out_scope_impl = _in_scope_implementation_files(
                    ar, delta["implementation_changed"]
                )
                rec.changed_files = len(delta["changed"])
                rec.source_changed_files = len(in_scope_impl)
                rec.out_of_scope_files = max(len(out_scope_impl), len(stage_out_of_scope_files))
                rec.added_files = len(delta["added"])
                rec.loc_delta = _loc_delta_for_files(before_stage, after_stage, in_scope_impl)
                rec.validation_errors = validation_errors
                if validation_errors:
                    msg = "validation failed: " + "; ".join(validation_errors)
                    rec.error = msg if not rec.error else f"{rec.error}; {msg}"

                # ─── Authoritative: audit LiteLLM proxy log ───
                if auditor and api_base:
                    proxy_audit = auditor.get_tokens(model, stage_start, stage_end)
                    if proxy_audit.api_calls > 0:
                        # Overwrite native data with proxy data (authoritative)
                        rec.input_tokens = proxy_audit.input_tokens
                        rec.output_tokens = proxy_audit.output_tokens
                        rec.cache_read_tokens = proxy_audit.cache_read_tokens
                        rec.cache_write_tokens = proxy_audit.cache_write_tokens
                        rec.cost_usd = proxy_audit.compute_cost(model)
                        rec.api_calls = proxy_audit.api_calls
                        rec.iterations = proxy_audit.api_calls
                        rec.data_source = "litellm_proxy"
                        print(
                            f"      [Proxy] in={proxy_audit.input_tokens:,} "
                            f"out={proxy_audit.output_tokens:,} "
                            f"cache={proxy_audit.cache_read_tokens:,} "
                            f"calls={proxy_audit.api_calls}"
                        )

                if rec.error:
                    print(f"      WARNING: {rec.error}")
                print(
                    f"      changed={rec.changed_files} added={rec.added_files} "
                    f"loc_delta={rec.loc_delta} attempts={rec.attempts}"
                )

            stage_records[stage_id] = rec
            artifacts = _read_stage_artifacts(workspace, ar["id"])
            prev_outputs = artifacts or prev_outputs

        ar_end = time.time()

        # ─── Reconcile: re-parse logs to correct api_calls ────────────────
        if not dry_run_prompts:
            reconcile_stage_records(adapter, str(log_dir), stage_records, ar["id"])

        # ─── Compute AR totals ────────────────────────────────────────────
        totals = {
            "input_tokens": sum(r.input_tokens for r in stage_records.values()),
            "output_tokens": sum(r.output_tokens for r in stage_records.values()),
            "cache_read_tokens": sum(r.cache_read_tokens for r in stage_records.values()),
            "cache_write_tokens": sum(r.cache_write_tokens for r in stage_records.values()),
            "total_tokens": sum(
                r.input_tokens + r.output_tokens + r.cache_read_tokens + r.cache_write_tokens
                for r in stage_records.values()
            ),
            "human_input_tokens": 0,
            "spec_context_tokens": 0,
            "iterations": sum(r.iterations for r in stage_records.values()),
            "duration_seconds": round(ar_end - ar_start, 2),
            "api_calls": sum(r.api_calls for r in stage_records.values()),
            "cost_usd": 0.0,
        }

        # Compute cost from real pricing
        if any(r.cost_usd for r in stage_records.values()):
            totals["cost_usd"] = round(sum(r.cost_usd for r in stage_records.values()), 4)
        else:
            totals["cost_usd"] = round(
                compute_token_cost(
                    model,
                    totals["input_tokens"],
                    totals["output_tokens"],
                    totals["cache_read_tokens"],
                    totals["cache_write_tokens"],
                ),
                4,
            )

        # Physical LOC scan. Per-AR output is the implementation-stage delta,
        # not cumulative workspace LOC, to avoid counting earlier ARs again.
        workspace_loc, workspace_files = _scan_loc(workspace, ar["lang"])
        st5_record = stage_records.get("ST-5", StageRecord())
        actual_loc = st5_record.loc_delta
        actual_files = st5_record.source_changed_files

        # Quality metrics from equivalence check, adjusted by benchmark
        # validation failures. Equivalence is cumulative within a workspace, so
        # a nearly-empty AR can appear equivalent because earlier ARs already
        # generated files in the same module. Implementation-stage validation
        # must therefore cap the per-AR quality score.
        eq_data = _eq_result if '_eq_result' in dir() else EquivalenceResult()
        st5_errors = stage_records.get("ST-5", StageRecord()).validation_errors or []
        st6_errors = stage_records.get("ST-6", StageRecord()).validation_errors or []
        all_validation_errors = [
            err
            for record in stage_records.values()
            for err in (record.validation_errors or [])
        ]
        local_check_failed = any("local checks failed" in e for e in st6_errors)
        implementation_failed = bool(st5_errors)
        model_verification_failed = any("model verification failed" in e for e in st6_errors)
        consistency_score = eq_data.overall_score / 100 if eq_data.overall_score > 0 else 0
        code_usability = eq_data.api_compliance_pct / 100 if eq_data.api_compliance_pct > 0 else 0
        if implementation_failed:
            consistency_score = min(consistency_score, 0.25)
            code_usability = min(code_usability, 0.25)
        if local_check_failed:
            consistency_score = min(consistency_score, 0.2)
            code_usability = 0
        elif model_verification_failed:
            consistency_score = min(consistency_score, 0.8)
        quality = {
            "consistency_score": consistency_score,
            "consistency_pct": round(consistency_score * 100, 2),
            "code_usability": code_usability,
            "test_coverage": 0,  # Requires running actual tests
            "bugs_found": 0,
            "implementation_valid": not implementation_failed,
            "local_checks_passed": not local_check_failed,
            "validation_error_count": len(all_validation_errors),
            "critical_validation_errors": st5_errors + [
                e for e in st6_errors if "local checks failed" in e or "model verification failed" in e
            ],
            "original_code_coverage": eq_data.file_coverage_pct,
            "api_contract_compliance": eq_data.api_compliance_pct,
            "line_similarity": eq_data.line_similarity_pct,
            "matched_files": len(eq_data.matched_files),
            "unmatched_original": len(eq_data.unmatched_original),
            "module_path_match": getattr(eq_data, "module_path_match", True),
            "original_module_path": getattr(eq_data, "original_module_path", ""),
            "generated_module_path": getattr(eq_data, "generated_module_path", ""),
            "equivalence_notes": getattr(eq_data, "notes", ""),
        }

        ar_result = {
            "ar_id": ar["id"],
            "ar_name": ar["name"],
            "module": ar["module"],
            "lang": ar["lang"],
            "type": ar["type"],
            "size": ar["size"],
            "stages": {
                k: {
                    "input_tokens": v.input_tokens,
                    "output_tokens": v.output_tokens,
                    "cache_read_tokens": v.cache_read_tokens,
                    "cache_write_tokens": v.cache_write_tokens,
                    "total_tokens": (
                        v.input_tokens + v.output_tokens
                        + v.cache_read_tokens + v.cache_write_tokens
                    ),
                    "human_input_tokens": 0,
                    "spec_context_tokens": 0,
                    "iterations": v.iterations,
                    "duration_seconds": round(v.duration_seconds, 2),
                    "api_calls": v.api_calls,
                    "cost_usd": round(v.cost_usd, 6),
                    "data_source": v.data_source,
                    "exit_code": v.exit_code,
                    "attempts": v.attempts,
                    "changed_files": v.changed_files,
                    "source_changed_files": v.source_changed_files,
                    "added_files": v.added_files,
                    "restored_files": v.restored_files,
                    "out_of_scope_files": v.out_of_scope_files,
                    "loc_delta": v.loc_delta,
                    "validation_errors": v.validation_errors,
                    "local_checks": v.local_checks,
                    "error": v.error,
                }
                for k, v in stage_records.items()
            },
            "totals": totals,
            "output": {
                "actual_loc": actual_loc,
                "actual_files": actual_files,
                "workspace_loc": workspace_loc,
                "workspace_files": workspace_files,
                "tasks_count": ar.get("est_tasks", 0),
            },
            "quality": quality,
            "metrics": {},
        }
        ar_result["metrics"] = _compute_ar_metrics(ar_result)
        ar_results.append(ar_result)

        print(
            f"  AR totals: {totals['total_tokens']:,} tokens, "
            f"{actual_loc} LOC, {actual_files} files"
        )

    # ─── Aggregate ────────────────────────────────────────────────────────
    total_duration = time.time() - run_start

    grand = {
        "ar_count": len(ar_results),
        "input_tokens": sum(r["totals"]["input_tokens"] for r in ar_results),
        "output_tokens": sum(r["totals"]["output_tokens"] for r in ar_results),
        "cache_read_tokens": sum(r["totals"]["cache_read_tokens"] for r in ar_results),
        "cache_write_tokens": sum(r["totals"]["cache_write_tokens"] for r in ar_results),
        "total_tokens": sum(r["totals"]["total_tokens"] for r in ar_results),
        "human_input_tokens": sum(r["totals"]["human_input_tokens"] for r in ar_results),
        "spec_context_tokens": sum(r["totals"]["spec_context_tokens"] for r in ar_results),
        "total_duration_seconds": round(total_duration, 2),
        "total_cost_usd": round(sum(r["totals"]["cost_usd"] for r in ar_results), 4),
        "total_cost_cny": round(sum(r["totals"]["cost_usd"] for r in ar_results) * 7.2, 4),
        "total_loc": sum(r["output"]["actual_loc"] for r in ar_results),
        "total_files": sum(r["output"]["actual_files"] for r in ar_results),
        "total_tasks": sum(r["output"]["tasks_count"] for r in ar_results),
        "total_iterations": sum(r["totals"]["iterations"] for r in ar_results),
        "total_api_calls": sum(r["totals"]["api_calls"] for r in ar_results),
    }

    stage_agg = {}
    for sid in STAGES:
        stage_agg[sid] = {
            "name": STAGE_NAMES_MAP[sid],
            "total_tokens": sum(r["stages"][sid]["total_tokens"] for r in ar_results),
            "input_tokens": sum(r["stages"][sid]["input_tokens"] for r in ar_results),
            "output_tokens": sum(r["stages"][sid]["output_tokens"] for r in ar_results),
            "cache_read_tokens": sum(r["stages"][sid]["cache_read_tokens"] for r in ar_results),
            "cache_write_tokens": sum(r["stages"][sid]["cache_write_tokens"] for r in ar_results),
            "duration_seconds": round(sum(r["stages"][sid]["duration_seconds"] for r in ar_results), 2),
            "iterations": sum(r["stages"][sid]["iterations"] for r in ar_results),
            "api_calls": sum(r["stages"][sid]["api_calls"] for r in ar_results),
            "cost_usd": round(sum(r["stages"][sid].get("cost_usd", 0.0) for r in ar_results), 4),
        }

    baselines = _compute_baselines(ar_results)

    data = {
        "meta": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "is_mock": dry_run_prompts,
            "framework": "SDD-TEE v5.1",
            "methodology": "CodeSpec 7-Stage + OpenSpec OPSX + LiteLLM Proxy",
            "target_project": "agentcube",
            "tool": tool,
            "model": model,
            "run_id": run_id,
            "ar_offset": ar_offset,
            "token_tracking": "LiteLLM Proxy per-request audit (authoritative) + native CLI parsing (fallback)",
            "litellm_proxy": api_base is not None,
            "api_base": api_base,
            "data_integrity": "All token data from real API responses. No fabrication.",
        },
        "ar_catalog": AR_CATALOG,
        "ar_results": ar_results,
        "grand_totals": grand,
        "stage_aggregates": stage_agg,
        "baselines": baselines,
    }

    # Save
    output_dir = BASE / "results" / "runs" / "v5.1"
    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / f"{run_id}_full.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"\n{'='*70}")
    print(f"Run complete: {run_id}")
    print(f"  Total tokens: {grand['total_tokens']:,}")
    print(f"  Total cost:   ${grand['total_cost_usd']:.4f}")
    print(f"  Total LOC:    {grand['total_loc']:,}")
    print(f"  Duration:     {total_duration/60:.1f}m")
    print(f"  Saved → {out_path}")
    print(f"{'='*70}")

    return data


def _scan_loc(workspace: Path, lang: str) -> tuple[int, int]:
    """Scan workspace for generated code files (exclude vendor, cache, agentcube-src)."""
    loc = 0
    files = 0

    for dirpath, dirnames, filenames in os.walk(workspace):
        # Prune skip dirs
        dirnames[:] = [d for d in dirnames if d not in SKIP_SCAN_DIRS and d != "changes"]
        for fn in filenames:
            fpath = Path(dirpath) / fn
            if not _is_source_like(fpath, lang):
                continue
            try:
                with open(fpath, errors="replace") as f:
                    loc += sum(1 for _ in f)
                files += 1
            except (OSError, UnicodeDecodeError):
                pass
    return loc, files


def _compute_ar_metrics(ar: dict) -> dict:
    """Compute 5-dimension metrics for one AR."""
    stages = ar["stages"]
    totals = ar["totals"]
    out = ar["output"]
    quality = ar.get("quality", {})

    st5 = stages.get("ST-5", {}).get("total_tokens", 0)
    total = totals["total_tokens"]
    loc = max(out["actual_loc"], 1)
    nf = max(out["actual_files"], 1)
    tasks = max(out["tasks_count"], 1)
    dur_h = max(totals["duration_seconds"] / 3600, 0.001)

    # Quality metrics: derive from quality dict, not from raw token counts
    # When no equivalence check ran, all quality fields are 0 → set metrics to 0 (unmeasured)
    has_quality = quality.get("consistency_score", 0) > 0 or quality.get("test_coverage", 0) > 0
    if has_quality:
        qt_cov = round(quality.get("test_coverage", 0) * 100, 2)
        qt_consist = round(quality.get("consistency_score", 0) * 100, 2)
        qt_avail = round(quality.get("code_usability", 0) * 100, 2)
        qt_bug = round(max(0, 100 - quality.get("consistency_score", 0) * 100), 2)
    else:
        qt_cov = 0
        qt_consist = 0
        qt_avail = 0
        qt_bug = 0  # Not measured, not "100 bugs found"

    return {
        "ET_LOC": round(st5 / loc, 2),
        "ET_FILE": round(st5 / nf, 2),
        "ET_TASK": round(st5 / tasks, 2),
        "ET_AR": round(total, 2),
        "ET_TIME": round(total / dur_h, 2),
        "ET_COST_LOC": round(totals["cost_usd"] / (loc / 1000), 2) if loc > 0 else 0,
        "RT_RATIO": 0,  # Requires human input tracking
        "RT_ITER": round(totals["iterations"], 2),
        "QT_COV": qt_cov,
        "QT_CONSIST": qt_consist,
        "QT_AVAIL": qt_avail,
        "QT_BUG": qt_bug,
        "PT_DESIGN": round(
            sum(stages.get(s, {}).get("total_tokens", 0) for s in ["ST-1", "ST-2", "ST-3"])
            / max(total, 1), 4
        ),
        "PT_PLAN": round(
            sum(stages.get(s, {}).get("total_tokens", 0) for s in ["ST-0", "ST-4"])
            / max(total, 1), 4
        ),
        "PT_DEV": round(st5 / max(total, 1), 4),
        "PT_VERIFY": round(
            sum(stages.get(s, {}).get("total_tokens", 0) for s in ["ST-6", "ST-7"])
            / max(total, 1), 4
        ),
    }


def _compute_baselines(ar_results: list) -> dict:
    """Compute size-stratified baselines."""
    groups = {"S": [], "M": [], "L": []}
    for ar in ar_results:
        size = ar["size"]
        if size in groups:
            groups[size].append(ar.get("metrics", {}))

    result = {}
    for size, metrics_list in groups.items():
        if not metrics_list:
            result[size] = {"count": 0}
            continue
        result[size] = {"count": len(metrics_list)}
        for key in metrics_list[0]:
            vals = [m[key] for m in metrics_list if isinstance(m.get(key), (int, float))]
            if vals:
                result[size][f"{key}_mean"] = round(sum(vals) / len(vals), 2)
                result[size][f"{key}_min"] = round(min(vals), 2)
                result[size][f"{key}_max"] = round(max(vals), 2)
    return result


# ─── Original code helpers ─────────────────────────────────────────────

def _ensure_original_repo(original_repo: str, workspace: Path) -> Optional[Path]:
    """Ensure original agentcube source is available outside the generated workspace.

    Supports:
    - Local path: returns the path directly
    - Git URL: clones/updates a cache under .cache/original/agentcube

    Returns path to original source, or None if unavailable.
    """
    # Local path
    local = Path(original_repo)
    if local.exists() and local.is_dir():
        return local.resolve()

    # Git URL — try to clone
    if original_repo.startswith(("http://", "https://", "git@")):
        cache_root = BASE / ".cache" / "original"
        target = cache_root / "agentcube"
        if target.exists():
            return target
        try:
            cache_root.mkdir(parents=True, exist_ok=True)
            subprocess.run(
                ["git", "clone", "--depth", "1", original_repo, str(target)],
                check=True, timeout=120, capture_output=True,
            )
            return target
        except Exception as e:
            print(f"[WARN] Could not clone original repo: {e}")
            return None

    print(f"[WARN] Original repo path/URL not found: {original_repo}")
    return None


def _gather_original_snippets(original_path: Path, module: str, lang: str) -> str:
    """Extract relevant code snippets from original source for a given module.

    Returns formatted text with file paths and content.
    """
    module_kw = module.lower().split("/")[-1]
    exts = {".go"} if lang == "Go" else {".py"}

    snippets = []
    for dirpath, dirnames, filenames in os.walk(original_path):
        dirnames[:] = [d for d in dirnames if d not in {
            ".git", "__pycache__", "vendor", "node_modules", ".pytest_cache",
        }]
        rel_dir = str(Path(dirpath).relative_to(original_path)).lower()

        # Only grab files related to the module
        if module_kw not in rel_dir and module_kw not in dirpath.lower():
            # Still check filenames
            pass

        for fn in filenames:
            ext = os.path.splitext(fn)[1]
            if ext not in exts:
                continue
            if module_kw not in fn.lower() and module_kw not in rel_dir:
                continue

            fpath = Path(dirpath) / fn
            try:
                content = fpath.read_text(encoding="utf-8", errors="replace")
                rel = fpath.relative_to(original_path)
                # Limit per-file size
                if len(content) > 3000:
                    content = content[:3000] + "\n... (truncated)"
                snippets.append(f"--- {rel} ---\n{content}")
            except OSError:
                pass

    if not snippets:
        # Fallback: grab all source files (up to 10)
        all_files = []
        for dirpath, dirnames, filenames in os.walk(original_path):
            dirnames[:] = [d for d in dirnames if d not in {
                ".git", "__pycache__", "vendor", "node_modules",
            }]
            for fn in filenames:
                ext = os.path.splitext(fn)[1]
                if ext in exts:
                    all_files.append(Path(dirpath) / fn)

        for fpath in all_files[:10]:
            try:
                content = fpath.read_text(encoding="utf-8", errors="replace")[:3000]
                rel = fpath.relative_to(original_path)
                snippets.append(f"--- {rel} ---\n{content}")
            except OSError:
                pass

    return "\n\n".join(snippets) if snippets else ""


# ─── Main ─────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="SDD-TEE v5.1 Benchmark Engine")
    parser.add_argument("--tool", required=True,
                        choices=["claude-code", "gemini-cli", "cursor-cli", "opencode-cli"],
                        help="CLI tool to benchmark")
    parser.add_argument("--model", required=True, help="Model identifier")
    parser.add_argument("--api-base", default=None,
                        help="LiteLLM Proxy URL (e.g. http://localhost:4000)")
    parser.add_argument("--specs-dir", default=str(BASE / "specs"),
                        help="Directory containing SDD spec files")
    parser.add_argument("--ar-limit", type=int, default=None,
                        help="Only run first N ARs (for testing)")
    parser.add_argument("--ar-offset", type=int, default=0,
                        help="Skip the first N ARs before applying --ar-limit")
    parser.add_argument("--dry-run-prompts", action="store_true",
                        help="Print prompts without executing CLI tools (testing)")
    parser.add_argument("--original-repo", default=None,
                        help="Path or URL to original agentcube source for equivalence verification")
    args = parser.parse_args()

    run_benchmark(
        tool=args.tool,
        model=args.model,
        specs_dir=args.specs_dir,
        api_base=args.api_base,
        ar_limit=args.ar_limit,
        ar_offset=args.ar_offset,
        dry_run_prompts=args.dry_run_prompts,
        original_repo=args.original_repo,
    )


if __name__ == "__main__":
    main()
