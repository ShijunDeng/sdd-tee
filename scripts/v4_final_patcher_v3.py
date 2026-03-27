import json
import os
import glob

def final_fix(fpath):
    with open(fpath) as f: data = json.load(f)
    # 为每一个 stage 和 total 补全缺失的 iterations 别名
    for ar in data["ar_results"]:
        ar["totals"]["total_iterations"] = ar["totals"]["iterations"]
        for st in ar["stages"].values():
            st["total_iterations"] = st["iterations"]
    for s in data["stage_aggregates"].values():
        s["iterations"] = s["total_iterations"]
    with open(fpath, 'w') as f: json.dump(data, f, indent=2)

if __name__ == "__main__":
    for f in glob.glob("results/runs/v4.0/*full.json"):
        final_fix(f)
