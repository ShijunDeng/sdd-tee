#!/bin/bash
# v4.0 Trial Run: Qwen3.5 Plus

echo "Starting v4.0 Trial: OpenCode with Qwen3.5 Plus"
nohup bash scripts/03_sdd_develop_v4.sh opencode-cli bailian-coding-plan/qwen3.5-plus specs > logs/qwen35_v4_trial.log 2>&1 &
PID=$!

echo "Evaluation Engine started (PID: $PID). Waiting for workspace..."
sleep 30

WS=$(ls -td workspaces/v4.0/opencode-cli_*qwen3.5-plus_* 2>/dev/null | head -1)

if [ -n "$WS" ]; then
    RUN_ID=$(basename "$WS")
    echo "Workspace found: $WS. Launching v4.0 Supervisor..."
    # 捕获监督进程的 PID 以便链式调用
    nohup bash orchestration/supervise_v4.sh $PID "$RUN_ID" "$WS" "opencode-cli" "bailian-coding-plan/qwen3.5-plus" > logs/sup_qwen35_v4_trial.log 2>&1 &
    SUP_PID=$!
    echo "v4.0 Supervisor started (PID: $SUP_PID)."
    echo $SUP_PID > logs/qwen35_sup_pid.txt
else
    echo "ERROR: Failed to find workspace."
    kill $PID 2>/dev/null
    exit 1
fi
