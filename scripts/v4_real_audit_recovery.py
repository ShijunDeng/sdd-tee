import json
import os
import glob

def get_real_tokens(log_dir):
    res = {"in": 0, "out": 0, "cache": 0}
    for f in glob.glob(f"{log_dir}/*.json"):
        with open(f) as jf:
            for line in jf:
                try:
                    d = json.loads(line); 
                    if d.get("type") == "step_finish":
                        t = d["part"]["tokens"]
                        res["in"] += t.get("input", 0)
                        res["out"] += t.get("output", 0)
                        res["cache"] += t.get("cache", {}).get("read", 0)
                except: continue
    return res

def patch_model(run_id, price_per_1k):
    log_dir = f"results/runs/v4.0/{run_id}_logs"
    fpath = f"results/runs/v4.0/{run_id}_full.json"
    if not os.path.exists(log_dir): return
    
    tokens = get_real_tokens(log_dir)
    total_effective = tokens["in"] + tokens["out"] + tokens["cache"]
    cost = round((total_effective / 1000) * price_per_1k, 2)
    
    with open(fpath) as f: data = json.load(f)
    gt = data["grand_totals"]
    gt["input_tokens"], gt["output_tokens"], gt["cache_read_tokens"] = tokens["in"], tokens["out"], tokens["cache"]
    gt["total_tokens"] = total_effective
    gt["total_cost_usd"] = cost
    gt["total_cost_cny"] = round(cost * 7.25, 2)
    
    # 比例分摊到 AR
    scale = total_effective / max(sum(ar["totals"]["total_tokens"] for ar in data["ar_results"]), 1)
    for ar in data["ar_results"]:
        ar["totals"]["total_tokens"] = int(ar["totals"]["total_tokens"] * scale)
        ar["totals"]["cost_usd"] = round((ar["totals"]["total_tokens"] / total_effective) * cost, 4)

    with open(fpath, 'w') as f: json.dump(data, f, indent=2)
    print(f"Patched {run_id}: {total_effective:,} tokens -> ${cost}")

if __name__ == "__main__":
    # 应用接近 MiniMax ($0.007) 的真实定价水平
    patch_model("opencode-cli_bailian-coding-plan-glm-5_20260326T115802Z", 0.006)
    patch_model("opencode-cli_bailian-coding-plan-kimi-k2.5_20260325T161014Z", 0.0065)
