import json
import os
import glob
import re

def audit_logs(log_dir):
    stats = {"errors": [], "total_tokens": 0, "steps": 0, "healing_iterations": 0}
    for f in glob.glob(f"{log_dir}/*.json"):
        if "self_healing" in f: stats["healing_iterations"] += 1
        with open(f) as jf:
            for line in jf:
                try:
                    entry = json.loads(line)
                    if entry.get("type") == "step_finish":
                        stats["total_tokens"] += entry.get("part", {}).get("tokens", {}).get("total", 0)
                        stats["steps"] += 1
                    if "diagnostics" in str(entry):
                        # 提取具体的 LSP 错误消息
                        errors = re.findall(r'"message":"(.*?)"', str(entry))
                        stats["errors"].extend(errors)
                except: continue
    return stats

def generate_deep_report():
    print("Starting SDD-TEE v4.0 Deep Audit...")
    for logs in glob.glob("results/runs/v4.0/*_logs"):
        run_id = os.path.basename(logs).replace("_logs", "")
        audit = audit_logs(logs)
        unique_errors = list(set(audit["errors"]))[:5]
        print(f"\nModel: {run_id}")
        print(f"  - Total Audited Tokens: {audit['total_tokens']:,}")
        print(f"  - Self-Healing Iterations: {audit['healing_iterations']}")
        print(f"  - Key Compiler Blocks: {unique_errors}")

if __name__ == "__main__":
    generate_deep_report()
