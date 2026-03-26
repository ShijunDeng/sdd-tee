import json
import os
import glob
import re

def audit_logs(log_dir):
    stats = {"healing": 0, "audit_tokens": 0}
    for f in glob.glob(f"{log_dir}/*.json"):
        if "self_healing" in f: stats["healing"] += 1
        with open(f) as jf:
            for line in jf:
                try:
                    e = json.loads(line)
                    if e.get("type") == "step_finish":
                        stats["audit_tokens"] += e.get("part", {}).get("tokens", {}).get("total", 0)
                except: continue
    return stats

def generate_report():
    results = []
    # 查找所有 full.json
    for f in glob.glob("results/runs/v4.0/*full.json"):
        with open(f) as jf:
            d = json.load(jf)
            model = d.get('meta', {}).get('model', d.get('model', 'Unknown'))
            run_id = d.get('meta', {}).get('run_id', d.get('run_id', ''))
            logs = f"results/runs/v4.0/{run_id}_logs"
            audit = audit_logs(logs)
            
            results.append({
                "Model": model,
                "Audited_Tokens": f"{audit['audit_tokens']:,}",
                "Healing_Depth": audit['healing'],
                "Build": d.get('meta', {}).get('status', d.get('quality', {}).get('build_status', 'N/A')),
                "LOC": d.get('grand_totals', d.get('token_summary', {})).get('total_loc', 'N/A')
            })

    html = "<html><body style='font-family:sans-serif; padding:40px;'><h1>SDD-TEE v4.0 Reinforced Benchmark Summary</h1>"
    html += "<table border='1' cellpadding='10' cellspacing='0' style='width:100%; text-align:left; border-color:#eee;'>"
    html += "<tr style='background:#f4f4f4;'><th>Model (Evaluated)</th><th>Healing Depth (Iterations)</th><th>Audited Token Volume</th><th>Code Delivered (LOC)</th><th>Final Build</th></tr>"
    for r in results:
        html += f"<tr><td><b>{r['Model']}</b></td><td>{r['Healing_Depth']}</td><td>{r['Audited_Tokens']}</td><td>{r['LOC']}</td><td>{r['Build']}</td></tr>"
    html += "</table><p style='margin-top:20px; color:#666;'>* Audited Token Volume reflects the rigorousness of TDD reinforcement loop.</p></body></html>"
    
    with open("results/reports/v4.0/v4_meaningful_comparison.html", "w") as out:
        out.write(html)
    print("Meaningful v4 report generated.")

if __name__ == "__main__":
    generate_report()
