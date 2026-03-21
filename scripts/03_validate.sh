#!/usr/bin/env bash
set -euo pipefail

# Stage 3: Validate generated code against original project
# Usage: ./scripts/03_validate.sh <workspace_dir> [original_dir]

WORKSPACE="${1:?Usage: $0 <workspace_dir> [original_dir]}"
ORIGINAL="${2:-/tmp/agentcube-benchmark-source}"
RESULTS_DIR="./results/runs"

RUN_ID=$(basename "$WORKSPACE")
TIMESTAMP=$(date -u +%Y%m%dT%H%M%SZ)
RESULT_FILE="$RESULTS_DIR/${RUN_ID}_validation.json"

echo "=== Stage 3: Validation ==="
echo "Workspace: $WORKSPACE"
echo "Original:  $ORIGINAL"

mkdir -p "$RESULTS_DIR"

python3 << 'PYEOF'
import os, json, subprocess, sys

workspace = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("WORKSPACE", "")
original = sys.argv[2] if len(sys.argv) > 2 else os.environ.get("ORIGINAL", "")
result_file = sys.argv[3] if len(sys.argv) > 3 else os.environ.get("RESULT_FILE", "")

def count_files(directory, exclude_dirs=None):
    exclude_dirs = exclude_dirs or {'.git', 'node_modules', '__pycache__', 'specs'}
    count = 0
    loc = 0
    by_ext = {}
    for root, dirs, files in os.walk(directory):
        dirs[:] = [d for d in dirs if d not in exclude_dirs]
        for f in files:
            fpath = os.path.join(root, f)
            count += 1
            ext = os.path.splitext(f)[1] or 'no_ext'
            by_ext[ext] = by_ext.get(ext, 0) + 1
            try:
                with open(fpath, errors='ignore') as fh:
                    loc += sum(1 for _ in fh)
            except:
                pass
    return count, loc, by_ext

def get_dir_structure(directory, exclude_dirs=None, max_depth=3):
    exclude_dirs = exclude_dirs or {'.git', 'node_modules', '__pycache__', 'specs'}
    dirs_found = set()
    for root, dirs, files in os.walk(directory):
        dirs[:] = [d for d in dirs if d not in exclude_dirs]
        rel = os.path.relpath(root, directory)
        depth = rel.count(os.sep) if rel != '.' else 0
        if depth < max_depth:
            dirs_found.add(rel)
    return dirs_found

# Analyze original
orig_files, orig_loc, orig_ext = count_files(original)
orig_dirs = get_dir_structure(original)

# Analyze workspace
ws_files, ws_loc, ws_ext = count_files(workspace)
ws_dirs = get_dir_structure(workspace)

# Directory overlap
common_dirs = orig_dirs & ws_dirs
dir_similarity = len(common_dirs) / max(len(orig_dirs), 1)

# Extension overlap
all_exts = set(orig_ext.keys()) | set(ws_ext.keys())
ext_overlap = {}
for ext in all_exts:
    o = orig_ext.get(ext, 0)
    w = ws_ext.get(ext, 0)
    ext_overlap[ext] = {"original": o, "generated": w, "ratio": round(w / max(o, 1), 2)}

# Go compilation check
go_compiles = False
go_mod = os.path.join(workspace, "go.mod")
if os.path.exists(go_mod):
    try:
        result = subprocess.run(
            ["go", "build", "./..."],
            cwd=workspace, capture_output=True, text=True, timeout=60
        )
        go_compiles = result.returncode == 0
    except:
        pass

# Python syntax check
py_syntax_ok = 0
py_syntax_fail = 0
for root, dirs, files in os.walk(workspace):
    dirs[:] = [d for d in dirs if d not in {'.git', 'node_modules', '__pycache__', 'specs'}]
    for f in files:
        if f.endswith('.py'):
            fpath = os.path.join(root, f)
            try:
                result = subprocess.run(
                    ["python3", "-m", "py_compile", fpath],
                    capture_output=True, timeout=5
                )
                if result.returncode == 0:
                    py_syntax_ok += 1
                else:
                    py_syntax_fail += 1
            except:
                py_syntax_fail += 1

validation = {
    "run_id": os.path.basename(workspace),
    "timestamp": os.popen("date -u +%Y-%m-%dT%H:%M:%SZ").read().strip(),
    "original": {
        "files": orig_files,
        "loc": orig_loc,
        "extensions": orig_ext
    },
    "generated": {
        "files": ws_files,
        "loc": ws_loc,
        "extensions": ws_ext
    },
    "comparison": {
        "file_count_ratio": round(ws_files / max(orig_files, 1), 2),
        "loc_ratio": round(ws_loc / max(orig_loc, 1), 2),
        "directory_similarity": round(dir_similarity, 2),
        "common_directories": len(common_dirs),
        "extension_overlap": ext_overlap
    },
    "checks": {
        "go_compiles": go_compiles,
        "python_syntax_ok": py_syntax_ok,
        "python_syntax_fail": py_syntax_fail,
        "python_syntax_rate": round(py_syntax_ok / max(py_syntax_ok + py_syntax_fail, 1), 2)
    }
}

with open(result_file, 'w') as f:
    json.dump(validation, f, indent=2)

print(f"Validation results: {result_file}")
print(f"  Files: {ws_files}/{orig_files} ({validation['comparison']['file_count_ratio']}x)")
print(f"  LOC: {ws_loc}/{orig_loc} ({validation['comparison']['loc_ratio']}x)")
print(f"  Dir similarity: {validation['comparison']['directory_similarity']}")
print(f"  Go compiles: {go_compiles}")
print(f"  Python syntax: {py_syntax_ok}/{py_syntax_ok + py_syntax_fail}")
PYEOF

echo "=== Stage 3 Complete ==="
