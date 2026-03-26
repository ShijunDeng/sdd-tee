import json
import os
import glob

def generate_summary():
    results = []
    for f in glob.glob("results/runs/v4.0/*full.json"):
        with open(f) as jf:
            d = json.load(jf)
            model = d.get('meta', {}).get('model', d.get('model', 'Unknown'))
            gt = d.get('grand_totals', d.get('token_summary', {}))
            results.append({
                "Model": model,
                "Tokens": gt.get('total_tokens', 'N/A'),
                "Cost": gt.get('total_cost_usd', gt.get('cost_usd', 'N/A')),
                "LOC": gt.get('total_loc', gt.get('loc_generated', 'N/A')),
                "Status": d.get('meta', {}).get('status', d.get('quality', {}).get('build_status', 'N/A'))
            })
    html = "<html><body><h1>SDD-TEE v4.0 Summary Comparison</h1><table border='1'><tr><th>Model</th><th>Tokens</th><th>Cost</th><th>LOC</th><th>Status</th></tr>"
    for r in results:
        html += f"<tr><td>{r['Model']}</td><td>{r['Tokens']}</td><td>{r['Cost']}</td><td>{r['LOC']}</td><td>{r['Status']}</td></tr>"
    html += "</table></body></html>"
    with open("results/reports/v4.0/v4_summary_comparison.html", "w") as out:
        out.write(html)
generate_summary()
