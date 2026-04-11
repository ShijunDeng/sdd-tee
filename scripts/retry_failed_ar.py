#!/usr/bin/env python3
"""
Retry failed AR stages for an existing v5.1 benchmark run.

Identifies ARs with data_source=none stages and re-runs only those stages.
Updates the existing _full.json with the new data.

Usage:
    python3 scripts/retry_failed_ar.py --run-id <run_id> [--tool <tool>] [--model <model>]
    python3 scripts/retry_failed_ar.py --run-id opencode-cli_bailian-coding-plan-MiniMax-M2.5_20260410T163134Z

Options:
    --run-id         Run ID to retry (basename of _full.json without _full.json)
    --tool           CLI tool to use (default: from _full.json meta)
    --model          Model to use (default: from _full.json meta)
    --original-repo  Path to original repo for equivalence checking
    --ar-range       Only retry specific ARs, e.g. "AR-001,AR-005" (default: all failed)
    --stages         Only retry specific stages, e.g. "ST-5" (default: all failed stages)
"""

import argparse
import json
import logging
import sys
import time
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE / "scripts"))

from schema import STAGES
from auditor import get_pricing
from adapters.opencode_cli import OpenCodeCliAdapter
from adapters.claude_code import ClaudeCodeAdapter
from adapters.base import BaseAdapter, StageRecord
from engine import (
    build_stage_prompt, load_specs, _gather_original_snippets,
    reconcile_stage_records, create_adapter, STAGE_NAMES_MAP
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("retry")


def main():
    parser = argparse.ArgumentParser(description="Retry failed AR stages for a benchmark run")
    parser.add_argument("--run-id", required=True, help="Run ID (without _full.json suffix)")
    parser.add_argument("--tool", help="Override tool (default: from _full.json)")
    parser.add_argument("--model", help="Override model (default: from _full.json)")
    parser.add_argument("--original-repo", help="Path to original repo for eq check")
    parser.add_argument("--ar-range", help="Comma-separated AR IDs to retry (default: all failed)")
    parser.add_argument("--stages", help="Comma-separated stage IDs to retry (default: all failed)")
    args = parser.parse_args()

    runs_dir = BASE / "results" / "runs" / "v5.1"
    full_json_path = runs_dir / f"{args.run_id}_full.json"

    if not full_json_path.exists():
        log.error(f"Run file not found: {full_json_path}")
        sys.exit(1)

    # Load existing data
    with open(full_json_path) as f:
        data = json.load(f)

    tool = args.tool or data["meta"].get("tool", "opencode-cli")
    model = args.model or data["meta"].get("model", "")
    workspace = BASE / "workspaces" / "v5.1" / args.run_id
    log_dir = runs_dir / f"{args.run_id}_logs"

    log.info(f"Loading run: {args.run_id}")
    log.info(f"Tool: {tool}, Model: {model}")
    log.info(f"Workspace: {workspace}")
    log.info(f"Log dir: {log_dir}")

    # Parse ar-range / stages filters
    target_ars = None
    if args.ar_range:
        target_ars = {x.strip() for x in args.ar_range.split(",")}
    target_stages = None
    if args.stages:
        target_stages = {x.strip() for x in args.stages.split(",")}

    # Find failed stages per AR
    ar_results = data.get("ar_results", [])
    ar_catalog = {ar["id"]: ar for ar in data.get("ar_catalog", [])}
    specs_content = load_specs(str(BASE / "specs"))
    original_repo_path = args.original_repo

    adapter = create_adapter(tool, model, None)  # No proxy for retry

    total_retries = 0
    total_fixed = 0

    for ar in ar_results:
        ar_id = ar["ar_id"]

        # Skip if not in target ARs
        if target_ars and ar_id not in target_ars:
            continue

        # Merge catalog data for build_stage_prompt compatibility
        catalog = ar_catalog.get(ar_id, {})
        ar_for_prompt = {
            "id": ar_id,
            "name": ar.get("ar_name", catalog.get("name", "")),
            "module": ar.get("module", catalog.get("module", "")),
            "lang": ar.get("lang", catalog.get("lang", "Go")),
            "size": ar.get("size", catalog.get("size", "M")),
            "type": ar.get("type", catalog.get("type", "新功能")),
        }

        # Find failed stages
        failed_stages = []
        for stage_id in STAGES:
            stage = ar["stages"].get(stage_id, {})
            # A stage is "failed" if data_source=none and total_tokens=0 (and it's not ST-6.5)
            if stage_id == "ST-6.5":
                continue
            if stage.get("data_source") == "none" and stage.get("total_tokens", 0) == 0:
                if target_stages and stage_id not in target_stages:
                    continue
                failed_stages.append(stage_id)

        if not failed_stages:
            continue

        log.info(f"\n{'='*60}")
        log.info(f"Retrying {ar_id}: failed stages = {failed_stages}")
        log.info(f"{'='*60}")

        # Build previous stage outputs for context
        prev_outputs = {}
        for stage_id in STAGES:
            stage = ar["stages"].get(stage_id, {})
            if stage.get("total_tokens", 0) > 0 or stage.get("data_source") == "native_output":
                prev_outputs[stage_id] = f"[Stage {stage_id} completed]"

        # Gather original code snippets
        original_snippets = ""
        if original_repo_path:
            original_snippets = _gather_original_snippets(
                original_repo_path, ar.get("module", ""), ar.get("lang", "Go")
            )

        # Re-run each failed stage
        for stage_id in failed_stages:
            # For stages that depend on earlier stages, we need all previous stages' context
            # Build prev_outputs from all stages before this one that have data
            stage_prev_outputs = {}
            for prev_id in STAGES:
                if prev_id == stage_id or prev_id == "ST-6.5":
                    break
                prev_stage = ar["stages"].get(prev_id, {})
                if prev_stage.get("total_tokens", 0) > 0 or prev_stage.get("data_source") != "none":
                    stage_prev_outputs[prev_id] = f"[Stage {prev_id} completed]"

            prompt = build_stage_prompt(ar_for_prompt, stage_id, specs_content, stage_prev_outputs, original_snippets)
            log_file = log_dir / f"{ar_id}_{stage_id}.log"
            stage_name = STAGE_NAMES_MAP.get(stage_id, stage_id)

            log.info(f"  {stage_id}: executing (attempt 1 of 3 with backoff)...")
            stage_start = time.time()

            rec = adapter.run(
                prompt=prompt,
                workspace=str(workspace),
                log_path=str(log_file),
                stage=stage_id,
                stage_name=stage_name,
            )

            stage_end = time.time()
            rec.duration_seconds = stage_end - stage_start

            if rec.error:
                log.warning(f"  {stage_id}: FAILED - {rec.error}")
            else:
                total_tokens = rec.input_tokens + rec.output_tokens + rec.cache_read_tokens + rec.cache_write_tokens
                log.info(
                    f"  {stage_id}: done - "
                    f"in={rec.input_tokens:,} out={rec.output_tokens:,} "
                    f"cache_r={rec.cache_read_tokens:,} "
                    f"calls={rec.api_calls}, total={total_tokens:,}"
                )

            # Reconcile
            reconcile_stage_records(adapter, str(log_dir), {stage_id: rec}, ar_id)

            # Update AR result
            if rec.api_calls > 0:
                ar["stages"][stage_id] = {
                    "input_tokens": rec.input_tokens,
                    "output_tokens": rec.output_tokens,
                    "cache_read_tokens": rec.cache_read_tokens,
                    "cache_write_tokens": rec.cache_write_tokens,
                    "total_tokens": rec.input_tokens + rec.output_tokens,
                    "human_input_tokens": 0,
                    "spec_context_tokens": 0,
                    "iterations": rec.iterations,
                    "duration_seconds": round(rec.duration_seconds, 2),
                    "api_calls": rec.api_calls,
                    "data_source": rec.data_source,
                }
                total_fixed += 1
            total_retries += 1

        # Recompute AR totals
        total_input = sum(s.get("input_tokens", 0) for s in ar["stages"].values())
        total_output = sum(s.get("output_tokens", 0) for s in ar["stages"].values())
        total_cache_read = sum(s.get("cache_read_tokens", 0) for s in ar["stages"].values())
        total_cache_write = sum(s.get("cache_write_tokens", 0) for s in ar["stages"].values())
        total_iterations = sum(s.get("iterations", 0) for s in ar["stages"].values())
        total_api_calls = sum(s.get("api_calls", 0) for s in ar["stages"].values())

        ar["totals"] = {
            "input_tokens": total_input,
            "output_tokens": total_output,
            "cache_read_tokens": total_cache_read,
            "cache_write_tokens": total_cache_write,
            "total_tokens": total_input + total_output,
            "human_input_tokens": 0,
            "spec_context_tokens": 0,
            "iterations": total_iterations,
            "duration_seconds": ar["totals"].get("duration_seconds", 0),
            "api_calls": total_api_calls,
            "cost_usd": 0.0,
        }

        # Recompute cost
        pricing = get_pricing(model)
        if pricing:
            net_in = max(0, total_input - total_cache_read)
            ar["totals"]["cost_usd"] = round(
                (net_in * pricing["input"] +
                 total_output * pricing["output"] +
                 total_cache_read * pricing["cache_read"] +
                 total_cache_write * pricing["cache_write"]) / 1_000_000,
                4,
            )

    # Recompute grand totals
    gt = data.get("grand_totals", {})
    ar_results = data.get("ar_results", [])
    data["grand_totals"] = {
        "input_tokens": sum(ar["totals"]["input_tokens"] for ar in ar_results),
        "output_tokens": sum(ar["totals"]["output_tokens"] for ar in ar_results),
        "cache_read_tokens": sum(ar["totals"]["cache_read_tokens"] for ar in ar_results),
        "cache_write_tokens": sum(ar["totals"]["cache_write_tokens"] for ar in ar_results),
        "total_tokens": sum(ar["totals"]["input_tokens"] + ar["totals"]["output_tokens"] for ar in ar_results),
        "human_input_tokens": 0,
        "spec_context_tokens": 0,
        "total_iterations": sum(ar["totals"]["iterations"] for ar in ar_results),
        "total_duration_seconds": gt.get("total_duration_seconds", 0),
        "total_api_calls": sum(ar["totals"]["api_calls"] for ar in ar_results),
        "total_cost_usd": sum(ar["totals"]["cost_usd"] for ar in ar_results),
        "total_loc": gt.get("total_loc", 0),
        "total_files": gt.get("total_files", 0),
        "ar_count": len(ar_results),
    }

    # Recompute stage aggregates
    stage_agg = {}
    for ar in ar_results:
        for sid, sv in ar["stages"].items():
            if sid not in stage_agg:
                stage_agg[sid] = {
                    "total_tokens": 0, "input_tokens": 0, "output_tokens": 0,
                    "cache_read_tokens": 0, "cache_write_tokens": 0,
                    "human_input_tokens": 0, "spec_context_tokens": 0,
                    "total_iterations": 0, "duration_seconds": 0,
                    "total_api_calls": 0, "cost_usd": 0.0,
                }
            sa = stage_agg[sid]
            sa["total_tokens"] += sv.get("total_tokens", 0)
            sa["input_tokens"] += sv.get("input_tokens", 0)
            sa["output_tokens"] += sv.get("output_tokens", 0)
            sa["cache_read_tokens"] += sv.get("cache_read_tokens", 0)
            sa["cache_write_tokens"] += sv.get("cache_write_tokens", 0)
            sa["total_iterations"] += sv.get("iterations", 0)
            sa["duration_seconds"] += sv.get("duration_seconds", 0)
            sa["total_api_calls"] += sv.get("api_calls", 0)
            pricing = get_pricing(model)
            if pricing:
                net_in = max(0, sv.get("input_tokens", 0) - sv.get("cache_read_tokens", 0))
                sa["cost_usd"] += (
                    (net_in * pricing["input"] + sv.get("output_tokens", 0) * pricing["output"] +
                     sv.get("cache_read_tokens", 0) * pricing["cache_read"] +
                     sv.get("cache_write_tokens", 0) * pricing["cache_write"]) / 1_000_000
                )
    for sa in stage_agg.values():
        sa["cost_usd"] = round(sa["cost_usd"], 4)
    data["stage_aggregates"] = stage_agg

    # Mark as retried
    data["meta"]["retried_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    data["meta"]["retry_stats"] = {
        "total_retries": total_retries,
        "total_fixed": total_fixed,
        "tool_used": tool,
        "model_used": model,
    }

    # Save
    with open(full_json_path, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    log.info(f"\n{'='*60}")
    log.info(f"Retry complete: {total_retries} stage retries attempted, {total_fixed} succeeded")
    log.info(f"Updated: {full_json_path}")
    log.info(f"New grand total_tokens: {data['grand_totals']['total_tokens']:,}")


if __name__ == "__main__":
    main()
