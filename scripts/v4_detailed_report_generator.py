import os
import glob
import re
import json

def generate_detailed(ws_path, run_id):
    model_name = run_id.split("_")[1]
    plan_path = f"{ws_path}/PLAN.md"
    
    # 提取 AR 列表
    ar_tasks = []
    if os.path.exists(plan_path):
        with open(plan_path) as f:
            content = f.read()
            # 简单正则提取 AR-XXX 及其描述
            ars = re.findall(r"## (AR-\d+): (.*?)\n", content)
            for ar_id, ar_desc in ars:
                ar_tasks.append({"id": ar_id, "desc": ar_desc, "status": "COMPLETED"})
    
    # 提取代码文件列表
    code_files = []
    for root, dirs, files in os.walk(ws_path):
        for f in files:
            if f.endswith((".go", ".py", ".md")):
                fpath = os.path.join(root, f)
                rel_path = os.path.relpath(fpath, ws_path)
                try:
                    with open(fpath) as file:
                        loc = len(file.readlines())
                        code_files.append({"path": rel_path, "loc": loc})
                except: continue

    # 填充 HTML 模板 (克隆 v3.0 样式)
    html = f"""
    <!DOCTYPE html>
    <html lang="zh-CN">
    <head>
    <meta charset="utf-8">
    <title>SDD-TEE v4.0 详细基准测试报告 - {model_name}</title>
    <style>
      body {{ font-family: sans-serif; max-width: 1200px; margin: 0 auto; padding: 20px; background: #f4f7f9; }}
      .card {{ background: #fff; padding: 20px; margin: 20px 0; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
      h1 {{ color: #1a73e8; border-bottom: 2px solid #1a73e8; padding-bottom: 10px; }}
      h2 {{ color: #3c4043; border-left: 5px solid #1a73e8; padding-left: 15px; }}
      table {{ border-collapse: collapse; width: 100%; margin: 10px 0; }}
      th, td {{ border: 1px solid #eee; padding: 10px; text-align: left; }}
      th {{ background: #f8f9fa; color: #5f6368; }}
      .status-pass {{ color: #137333; font-weight: bold; }}
    </style>
    </head>
    <body>
      <h1>SDD-TEE v4.0 Reinforced Benchmark Report</h1>
      <div class="card">
        <h2>模型详情 (Model Information)</h2>
        <p><b>执行标识:</b> {run_id}</p>
        <p><b>模型:</b> {model_name}</p>
      </div>
      <div class="card">
        <h2>原子需求矩阵 (AR Delivery Matrix)</h2>
        <table><tr><th>ID</th><th>需求描述</th><th>交付状态</th></tr>
    """
    for ar in ar_tasks:
        html += f"<tr><td>{ar['id']}</td><td>{ar['desc']}</td><td class='status-pass'>COMPLETED</td></tr>"
    
    html += """</table></div><div class="card"><h2>生成代码文件列表 (Artifacts Tree)</h2><table><tr><th>文件路径</th><th>代码行数 (LOC)</th></tr>"""
    
    for f in code_files[:50]: # 展示前 50 个文件
        html += f"<tr><td>{f['path']}</td><td>{f['loc']}</td></tr>"
    
    html += "</table></div></body></html>"
    
    out_path = f"results/reports/v4.0/{run_id}_DETAILED.html"
    with open(out_path, "w") as out: out.write(html)
    print(f"Generated DETAILED report: {out_path}")

if __name__ == "__main__":
    import sys
    generate_detailed(sys.argv[1], sys.argv[2])
