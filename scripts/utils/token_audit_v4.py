import json
import os
import glob
from decimal import Decimal

def audit_tokens_cumulative(log_dir):
    """
    SDD-TEE v4.0 Precision Audit: 
    Sum every single turn's tokens to ensure zero-loss tracking.
    """
    total_in = 0
    total_out = 0
    total_cr = 0
    
    raw_files = glob.glob(os.path.join(log_dir, "*_raw.json"))
    for rf in raw_files:
        with open(rf, 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                if '"tokens":' in line and '"type":"step_finish"' in line:
                    try:
                        data = json.loads(line)
                        toks = data.get('part', {}).get('tokens') or data.get('tokens')
                        if toks:
                            total_in += toks.get('input', 0)
                            total_out += toks.get('output', 0)
                            total_cr += toks.get('cache', {}).get('read', 0) or toks.get('cached', 0)
                    except: continue
    return total_in, total_out, total_cr

def get_physical_loc(ws_dir):
    """SDD-TEE v4.0: Physical line count via file scanning."""
    total_loc = 0
    extensions = {'.go', '.py', '.yaml', '.yml', '.sh', '.md'}
    if not os.path.exists(ws_dir): return 0
    
    for root, dirs, files in os.walk(ws_dir):
        if any(x in root for x in ['.git', 'node_modules', 'venv', 'specs', 'results']): continue
        for f in files:
            if any(f.endswith(ext) for ext in extensions):
                if f in ['all_specs.txt', 'PLAN.md']: continue
                p = os.path.join(root, f)
                if os.path.getsize(p) > 1024 * 500: continue # Skip >500KB
                try:
                    with open(p, 'r', encoding='utf-8', errors='ignore') as fh:
                        total_loc += len(fh.readlines())
                except: continue
    return total_loc
