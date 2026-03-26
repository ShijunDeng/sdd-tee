#!/bin/bash
# v4.0 Trial Run: GLM-4.7

echo "Starting v4.0 Trial: OpenCode with GLM-4.7"
nohup bash scripts/03_sdd_develop_v4.sh opencode-cli bailian-coding-plan/glm-4.7 specs > logs/glm47_v4_trial.log 2>&1 &
PID=$!

echo "Evaluation Engine started (PID: $PID). Waiting for workspace..."
sleep 30

WS=$(ls -td workspaces/v4.0/opencode-cli_*glm-4.7_* 2>/dev/null | head -1)

if [ -n "$WS" ]; then
    RUN_ID=$(basename "$WS")
    echo "Workspace found: $WS. Launching v4.0 Supervisor..."
    nohup bash orchestration/supervise_v4.sh $PID "$RUN_ID" "$WS" "opencode-cli" "bailian-coding-plan/glm-4.7" > logs/sup_glm47_v4_trial.log 2>&1 &
    echo "v4.0 Supervisor started."
else
    echo "ERROR: Failed to find workspace."
    kill $PID 2>/dev/null
    exit 1
fi
