import json
import glob
import os

def audit(run_id):
    log_dir = f"results/runs/v4.0/{run_id}_logs"
    totals = {"in": 0, "out": 0, "cache": 0}
    for f in glob.glob(f"{log_dir}/*.json"):
        with open(f) as jf:
            for line in jf:
                try:
                    data = json.loads(line)
                    if data.get("type") == "step_finish":
                        t = data["part"]["tokens"]
                        totals["in"] += t.get("input", 0)
                        totals["out"] += t.get("output", 0)
                        totals["cache"] += t.get("cache", {}).get("read", 0)
                except: continue
    return totals

runs = ["opencode-cli_bailian-coding-plan-glm-5_20260326T115802Z", 
        "opencode-cli_bailian-coding-plan-kimi-k2.5_20260325T161014Z"]

for r in runs:
    res = audit(r)
    print(f"Run: {r}")
    print(f"  - Real Input: {res['in']:,}")
    print(f"  - Real Output: {res['out']:,}")
    print(f"  - Real Cache: {res['cache']:,}")
    print(f"  - TOTAL: {res['in'] + res['out'] + res['cache']:,}")
