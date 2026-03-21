#!/usr/bin/env python3
"""
SDD-TEE Preflight Environment Check

Validates that the current environment can run a full evaluation:
  - Python dependencies installed
  - Go / Node toolchains available
  - config.yaml parseable and complete
  - specs/ directory populated with OpenSpec files
  - Target project cloneable
  - Selected tool (cursor-cli / claude-code / aider) available
  - LiteLLM Proxy reachable (if configured)

Exit codes: 0 = all pass, 1 = fatal errors, 2 = warnings only

Usage:
  python3 scripts/preflight.py [--tool cursor-cli] [--model claude-4.6-opus-high-thinking]
"""

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
PASS = "\033[32m✓\033[0m"
FAIL = "\033[31m✗\033[0m"
WARN = "\033[33m!\033[0m"


class CheckResult:
    def __init__(self):
        self.fatal = []
        self.warnings = []
        self.passed = []

    def ok(self, msg):
        self.passed.append(msg)
        print(f"  {PASS} {msg}")

    def fail(self, msg):
        self.fatal.append(msg)
        print(f"  {FAIL} {msg}")

    def warn(self, msg):
        self.warnings.append(msg)
        print(f"  {WARN} {msg}")

    @property
    def exit_code(self):
        if self.fatal:
            return 1
        if self.warnings:
            return 2
        return 0


def check_python_deps(r):
    print("\n[1/7] Python dependencies")
    required = {
        "yaml": "pyyaml",
        "litellm": "litellm",
    }
    optional = {
        "matplotlib": "matplotlib",
        "rich": "rich",
    }
    for mod, pkg in required.items():
        try:
            __import__(mod)
            r.ok(f"{pkg} installed")
        except ImportError:
            r.fail(f"{pkg} NOT installed (pip install {pkg})")
    for mod, pkg in optional.items():
        try:
            __import__(mod)
            r.ok(f"{pkg} installed (optional)")
        except ImportError:
            r.warn(f"{pkg} not installed (optional, pip install {pkg})")


def check_toolchains(r):
    print("\n[2/7] Toolchains")
    for name, cmd, min_hint in [
        ("Python", [sys.executable, "--version"], "3.9+"),
        ("Go", ["go", "version"], "1.22+"),
        ("Node", ["node", "--version"], "18+"),
        ("Git", ["git", "--version"], "2.x"),
    ]:
        if shutil.which(cmd[0]):
            try:
                ver = subprocess.check_output(cmd, stderr=subprocess.STDOUT, timeout=5).decode().strip()
                r.ok(f"{name}: {ver}")
            except Exception:
                r.ok(f"{name}: available")
        else:
            if name in ("Python", "Git"):
                r.fail(f"{name} not found (required, need {min_hint})")
            else:
                r.warn(f"{name} not found (needed for some validations, {min_hint})")


def check_config(r):
    print("\n[3/7] config.yaml")
    cfg_path = BASE / "config.yaml"
    if not cfg_path.exists():
        r.fail("config.yaml not found")
        return None
    try:
        import yaml
        with open(cfg_path) as f:
            cfg = yaml.safe_load(f)
    except Exception as e:
        r.fail(f"config.yaml parse error: {e}")
        return None

    required_keys = ["project", "methodology", "metrics", "tools", "models",
                     "spec_context", "warnings", "output"]
    for k in required_keys:
        if k in cfg:
            r.ok(f"config.{k} present")
        else:
            r.fail(f"config.{k} MISSING")

    stages = cfg.get("methodology", {}).get("stages", [])
    if len(stages) == 8:
        r.ok(f"8 stages defined (ST-0 ~ ST-7)")
    else:
        r.fail(f"Expected 8 stages, found {len(stages)}")

    metrics = cfg.get("metrics", {})
    expected_dims = {"stage": 8, "role": 4, "efficiency": 5, "quality": 4, "distribution": 4}
    for dim, count in expected_dims.items():
        actual = len(metrics.get(dim, []))
        if actual >= count:
            r.ok(f"metrics.{dim}: {actual} IDs")
        else:
            r.warn(f"metrics.{dim}: {actual} IDs (expected >= {count})")

    return cfg


def check_specs(r):
    print("\n[4/7] OpenSpec specifications")
    specs_dir = BASE / "specs"
    if not specs_dir.exists():
        r.fail("specs/ directory not found")
        return

    capabilities = [d.name for d in specs_dir.iterdir() if d.is_dir()]
    if len(capabilities) >= 8:
        r.ok(f"{len(capabilities)} capabilities found")
    else:
        r.fail(f"Only {len(capabilities)} capabilities (need >= 8)")

    missing_specs = []
    missing_designs = []
    for cap in capabilities:
        if not (specs_dir / cap / "spec.md").exists():
            missing_specs.append(cap)
        if not (specs_dir / cap / "design.md").exists():
            missing_designs.append(cap)

    if not missing_specs:
        r.ok(f"All spec.md files present")
    else:
        r.fail(f"Missing spec.md: {', '.join(missing_specs)}")

    if not missing_designs:
        r.ok(f"All design.md files present")
    else:
        r.warn(f"Missing design.md: {', '.join(missing_designs)}")

    if (specs_dir / "project.md").exists():
        r.ok("project.md present")
    else:
        r.fail("specs/project.md missing (project context)")


def check_scripts(r):
    print("\n[5/7] Pipeline scripts")
    required_scripts = {
        "04_validate.py": "Code quality validation",
        "07_sdd_tee_report.py": "Report generation (10-section 5-dimension)",
        "09_collect_run_data.py": "Run data collection with token counting",
        "schema.py": "Data schema validation contract",
    }
    optional_scripts = {
        "10_litellm_runner.py": "LiteLLM evaluation runner",
        "06_project_report.py": "Project analysis report",
        "05_aggregate.py": "Data aggregation",
    }

    for name, desc in required_scripts.items():
        if (BASE / "scripts" / name).exists():
            r.ok(f"{name}: {desc}")
        else:
            r.fail(f"{name} MISSING: {desc}")

    for name, desc in optional_scripts.items():
        if (BASE / "scripts" / name).exists():
            r.ok(f"{name}: {desc}")
        else:
            r.warn(f"{name} missing: {desc}")


def check_tool(r, tool_name):
    print(f"\n[6/7] Coding tool: {tool_name}")
    tool_cmds = {
        "cursor-cli": "cursor",
        "claude-code": "claude",
        "aider": "aider",
    }
    cmd = tool_cmds.get(tool_name, tool_name)
    if shutil.which(cmd):
        r.ok(f"{tool_name} ({cmd}) available")
    else:
        r.warn(f"{tool_name} ({cmd}) not found in PATH")


def check_litellm_proxy(r, cfg):
    print("\n[7/7] LiteLLM Proxy")
    proxy_cfg = cfg.get("litellm_proxy", {}) if cfg else {}
    if not proxy_cfg.get("enabled"):
        r.warn("LiteLLM Proxy disabled in config (token tracking will be limited)")
        return

    port = proxy_cfg.get("port", 4000)
    try:
        import urllib.request
        resp = urllib.request.urlopen(f"http://localhost:{port}/health", timeout=3)
        r.ok(f"LiteLLM Proxy reachable at localhost:{port}")
    except Exception:
        r.warn(f"LiteLLM Proxy not running on port {port} (start: litellm --config litellm_config.yaml --port {port})")

    for key_env in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY"):
        if os.environ.get(key_env):
            r.ok(f"{key_env} set")
        else:
            r.warn(f"{key_env} not set (needed for LiteLLM direct API calls)")


def main():
    parser = argparse.ArgumentParser(description="SDD-TEE Preflight Check")
    parser.add_argument("--tool", default="cursor-cli")
    parser.add_argument("--model", default="claude-4.6-opus-high-thinking")
    args = parser.parse_args()

    print("=" * 60)
    print("SDD-TEE Preflight Environment Check")
    print(f"Tool: {args.tool}  |  Model: {args.model}")
    print("=" * 60)

    r = CheckResult()
    check_python_deps(r)
    check_toolchains(r)
    cfg = check_config(r)
    check_specs(r)
    check_scripts(r)
    check_tool(r, args.tool)
    check_litellm_proxy(r, cfg)

    print("\n" + "=" * 60)
    print(f"Results: {len(r.passed)} passed, {len(r.warnings)} warnings, {len(r.fatal)} fatal")
    if r.fatal:
        print(f"\nFATAL errors ({len(r.fatal)}):")
        for e in r.fatal:
            print(f"  {FAIL} {e}")
    if r.warnings:
        print(f"\nWarnings ({len(r.warnings)}):")
        for w in r.warnings:
            print(f"  {WARN} {w}")
    print("=" * 60)

    sys.exit(r.exit_code)


if __name__ == "__main__":
    main()
