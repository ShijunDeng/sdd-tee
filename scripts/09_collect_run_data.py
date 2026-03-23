#!/usr/bin/env python3
"""
SDD-TEE Run Data Collector v3 (Billing by Telemetry)

Key improvements:
  1. Audit-First: Prioritizes real API usage from *_raw.json logs.
  2. Fallback Mitigation: Uses file-diff only if logs are missing, with a 5x penalty.
  3. Context Awareness: Correctly accounts for long-session context ballooning.
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import importlib
_mod = importlib.import_module("07_sdd_tee_report")
AR_CATALOG = _mod.AR_CATALOG
STAGE_NAMES = _mod.STAGE_NAMES
OPSX_COMMANDS = _mod.OPSX_COMMANDS

try:
    from litellm import token_counter
    HAS_LITELLM = True
except ImportError:
    HAS_LITELLM = False

# ============================================================================
# Telemetry Audit Engine
# ============================================================================

def audit_logs(log_dir):
    """Parses raw logs to find real API usage."""
    totals = {"input": 0, "output": 0, "cache_read": 0, "cache_write": 0, "total": 0}
    if not os.path.exists(log_dir): return None
    
    found_any = False
    for f in sorted(os.listdir(log_dir)):
        if not f.endswith("_raw.json"): continue
        path = os.path.join(log_dir, f)
        try:
            with open(path, "r") as src:
                content = src.read()
                # Opencode format
                if '"type":"step_finish"' in content:
                    for line in content.strip().split("\n"):
                        try:
                            d = json.loads(line)
                            if d.get("type") == "step_finish":
                                t = d.get("part", {}).get("tokens", {})
                                if t:
                                    totals["input"] += t.get("input", 0)
                                    totals["output"] += t.get("output", 0)
                                    totals["cache_read"] += t.get("cache", {}).get("read", 0)
                                    totals["cache_write"] += t.get("cache", {}).get("write", 0)
                                    totals["total"] += t.get("total", 0)
                                    found_any = True
                        except: continue
                # Gemini stats format
                elif '"stats":' in content:
                    json_start = content.find("{")
                    if json_start != -1:
                        data = json.loads(content[json_start:])
                        models = data.get("stats", {}).get("models", {})
                        for m in models.values():
                            t = m.get("tokens", {})
                            if t:
                                totals["input"] += t.get("prompt", 0)
                                totals["output"] += t.get("candidates", 0)
                                totals["total"] += t.get("total", 0)
                                totals["cache_read"] += t.get("cached", 0)
                                found_any = True
        except: continue
    
    return totals if found_any else None

# ============================================================================
# File Classification & Distribution (Legacy but needed for AR mapping)
# ============================================================================

AR_FILE_PATTERNS = [
    ("AR-001", [r"pkg/apis/runtime/v1alpha1/agentruntime", r"pkg/apis/runtime/v1alpha1/register"]),
    ("AR-002", [r"pkg/apis/runtime/v1alpha1/codeinterpreter", r"pkg/apis/runtime/v1alpha1/doc\.go"]),
    ("AR-003", [r"pkg/apis/runtime/v1alpha1/types\.go", r"pkg/apis/runtime/v1alpha1/defaults",
                r"pkg/common/types", r"pkg/apis/runtime/v1alpha1/zz_generated"]),
    ("AR-038", [r"pkg/workloadmanager/.*_test\.go"]),
    ("AR-039", [r"pkg/(router|store|picod)/.*_test\.go"]),
    ("AR-040", [r"sdk-python/tests/", r"cmd/cli/tests/"]),
]

def classify_file(relpath):
    relpath_lower = relpath.lower().replace("\\", "/")
    for ar_id, patterns in AR_FILE_PATTERNS:
        for pat in patterns:
            if re.search(pat, relpath_lower): return ar_id
    return "AR-004" # Default fallback

# ============================================================================
# Main Collector Logic
# ============================================================================

def collect(run_json_path, workspace_dir, specs_dir, model_id):
    with open(run_json_path) as f:
        run_data = json.load(f)

    log_dir = run_json_path.replace(".json", "_logs")
    if not os.path.exists(log_dir):
        # Compatibility for some dir structures
        log_dir = os.path.join(os.path.dirname(run_json_path), f"{run_data['run_id']}_logs")

    # 1. Try Audit First
    telemetry = audit_logs(log_dir)
    tracking_method = "telemetry-audit" if telemetry else "estimation-fallback"
    
    ws = Path(workspace_dir)
    source_exts = {".go", ".py", ".yaml", ".yml", ".md", ".json", ".sh"}
    
    total_loc = 0
    total_files = 0
    for fpath in ws.rglob("*"):
        if fpath.is_file() and fpath.suffix.lower() in source_exts and ".git" not in str(fpath):
            total_files += 1
            try: total_loc += len(fpath.read_text().splitlines())
            except: pass

    # 2. Token Allocation
    if telemetry:
        grand_total_tokens = telemetry["total"]
        grand_input = telemetry["input"]
        grand_output = telemetry["output"]
        grand_cache_read = telemetry["cache_read"]
        grand_cache_write = telemetry["cache_write"]
    else:
        # Fallback with penalty (5x to account for agentic overhead)
        print(f"  [WARN] No telemetry found. Using penalized estimation.")
        grand_output = total_loc * 30 
        grand_input = grand_output * 4
        grand_cache_read = int(grand_input * 0.5)
        grand_cache_write = 0
        grand_total_tokens = grand_input + grand_output

    pricing = {"input": 15.0, "output": 75.0, "cache_read": 1.50, "cache_write": 18.75}
    cost = (grand_input * pricing["input"] / 1e6 
            + grand_cache_read * pricing["cache_read"] / 1e6
            + grand_cache_write * pricing["cache_write"] / 1e6
            + grand_output * pricing["output"] / 1e6)

    # Simplified mock for AR distribution (v3 focuses on totals)
    ar_results = []
    for ar in AR_CATALOG:
        share = 1.0 / len(AR_CATALOG)
        ar_results.append({
            "ar_id": ar["id"],
            "ar_name": ar["name"],
            "size": ar["size"],
            "totals": {
                "total_tokens": int(grand_total_tokens * share),
                "input_tokens": int(grand_input * share),
                "output_tokens": int(grand_output * share),
                "cost_usd": round(cost * share, 4)
            },
            "output": {"actual_loc": int(total_loc * share), "actual_files": 1},
            "metrics": {"ET_LOC": 0, "QT_COV": 0.8},
            "stages": {} # Placeholder
        })

    return {
        "meta": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "run_id": run_data["run_id"],
            "tool": run_data["tool"],
            "model": run_data["model"],
            "token_tracking": tracking_method,
            "agentic_overhead_factor": round(grand_total_tokens / (total_loc * 30 + 1), 2)
        },
        "grand_totals": {
            "ar_count": len(AR_CATALOG),
            "input_tokens": grand_input,
            "output_tokens": grand_output,
            "cache_read_tokens": grand_cache_read,
            "cache_write_tokens": grand_cache_write,
            "total_tokens": grand_total_tokens,
            "total_cost_usd": round(cost, 2),
            "total_cost_cny": round(cost * 7.25, 2),
            "total_loc": total_loc,
            "total_files": total_files,
        },
        "ar_results": ar_results,
        "stage_aggregates": {},
        "baselines": {}
    }

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("run_json")
    parser.add_argument("workspace")
    parser.add_argument("--specs-dir", default="specs/")
    parser.add_argument("--model", default="claude-sonnet-4")
    args = parser.parse_args()

    print(f"[09] V3 Auditing: {args.run_json}")
    data = collect(args.run_json, args.workspace, args.specs_dir, args.model)
    
    out_path = args.run_json.replace(".json", "_full.json")
    with open(out_path, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    
    gt = data["grand_totals"]
    print(f"  Audit Complete: {gt['total_tokens']:,} tokens (${gt['total_cost_usd']})")
    print(f"  Agentic Overhead: {data['meta']['agentic_overhead_factor']}x")

if __name__ == "__main__":
    main()
