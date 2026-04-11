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
from auditor import TokenAuditor, get_pricing
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

    # Find relevant specs
    relevant = []
    for name, text in specs_content.items():
        mod_kw = ar["module"].lower().split("/")[-1]
        lang_kw = ar["lang"].lower()
        name_lower = name.lower()
        if mod_kw in name_lower or lang_kw in name_lower:
            relevant.append(f"--- {name} ---\n{text}")

    spec_ctx = "\n\n".join(relevant[:5]) if relevant else "(No directly matching specs)"

    prompts = {
        "ST-0": (
            f"Initialize a new OpenSpec change for the agentcube project:\n\n"
            f"{ar_desc}\n\n"
            f"Create the change directory scaffold under changes/{ar['id']}/.\n"
            f"Do NOT write code yet."
        ),
        "ST-1": (
            f"Write proposal.md for the agentcube project:\n\n"
            f"{ar_desc}\n\n"
            f"Relevant specs:\n{spec_ctx}\n\n"
            f"Include: purpose, scope, impact analysis, alternatives considered."
        ),
        "ST-2": (
            f"Write delta-spec.md (GIVEN/WHEN/THEN scenarios) for the agentcube project:\n\n"
            f"{ar_desc}\n\n"
            f"Base specs:\n{spec_ctx}\n\n"
            f"Use OpenSpec format. Each requirement must have acceptance scenarios."
        ),
        "ST-3": (
            f"Write design.md with technical implementation details for the agentcube project:\n\n"
            f"{ar_desc}\n\n"
            f"Specs:\n{spec_ctx}\n\n"
            f"Previous proposal:\n{prev_outputs.get('ST-1', 'N/A')[:3000]}\n\n"
            f"Include: architecture, data structures, API contracts, error handling, testing strategy."
        ),
        "ST-4": (
            f"Write tasks.md checklist for the agentcube project:\n\n"
            f"{ar_desc}\n\n"
            f"Design:\n{prev_outputs.get('ST-3', 'N/A')[:3000]}\n\n"
            f"Break into atomic, independently verifiable tasks."
        ),
        "ST-5": (
            f"Implement ALL code for the agentcube project. Write COMPLETE, working code.\n\n"
            f"{ar_desc}\n\n"
            f"Tasks:\n{prev_outputs.get('ST-4', 'N/A')[:3000]}\n\n"
            f"Design:\n{prev_outputs.get('ST-3', 'N/A')[:3000]}\n\n"
            f"ORIGINAL CODE REFERENCE (ground truth — match these interfaces and behaviors):\n"
            f"{original_snippets[:5000] if original_snippets else '(No original code available — follow specs strictly)'}\n\n"
            f"CRITICAL:\n"
            f"1. Write COMPLETE, working code — no placeholders, no TODOs, no stubs\n"
            f"2. Write unit tests for every component\n"
            f"3. Follow Go/Python best practices\n"
            f"4. Handle errors properly\n"
            f"5. You MUST use tool calls to WRITE files to disk\n"
            f"6. Match the original code's API contracts, function signatures, and behavior\n"
            f"7. Do NOT copy original code verbatim — implement from specs using original as reference"
        ),
        "ST-6": (
            f"Verify implementation against spec for the agentcube project:\n\n"
            f"{ar_desc}\n\n"
            f"Spec:\n{spec_ctx[:3000]}\n\n"
            f"Check: Are all requirements met? Are tests passing?\n"
            f"If original code is available, also verify API contracts and behavior match."
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
            f"Archive change for the agentcube project:\n\n"
            f"{ar_desc}\n\n"
            f"Summarize: What was completed, what was deferred."
        ),
    }
    return prompts.get(stage_id, f"Process {stage_id} for {ar_desc}")


# ─── Engine ───────────────────────────────────────────────────────────────

def run_benchmark(
    tool: str,
    model: str,
    specs_dir: str,
    api_base: Optional[str] = None,
    ar_limit: Optional[int] = None,
    dry_run_prompts: bool = False,
    original_repo: Optional[str] = None,
) -> dict:
    """Execute the SDD-TEE benchmark.

    Args:
        tool: CLI tool name (claude-code, gemini-cli, cursor-cli, opencode-cli).
        model: Model identifier.
        specs_dir: Path to specs directory.
        api_base: LiteLLM Proxy URL (e.g. http://localhost:4000).
        ar_limit: Only run first N ARs (for testing).
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
    ars = AR_CATALOG[:ar_limit] if ar_limit else AR_CATALOG

    print(f"\n{'='*70}")
    print(f"SDD-TEE v5.1 Benchmark: {tool} / {model}")
    print(f"Run ID:   {run_id}")
    print(f"Workspace: {workspace}")
    print(f"AR count: {len(ars)}")
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

                # Run CLI tool (routes through proxy if api_base set)
                rec = adapter.run(
                    prompt=prompt,
                    workspace=str(workspace),
                    log_path=str(log_file),
                    stage=stage_id,
                    stage_name=stage_name,
                )

                stage_end = time.time()
                rec.duration_seconds = stage_end - stage_start

                # ─── Authoritative: audit LiteLLM proxy log ───
                if auditor and api_base:
                    proxy_audit = auditor.get_tokens(model, stage_start, stage_end)
                    if proxy_audit.api_calls > 0:
                        # Overwrite native data with proxy data (authoritative)
                        rec.input_tokens = proxy_audit.input_tokens
                        rec.output_tokens = proxy_audit.output_tokens
                        rec.cache_read_tokens = proxy_audit.cache_read_tokens
                        rec.cache_write_tokens = proxy_audit.cache_write_tokens
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

            stage_records[stage_id] = rec
            prev_outputs[stage_id] = f"[Stage {stage_id} completed]"

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
            "total_tokens": sum(r.input_tokens + r.output_tokens for r in stage_records.values()),
            "human_input_tokens": 0,
            "spec_context_tokens": 0,
            "iterations": sum(r.iterations for r in stage_records.values()),
            "duration_seconds": round(ar_end - ar_start, 2),
            "api_calls": sum(r.api_calls for r in stage_records.values()),
            "cost_usd": 0.0,
        }

        # Compute cost from real pricing
        pricing = get_pricing(model)
        if pricing:
            net_in = max(0, totals["input_tokens"] - totals["cache_read_tokens"])
            totals["cost_usd"] = round(
                (net_in * pricing["input"] +
                 totals["output_tokens"] * pricing["output"] +
                 totals["cache_read_tokens"] * pricing["cache_read"] +
                 totals["cache_write_tokens"] * pricing["cache_write"]) / 1_000_000,
                4,
            )

        # Physical LOC scan
        actual_loc, actual_files = _scan_loc(workspace, ar["lang"])

        # Quality metrics from equivalence check
        eq_data = _eq_result if '_eq_result' in dir() else EquivalenceResult()
        quality = {
            "consistency_score": eq_data.overall_score,
            "code_usability": eq_data.api_compliance_pct / 100 if eq_data.api_compliance_pct > 0 else 0,
            "test_coverage": 0,  # Requires running actual tests
            "bugs_found": 0,
            "original_code_coverage": eq_data.file_coverage_pct,
            "api_contract_compliance": eq_data.api_compliance_pct,
            "line_similarity": eq_data.line_similarity_pct,
            "matched_files": len(eq_data.matched_files),
            "unmatched_original": len(eq_data.unmatched_original),
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
                    "total_tokens": v.input_tokens + v.output_tokens,
                    "human_input_tokens": 0,
                    "spec_context_tokens": 0,
                    "iterations": v.iterations,
                    "duration_seconds": round(v.duration_seconds, 2),
                    "api_calls": v.api_calls,
                    "data_source": v.data_source,
                }
                for k, v in stage_records.items()
            },
            "totals": totals,
            "output": {
                "actual_loc": actual_loc,
                "actual_files": actual_files,
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
    skip_dirs = {".git", "__pycache__", ".mypy_cache", "vendor", "node_modules", "agentcube-src", ".pytest_cache"}

    if lang == "Go":
        exts = {".go"}
    else:
        exts = {".py"}

    for dirpath, dirnames, filenames in os.walk(workspace):
        # Prune skip dirs
        dirnames[:] = [d for d in dirnames if d not in skip_dirs]
        for fn in filenames:
            ext = os.path.splitext(fn)[1]
            if ext in exts:
                fpath = os.path.join(dirpath, fn)
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
        "ET_LOC": round(total / loc, 2),
        "ET_FILE": round(total / nf, 2),
        "ET_TASK": round(total / tasks, 2),
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
    """Ensure original agentcube source is available in workspace.

    Supports:
    - Local path: copies if not already in workspace
    - Git URL: clones into workspace/original

    Returns path to original source, or None if unavailable.
    """
    target = workspace / "agentcube-src"

    # Already exists (from previous AR)
    if target.exists():
        return target

    # Local path
    local = Path(original_repo)
    if local.exists() and local.is_dir():
        # Copy into workspace
        try:
            shutil.copytree(local, target, symlinks=True, ignore=shutil.ignore_patterns(
                ".git", "__pycache__", "node_modules", "vendor", ".pytest_cache",
            ))
            return target
        except Exception as e:
            print(f"[WARN] Could not copy original repo: {e}")
            return None

    # Git URL — try to clone
    if original_repo.startswith(("http://", "https://", "git@")):
        try:
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
        dry_run_prompts=args.dry_run_prompts,
        original_repo=args.original_repo,
    )


if __name__ == "__main__":
    main()
