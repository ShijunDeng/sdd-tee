#!/usr/bin/env python3
"""
Stage 3: Validate generated code against original project.
Usage: python3 scripts/03_validate.py <workspace_dir> <original_dir> <output_file>
"""

import os
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

EXCLUDE_DIRS = {'.git', 'node_modules', '__pycache__', '.mypy_cache', '.ruff_cache',
                '.pytest_cache', 'specs', '.egg-info', 'egg-info', 'venv', '.venv'}
EXCLUDE_EXTS = {'.pyc', '.pyo', '.egg-info'}


def walk_files(directory, exclude_dirs=None, exclude_exts=None):
    exclude_dirs = exclude_dirs or EXCLUDE_DIRS
    exclude_exts = exclude_exts or EXCLUDE_EXTS
    for root, dirs, files in os.walk(directory):
        dirs[:] = [d for d in dirs if d not in exclude_dirs and not d.endswith('.egg-info')]
        for f in files:
            ext = os.path.splitext(f)[1]
            if ext in exclude_exts:
                continue
            yield os.path.join(root, f)


def count_stats(directory):
    total_files = 0
    total_loc = 0
    by_ext = {}
    for fpath in walk_files(directory):
        total_files += 1
        ext = os.path.splitext(fpath)[1] or '.no_ext'
        by_ext[ext] = by_ext.get(ext, 0) + 1
        try:
            with open(fpath, errors='ignore') as fh:
                total_loc += sum(1 for _ in fh)
        except Exception:
            pass
    return total_files, total_loc, by_ext


def get_dir_tree(directory, max_depth=3):
    dirs_found = set()
    for root, dirs, files in os.walk(directory):
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS and not d.endswith('.egg-info')]
        rel = os.path.relpath(root, directory)
        depth = rel.count(os.sep) if rel != '.' else 0
        if depth < max_depth:
            dirs_found.add(rel)
    return dirs_found


def get_file_tree(directory):
    files = set()
    for fpath in walk_files(directory):
        files.add(os.path.relpath(fpath, directory))
    return files


def check_python_syntax(directory):
    ok = 0
    fail = 0
    errors = []
    for fpath in walk_files(directory):
        if fpath.endswith('.py'):
            try:
                result = subprocess.run(
                    [sys.executable, '-m', 'py_compile', fpath],
                    capture_output=True, text=True, timeout=10
                )
                if result.returncode == 0:
                    ok += 1
                else:
                    fail += 1
                    errors.append({
                        'file': os.path.relpath(fpath, directory),
                        'error': result.stderr.strip()[:200]
                    })
            except Exception as e:
                fail += 1
                errors.append({'file': os.path.relpath(fpath, directory), 'error': str(e)[:200]})
    return ok, fail, errors


def check_yaml_syntax(directory):
    try:
        import yaml
    except ImportError:
        return -1, 0, [], 0

    ok = 0
    fail = 0
    skipped_helm = 0
    errors = []
    for fpath in walk_files(directory):
        if fpath.endswith(('.yaml', '.yml')):
            rel = os.path.relpath(fpath, directory)
            # Helm templates contain Go template syntax ({{ }}) which is not valid YAML
            is_helm_template = '/templates/' in rel
            try:
                with open(fpath) as f:
                    content = f.read()
                if is_helm_template and '{{' in content:
                    skipped_helm += 1
                    continue
                list(yaml.safe_load_all(content))
                ok += 1
            except Exception as e:
                fail += 1
                errors.append({'file': rel, 'error': str(e)[:200]})
    return ok, fail, errors, skipped_helm


def main():
    if len(sys.argv) < 4:
        print(f"Usage: {sys.argv[0]} <workspace> <original> <output_file>")
        sys.exit(1)

    workspace = sys.argv[1]
    original = sys.argv[2]
    output_file = sys.argv[3]

    print("=== Stage 3: Validation ===")
    print(f"Workspace: {workspace}")
    print(f"Original:  {original}")
    print(f"Output:    {output_file}")

    # Stats
    orig_files, orig_loc, orig_ext = count_stats(original)
    ws_files, ws_loc, ws_ext = count_stats(workspace)

    print(f"\nOriginal: {orig_files} files, {orig_loc} LOC")
    print(f"Generated: {ws_files} files, {ws_loc} LOC")

    # Directory overlap
    orig_dirs = get_dir_tree(original)
    ws_dirs = get_dir_tree(workspace)
    common_dirs = orig_dirs & ws_dirs
    dir_similarity = len(common_dirs) / max(len(orig_dirs), 1)

    # File overlap
    orig_file_tree = get_file_tree(original)
    ws_file_tree = get_file_tree(workspace)
    common_files = orig_file_tree & ws_file_tree
    file_overlap = len(common_files) / max(len(orig_file_tree), 1)

    # Extension comparison
    all_exts = sorted(set(orig_ext.keys()) | set(ws_ext.keys()), key=lambda e: orig_ext.get(e, 0), reverse=True)
    ext_comparison = {}
    for ext in all_exts:
        o = orig_ext.get(ext, 0)
        w = ws_ext.get(ext, 0)
        ext_comparison[ext] = {
            "original": o,
            "generated": w,
            "ratio": round(w / max(o, 1), 2)
        }

    # Python syntax check
    print("\nChecking Python syntax...")
    py_ok, py_fail, py_errors = check_python_syntax(workspace)
    py_rate = round(py_ok / max(py_ok + py_fail, 1), 4)
    print(f"  Python: {py_ok} OK, {py_fail} FAIL ({py_rate*100:.1f}%)")

    # YAML syntax check
    print("Checking YAML syntax...")
    yaml_ok, yaml_fail, yaml_errors, yaml_helm_skipped = check_yaml_syntax(workspace)
    if yaml_ok >= 0:
        yaml_rate = round(yaml_ok / max(yaml_ok + yaml_fail, 1), 4)
        print(f"  YAML: {yaml_ok} OK, {yaml_fail} FAIL, {yaml_helm_skipped} Helm templates skipped ({yaml_rate*100:.1f}%)")
    else:
        yaml_rate = -1
        yaml_helm_skipped = 0
        print("  YAML: skipped (pyyaml not installed)")

    # Key file presence check
    key_files = [
        'go.mod', 'Makefile', 'README.md', 'LICENSE',
        'cmd/router/main.go', 'cmd/workload-manager/main.go',
        'cmd/agentd/main.go', 'cmd/picod/main.go',
        'cmd/cli/pyproject.toml', 'cmd/cli/agentcube/cli/main.py',
        'sdk-python/pyproject.toml', 'sdk-python/agentcube/__init__.py',
        'pkg/apis/runtime/v1alpha1/types.go',
        'pkg/store/store.go', 'pkg/store/redis.go',
        'pkg/router/server.go', 'pkg/router/jwt.go',
        'pkg/workloadmanager/server.go',
        'pkg/picod/server.go', 'pkg/agentd/reconciler.go',
        'manifests/charts/base/Chart.yaml',
        'manifests/charts/base/values.yaml',
        'docker/Dockerfile', 'docker/Dockerfile.router', 'docker/Dockerfile.picod',
    ]
    key_files_present = 0
    key_files_missing = []
    for kf in key_files:
        if os.path.exists(os.path.join(workspace, kf)):
            key_files_present += 1
        else:
            key_files_missing.append(kf)

    key_file_rate = round(key_files_present / len(key_files), 4)
    print(f"\nKey files: {key_files_present}/{len(key_files)} ({key_file_rate*100:.1f}%)")
    if key_files_missing:
        print(f"  Missing: {', '.join(key_files_missing[:10])}")

    # Build result
    result = {
        "run_id": os.path.basename(workspace),
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
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
            "file_count_ratio": round(ws_files / max(orig_files, 1), 4),
            "loc_ratio": round(ws_loc / max(orig_loc, 1), 4),
            "directory_similarity": round(dir_similarity, 4),
            "common_directories": len(common_dirs),
            "total_original_directories": len(orig_dirs),
            "file_overlap_ratio": round(file_overlap, 4),
            "common_files": len(common_files),
            "total_original_files": len(orig_file_tree),
            "extension_comparison": ext_comparison
        },
        "checks": {
            "python_syntax_ok": py_ok,
            "python_syntax_fail": py_fail,
            "python_syntax_rate": py_rate,
            "python_syntax_errors": py_errors[:10],
            "yaml_syntax_ok": yaml_ok,
            "yaml_syntax_fail": yaml_fail,
            "yaml_syntax_rate": yaml_rate,
            "yaml_helm_templates_skipped": yaml_helm_skipped,
            "yaml_syntax_errors": yaml_errors[:10],
            "key_files_total": len(key_files),
            "key_files_present": key_files_present,
            "key_files_rate": key_file_rate,
            "key_files_missing": key_files_missing
        }
    }

    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    with open(output_file, 'w') as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    print(f"\n=== Validation Summary ===")
    print(f"  Files:  {ws_files}/{orig_files} ({result['comparison']['file_count_ratio']}x)")
    print(f"  LOC:    {ws_loc}/{orig_loc} ({result['comparison']['loc_ratio']}x)")
    print(f"  Dir similarity:  {dir_similarity:.2%}")
    print(f"  File overlap:    {file_overlap:.2%}")
    print(f"  Key files:       {key_file_rate:.0%}")
    print(f"  Python syntax:   {py_rate:.0%}")
    if yaml_ok >= 0:
        print(f"  YAML syntax:     {yaml_rate:.0%}")
    print(f"\nResult: {output_file}")


if __name__ == "__main__":
    main()
