#!/usr/bin/env bash
set -euo pipefail

# SDD-TEE v4.0 Robust Supervisor
# Usage: ./supervise_v4.sh <PID> <RUN_ID> <WORKSPACE> <TOOL> <MODEL>

PID=$1
RUN_ID=$2
WORKSPACE=$3
TOOL=$4
MODEL=$5
RESULTS_DIR="results/runs/v4.0"
LOG_DIR="${RESULTS_DIR}/${RUN_ID}_logs"
mkdir -p "$LOG_DIR"

# --- MEMORY PROTECTION ---
# Protect the supervisor from OOM (highest priority to stay alive)
echo -1000 > /proc/$$/oom_score_adj 2>/dev/null || true

echo "[v4.0 Guard] Monitoring Evaluation Engine (PID: $PID)..."

# 等待主进程结束
while ps -p $PID > /dev/null; do sleep 30; done
echo "[v4.0 Guard] Initial execution rounds completed."

# --- 闭环纠偏与自愈环节 (Self-Healing Loop) ---

MAX_HEALING_ITERATIONS=2
for ((i=1; i<=MAX_HEALING_ITERATIONS; i++)); do
    echo "[v4.0 Guard] Self-Healing Iteration $i/ $MAX_HEALING_ITERATIONS..."
    
    # 1. 静态检查与测试运行
    ERR_LOG=""
    # Resolve absolute path for workspace to avoid directory jumping issues
    ABS_WORKSPACE=$(cd "$WORKSPACE" && pwd)
    if ls "$ABS_WORKSPACE"/*.go >/dev/null 2>&1 || [ -d "$ABS_WORKSPACE/pkg" ]; then
        echo "  Checking Go build & tests in $ABS_WORKSPACE..."
        cd "$ABS_WORKSPACE" && go build ./... > check_err.log 2>&1 && go test ./... >> check_err.log 2>&1 || ERR_LOG=$(cat check_err.log)
        # 增加测试密度校验
        TEST_COUNT=$(grep -r "func Test" "$ABS_WORKSPACE" | wc -l)
        if [ "$TEST_COUNT" -lt 5 ]; then ERR_LOG="Insufficient unit tests found (Count: $TEST_COUNT). You must implement at least 5-10 tests per round as per TDD manifest."; fi
        cd - >/dev/null
    elif ls "$ABS_WORKSPACE"/*.py >/dev/null 2>&1 || [ -d "$ABS_WORKSPACE/sdk-python" ]; then
        echo "  Checking Python syntax & tests in $ABS_WORKSPACE..."
        python3 -m pytest "$ABS_WORKSPACE" > check_err.log 2>&1 || ERR_LOG=$(cat check_err.log)
        TEST_COUNT=$(grep -r "def test_" "$ABS_WORKSPACE" | wc -l)
        if [ "$TEST_COUNT" -lt 5 ]; then ERR_LOG="Insufficient pytest cases found. Add more tests."; fi
    fi

    if [ -z "$ERR_LOG" ]; then
        echo "[v4.0 Guard] Validation PASSED. No healing required."
        break
    fi

    echo "[v4.0 Guard] Validation FAILED. Error detected. Triggering correction..."
    
    # 2. 构造纠偏指令并调用工具
    FIX_PROMPT="Your previous implementation has the following build errors. Please analyze the logs and fix all files to ensure a successful build. Use the actual project root at $WORKSPACE:\n\n$ERR_LOG"
    
    RAW_FIX_LOG="${LOG_DIR}/self_healing_v4_${i}_raw.json"
    
    echo "  Invoking $TOOL for correction (this consumes additional tokens)..."
    if [ "$TOOL" == "gemini-cli" ]; then
        gemini "$WORKSPACE" --model "$MODEL" --prompt "$FIX_PROMPT" --yolo --output-format json > "$RAW_FIX_LOG" 2>&1 || true
    elif [ "$TOOL" == "opencode-cli" ]; then
        opencode run "$FIX_PROMPT" --dir "$WORKSPACE" --model "$MODEL" --format json > "$RAW_FIX_LOG" 2>&1 || true
    fi
done

# --- 数据聚合与精密审计 ---

echo "[v4.0 Guard] Starting Precision Token Audit (v4.0 Sum-of-Turns)..."

export __RUN_ID="$RUN_ID"
export __WORKSPACE="$WORKSPACE"
export __MODEL="$MODEL"
export __TOOL="$TOOL"
export __ITERATION="$i"

python3 << 'PYEOF'
import json, os, glob, sys, datetime
from decimal import Decimal

# 导入刚才写的审计逻辑
sys.path.append('scripts/utils')
from token_audit_v4 import audit_tokens_cumulative, get_physical_loc

run_id = os.environ.get('__RUN_ID', 'v4_run')
log_dir = f"results/runs/v4.0/{run_id}_logs"
workspace = os.environ.get('__WORKSPACE', '.')
model = os.environ.get('__MODEL', 'unknown')
tool = os.environ.get('__TOOL', 'unknown')
iteration = int(os.environ.get('__ITERATION', '0'))

# 1. 严格累加所有日志（含纠偏日志）
in_tok, out_tok, cr_tok = audit_tokens_cumulative(log_dir)
loc = get_physical_loc(workspace)

# 2. 成本核算 (计入所有纠偏开销)
# 价格参考: In $15/M, Out $75/M, CacheRead $1.5/M
net_in = max(0, in_tok - cr_tok)
cost_usd = (net_in * 15.0 + cr_tok * 1.5 + out_tok * 75.0) / 1e6

res = {
    "run_id": run_id,
    "timestamp": datetime.datetime.now().strftime("%Y%m%dT%H%M%SZ"),
    "project": "agentcube",
    "tool": tool,
    "model": model,
    "token_summary": {
        "input_tokens": in_tok,
        "output_tokens": out_tok,
        "cache_read_tokens": cr_tok,
        "total_tokens": in_tok + out_tok,
        "cost_usd": float(round(cost_usd, 4))
    },
    "quality": {
        "loc_generated": loc,
        "build_status": "PASSED" if iteration < 2 else "FAILED" 
    }
}

# 保存最终数据
target_file = f"results/runs/v4.0/{run_id}_full.json"
with open(target_file, 'w') as f:
    json.dump(res, f, indent=2)
print(f"Final Data → {target_file}")
PYEOF

# 3. 生成报告并提交
python3 scripts/07_sdd_tee_report.py --data "results/runs/v4.0/${RUN_ID}_full.json" --output "results/reports/v4.0/${RUN_ID}_report.html" || true
python3 scripts/11_compare_runs.py --runs results/runs/v4.0/*_full.json --output results/reports/v4.0/compare_report.html || true

git add . && git commit -m "v4.0: Auto-healing & precision audit for $MODEL" || true
git push origin main || true

echo "[v4.0 Guard] Supervisor pipeline fully completed."
