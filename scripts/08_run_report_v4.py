import json
import sys
import os

def generate_v4_html(json_path):
    with open(json_path) as f:
        data = json.load(f)
    
    model = data.get('meta', {}).get('model', data.get('model', 'Unknown'))
    tokens = data.get('grand_totals', {}).get('total_tokens', data.get('token_summary', {}).get('total_tokens', 0))
    cost = data.get('grand_totals', {}).get('total_cost_usd', data.get('token_summary', {}).get('cost_usd', 0))
    loc = data.get('grand_totals', {}).get('total_loc', data.get('quality', {}).get('loc_generated', 0))
    status = data.get('meta', {}).get('status', data.get('quality', {}).get('build_status', 'N/A'))
    
    html = f"""
    <!DOCTYPE html>
    <html lang="zh-CN">
    <head>
    <meta charset="utf-8">
    <title>SDD-TEE v4.0 详细报告 - {model}</title>
    <style>
      body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; max-width: 1200px; margin: 0 auto; padding: 20px; background: #f8f9fa; color: #333; }}
      .section {{ background: #fff; padding: 25px; margin: 20px 0; border-radius: 12px; box-shadow: 0 2px 10px rgba(0,0,0,0.05); }}
      h1 {{ color: #1a73e8; border-bottom: 3px solid #1a73e8; padding-bottom: 10px; }}
    </style>
    </head>
    <body>
    <h1>SDD-TEE v4.0 评测报告: {model}</h1>
    <div class="section">
      <h2>核心指标 (Core Metrics)</h2>
      <p>总消耗 Token: {tokens:,}</p>
      <p>测试成本 (USD): ${cost}</p>
      <p>生成代码 (LOC): {loc}</p>
      <p>构建状态: {status}</p>
    </div>
    </body></html>
    """
    return html

if __name__ == "__main__":
    if len(sys.argv) > 1:
        print(generate_v4_html(sys.argv[1]))
