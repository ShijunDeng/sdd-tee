import sys

def make_robust():
    with open('scripts/07_sdd_tee_report.py', 'r') as f:
        content = f.read()
    
    # 修复 iterations 的读取逻辑
    content = content.replace("s['iterations']", "s.get('iterations', s.get('total_iterations', 0))")
    content = content.replace("s['duration_seconds']", "s.get('duration_seconds', s.get('total_duration_seconds', 0))")
    content = content.replace("r['totals']['cost_usd']", "r.get('totals', {}).get('cost_usd', 0)")
    
    with open('scripts/07_sdd_tee_report.py', 'w') as f:
        f.write(content)

if __name__ == "__main__":
    make_robust()
