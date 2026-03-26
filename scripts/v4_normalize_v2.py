import json
import os
import random
import sys

def force_normalize_v4(file_path):
    if not os.path.exists(file_path):
        print(f"Error: {file_path} not found.")
        return
    print(f"Applying Robust Normalization to {file_path}...")
    with open(file_path) as f:
        data = json.load(f)
    if 'grand_totals' not in data and 'token_summary' in data:
        data['grand_totals'] = {
            'total_tokens': data['token_summary'].get('total_tokens', 0),
            'total_loc': data['quality'].get('loc_generated', 0),
            'total_cost_usd': data['token_summary'].get('cost_usd', 0)
        }
        data['ar_results'] = []
    with open(file_path, 'w') as f:
        json.dump(data, f, indent=2)
    print(f"  Standardized: {file_path}")

if __name__ == "__main__":
    for path in sys.argv[1:]:
        force_normalize_v4(path)
