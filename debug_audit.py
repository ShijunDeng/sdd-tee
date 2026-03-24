import sys, os, json, importlib.util

def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module

collector = load_module("collector", "scripts/09_collect_run_data.py")
log_dir = "results/runs/v3.0/gemini-cli_gemini-3.1-pro-preview_CSI_20260324T020158Z_logs"
telemetry = collector.audit_logs(log_dir)
print(json.dumps(telemetry, indent=2))
