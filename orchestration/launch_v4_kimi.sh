#!/bin/bash
# v4.0 Trial Run 2: Kimi 2.5

MODEL="bailian-coding-plan/kimi-k2.5"
echo "Starting v4.0 Trial 2: OpenCode with $MODEL"

# Run in background but without nohup first to see if it behaves better
bash scripts/03_sdd_develop_v4.sh opencode-cli "$MODEL" specs > logs/kimi_v4_trial.log 2>&1 &
PID=$!

echo "Evaluation Engine started (PID: $PID). Waiting for workspace..."
sleep 20

WS=$(ls -td workspaces/v4.0/opencode-cli_bailian-coding-plan-kimi-k2.5_* 2>/dev/null | head -1)

if [ -n "$WS" ]; then
    RUN_ID=$(basename "$WS")
    echo "Workspace found: $WS. Launching v4.0 Supervisor..."
    bash orchestration/supervise_v4.sh $PID "$RUN_ID" "$WS" "opencode-cli" "$MODEL" > logs/sup_kimi_v4_trial.log 2>&1 &
    echo "v4.0 Supervisor started."
else
    echo "ERROR: Failed to find workspace."
    kill $PID 2>/dev/null
    exit 1
fi
