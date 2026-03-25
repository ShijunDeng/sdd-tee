#!/bin/bash
# v4.0 Trial Run: MiniMax M2.5

echo "Starting v4.0 Trial: OpenCode with MiniMax M2.5"
# Run with nohup to survive session logout
nohup bash scripts/03_sdd_develop_v4.sh opencode-cli bailian-coding-plan/MiniMax-M2.5 specs > logs/minimax_v4_trial.log 2>&1 &
PID=$!

echo "Evaluation Engine started (PID: $PID). Waiting for workspace..."
sleep 20

WS=$(ls -td workspaces/v4.0/opencode-cli_*MiniMax-M2.5_* 2>/dev/null | head -1)

if [ -n "$WS" ]; then
    RUN_ID=$(basename "$WS")
    echo "Workspace found: $WS. Launching v4.0 Supervisor..."
    nohup bash orchestration/supervise_v4.sh $PID "$RUN_ID" "$WS" "opencode-cli" "bailian-coding-plan/MiniMax-M2.5" > logs/sup_minimax_v4_trial.log 2>&1 &
    echo "v4.0 Supervisor started."
else
    echo "ERROR: Failed to find workspace."
    kill $PID 2>/dev/null
    exit 1
fi
