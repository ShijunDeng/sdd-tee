#!/usr/bin/env python3
"""
SDD-TEE Evaluation Runner with LiteLLM Proxy Token Tracking

Executes the CodeSpec 7-stage workflow for each AR via LiteLLM,
recording precise per-request token data.

Prerequisites:
  1. Start LiteLLM Proxy:
     litellm --config litellm_config.yaml --port 4000
  2. Set API key:
     export ANTHROPIC_API_KEY=sk-...   (or OPENAI_API_KEY)
  3. Run:
     python3 scripts/10_litellm_runner.py --model claude-sonnet-4 --tool litellm-proxy

Token tracking:
  - Every litellm.completion() call returns response.usage with:
    prompt_tokens, completion_tokens, total_tokens,
    cache_read_input_tokens, cache_creation_input_tokens
  - Mapped to: input_tokens, output_tokens, cache_read_tokens, cache_write_tokens
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import importlib
_mod = importlib.import_module("07_sdd_tee_report")
AR_CATALOG = _mod.AR_CATALOG
STAGE_NAMES = _mod.STAGE_NAMES
OPSX_COMMANDS = _mod.OPSX_COMMANDS

try:
    import litellm
    HAS_LITELLM = True
except ImportError:
    HAS_LITELLM = False


def load_specs(specs_dir):
    specs = Path(specs_dir)
    content = {}
    for sf in sorted(specs.rglob("*.md")):
        rel = str(sf.relative_to(specs))
        content[rel] = sf.read_text(encoding="utf-8", errors="replace")
    return content


def build_stage_prompt(ar, stage_id, specs_content, prev_outputs):
    """Build the prompt for a given AR × stage combination."""
    ar_desc = f"AR: {ar['id']} — {ar['name']} (module: {ar['module']}, lang: {ar['lang']}, size: {ar['size']})"

    if stage_id == "ST-0":
        return f"Initialize a new OpenSpec change for:\n{ar_desc}\nCreate the change directory scaffold."

    relevant_specs = []
    for name, text in specs_content.items():
        mod_lower = ar["module"].lower()
        name_lower = name.lower()
        if any(kw in name_lower for kw in [mod_lower.split("/")[-1], ar["lang"].lower()]):
            relevant_specs.append(f"--- {name} ---\n{text}")

    spec_context = "\n\n".join(relevant_specs[:3]) if relevant_specs else "No directly matching specs."

    prompts = {
        "ST-1": f"Write proposal.md for:\n{ar_desc}\n\nRelevant specs:\n{spec_context}\n\nInclude: purpose, scope, impact analysis.",
        "ST-2": f"Write delta-spec.md (ADDED/MODIFIED requirements with GIVEN/WHEN/THEN scenarios) for:\n{ar_desc}\n\nBase specs:\n{spec_context}",
        "ST-3": f"Write design.md with technical implementation details for:\n{ar_desc}\n\nSpecs:\n{spec_context}\n\nPrevious proposal:\n{prev_outputs.get('ST-1', 'N/A')[:2000]}",
        "ST-4": f"Write tasks.md checklist for:\n{ar_desc}\n\nDesign:\n{prev_outputs.get('ST-3', 'N/A')[:2000]}",
        "ST-5": f"Implement the code for:\n{ar_desc}\n\nTasks:\n{prev_outputs.get('ST-4', 'N/A')[:2000]}\n\nDesign:\n{prev_outputs.get('ST-3', 'N/A')[:3000]}",
        "ST-6": f"Verify implementation against spec for:\n{ar_desc}\n\nSpec:\n{spec_context[:2000]}\n\nCode output:\n{prev_outputs.get('ST-5', 'N/A')[:3000]}",
        "ST-7": f"Archive change for:\n{ar_desc}\n\nMerge delta specs into main specs. Summarize what was completed.",
    }
    return prompts.get(stage_id, f"Process stage {stage_id} for {ar_desc}")


def run_stage(ar, stage_id, prompt, model, api_base=None):
    """Execute a single stage via LiteLLM and record token usage."""
    start = time.time()

    kwargs = {
        "model": model,
        "messages": [
            {"role": "system", "content": "You are an SDD (Specification-Driven Development) assistant."},
            {"role": "user", "content": prompt},
        ],
        "max_tokens": 4096,
    }
    if api_base:
        kwargs["api_base"] = api_base

    try:
        response = litellm.completion(**kwargs)
        usage = response.usage
        output_text = response.choices[0].message.content or ""

        result = {
            "stage": stage_id,
            "stage_name": STAGE_NAMES[stage_id],
            "opsx_command": OPSX_COMMANDS[stage_id],
            "input_tokens": getattr(usage, "prompt_tokens", 0),
            "output_tokens": getattr(usage, "completion_tokens", 0),
            "cache_read_tokens": getattr(usage, "cache_read_input_tokens", 0) or 0,
            "cache_write_tokens": getattr(usage, "cache_creation_input_tokens", 0) or 0,
            "total_tokens": getattr(usage, "total_tokens", 0),
            "human_input_tokens": 0,
            "spec_context_tokens": 0,
            "iterations": 1,
            "duration_seconds": int(time.time() - start),
            "api_calls": 1,
            "output_text": output_text,
        }
    except Exception as e:
        result = {
            "stage": stage_id,
            "stage_name": STAGE_NAMES[stage_id],
            "opsx_command": OPSX_COMMANDS[stage_id],
            "input_tokens": 0, "output_tokens": 0,
            "cache_read_tokens": 0, "cache_write_tokens": 0,
            "total_tokens": 0, "human_input_tokens": 0,
            "spec_context_tokens": 0, "iterations": 0,
            "duration_seconds": int(time.time() - start),
            "api_calls": 1,
            "output_text": "",
            "error": str(e),
        }
    return result


def run_evaluation(model, specs_dir, api_base=None, output_dir="results/runs"):
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    tool_name = "litellm-proxy" if api_base else "litellm-direct"
    run_id = f"{tool_name}_{model}_{ts}"

    print(f"[10] Starting evaluation: {run_id}")
    print(f"  Model: {model}")
    print(f"  API base: {api_base or 'direct'}")
    print(f"  Specs: {specs_dir}")

    specs_content = load_specs(specs_dir)
    print(f"  Loaded {len(specs_content)} spec files")

    all_results = []
    total_start = time.time()

    for i, ar in enumerate(AR_CATALOG):
        print(f"\n  [{i+1}/{len(AR_CATALOG)}] {ar['id']} {ar['name']} ({ar['size']})")
        prev_outputs = {}
        ar_stages = {}

        for sid in STAGE_NAMES:
            prompt = build_stage_prompt(ar, sid, specs_content, prev_outputs)
            result = run_stage(ar, sid, prompt, model, api_base)
            ar_stages[sid] = result
            prev_outputs[sid] = result.get("output_text", "")

            tok = result["total_tokens"]
            dur = result["duration_seconds"]
            print(f"    {sid}: {tok:,} tokens, {dur}s" +
                  (f" ERROR: {result['error']}" if "error" in result else ""))

        total_input = sum(s["input_tokens"] for s in ar_stages.values())
        total_output = sum(s["output_tokens"] for s in ar_stages.values())

        all_results.append({
            "ar_id": ar["id"],
            "ar_name": ar["name"],
            "module": ar["module"],
            "lang": ar["lang"],
            "type": ar["type"],
            "size": ar["size"],
            "stages": {k: {kk: vv for kk, vv in v.items() if kk != "output_text"}
                       for k, v in ar_stages.items()},
            "totals": {
                "input_tokens": total_input,
                "output_tokens": total_output,
                "cache_read_tokens": sum(s["cache_read_tokens"] for s in ar_stages.values()),
                "cache_write_tokens": sum(s["cache_write_tokens"] for s in ar_stages.values()),
                "total_tokens": total_input + total_output,
                "human_input_tokens": sum(s["human_input_tokens"] for s in ar_stages.values()),
                "spec_context_tokens": sum(s["spec_context_tokens"] for s in ar_stages.values()),
                "iterations": sum(s["iterations"] for s in ar_stages.values()),
                "duration_seconds": sum(s["duration_seconds"] for s in ar_stages.values()),
                "api_calls": sum(s["api_calls"] for s in ar_stages.values()),
                "cost_usd": 0,
            },
            "output": {"actual_loc": 0, "actual_files": 0, "tasks_count": ar["est_tasks"]},
            "quality": {"consistency_score": 0, "code_usability": 0,
                        "test_coverage": 0, "bugs_found": 0},
            "metrics": {},
        })

    total_dur = int(time.time() - total_start)

    # Build aggregates (same structure as 07_sdd_tee_report expects)
    grand = {
        "ar_count": len(all_results),
        "input_tokens": sum(r["totals"]["input_tokens"] for r in all_results),
        "output_tokens": sum(r["totals"]["output_tokens"] for r in all_results),
        "cache_read_tokens": sum(r["totals"]["cache_read_tokens"] for r in all_results),
        "cache_write_tokens": sum(r["totals"]["cache_write_tokens"] for r in all_results),
        "total_tokens": sum(r["totals"]["total_tokens"] for r in all_results),
        "human_input_tokens": sum(r["totals"]["human_input_tokens"] for r in all_results),
        "spec_context_tokens": sum(r["totals"]["spec_context_tokens"] for r in all_results),
        "total_duration_seconds": total_dur,
        "total_cost_usd": 0,
        "total_cost_cny": 0,
        "total_loc": 0,
        "total_files": 0,
        "total_tasks": sum(r["output"]["tasks_count"] for r in all_results),
        "total_iterations": sum(r["totals"]["iterations"] for r in all_results),
        "total_api_calls": sum(r["totals"]["api_calls"] for r in all_results),
    }

    stage_agg = {}
    for sid in STAGE_NAMES:
        stage_agg[sid] = {
            "name": STAGE_NAMES[sid],
            "total_tokens": sum(r["stages"][sid]["total_tokens"] for r in all_results),
            "input_tokens": sum(r["stages"][sid]["input_tokens"] for r in all_results),
            "output_tokens": sum(r["stages"][sid]["output_tokens"] for r in all_results),
            "duration_seconds": sum(r["stages"][sid]["duration_seconds"] for r in all_results),
            "iterations": sum(r["stages"][sid]["iterations"] for r in all_results),
        }

    data = {
        "meta": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "is_mock": False,
            "framework": "SDD-TEE v2",
            "methodology": "CodeSpec 7-Stage + OpenSpec OPSX",
            "target_project": "agentcube",
            "tool": tool_name,
            "model": model,
            "run_id": run_id,
            "token_tracking": "LiteLLM Proxy per-request recording (precise)",
        },
        "ar_catalog": AR_CATALOG,
        "ar_results": all_results,
        "grand_totals": grand,
        "stage_aggregates": stage_agg,
        "baselines": {},
    }

    Path(output_dir).mkdir(parents=True, exist_ok=True)
    out_path = os.path.join(output_dir, f"{run_id}_full.json")
    with open(out_path, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"\n[10] Evaluation complete: {run_id}")
    print(f"  Total: {grand['total_tokens']:,} tokens, {total_dur//60}m{total_dur%60}s")
    print(f"  Saved → {out_path}")
    print(f"\n  Generate report:")
    print(f"    python3 scripts/07_sdd_tee_report.py --data {out_path}")
    return data


def main():
    parser = argparse.ArgumentParser(description="SDD-TEE LiteLLM Evaluation Runner")
    parser.add_argument("--model", default="anthropic/claude-sonnet-4-20250514")
    parser.add_argument("--api-base", default=None, help="LiteLLM proxy URL (e.g. http://localhost:4000)")
    parser.add_argument("--specs-dir", default="specs/")
    parser.add_argument("--output-dir", default="results/runs")
    args = parser.parse_args()

    if not HAS_LITELLM:
        print("ERROR: litellm not installed. Run: pip install litellm")
        sys.exit(1)

    run_evaluation(args.model, args.specs_dir, args.api_base, args.output_dir)


if __name__ == "__main__":
    main()
