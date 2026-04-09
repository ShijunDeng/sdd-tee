import sys

def fix():
    with open('scripts/07_sdd_tee_report.py', 'r') as f:
        lines = f.readlines()
    
    new_lines = []
    skip = False
    for line in lines:
        if '<div class="insight-box"><strong>📊 散点图深度解析' in line:
            continue # 移除之前错误的注入
        if 'cx = min(x / max' in line:
            # 保持原始缩进并注入正确的逻辑
            indent = line[:line.find('cx')]
            new_lines.append(f'{indent}max_x = max([r["output"]["actual_loc"] for r in ars] + [1])\n')
            new_lines.append(f'{indent}max_y = max([r["totals"]["total_tokens"] for r in ars] + [1])\n')
            new_lines.append(f'{indent}cx = min(x / max_x * 540, 540) + 80\n')
            new_lines.append(f'{indent}cy = 350 - min(y / max_y * 300, 300)\n')
            continue
        if 'cy = 350 - min(y / max' in line:
            continue
        if 'scatter_svg = f"""<svg' in line:
            new_lines.append(line)
            continue
        new_lines.append(line)
    
    with open('scripts/07_sdd_tee_report.py', 'w') as f:
        f.writelines(new_lines)

fix()
