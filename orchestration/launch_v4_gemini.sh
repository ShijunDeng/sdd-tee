#!/bin/bash
# v4.0 Trial Run 3: Gemini 1.5 Pro 002

MODEL="gemini-1.5-pro-002"
echo "Starting v4.0 Trial 3: Gemini-CLI with $MODEL"

# Run with nohup to survive session logout
nohup bash scripts/03_sdd_develop_v4.sh gemini-cli "$MODEL" specs > logs/gemini_v4_trial.log 2>&1 &
PID=$!

echo "Evaluation Engine started (PID: $PID). Waiting for workspace..."
sleep 20

WS=$(ls -td workspaces/v4.0/gemini-cli_gemini-1.5-pro-002_* 2>/dev/null | head -1)

if [ -n "$WS" ]; then
    RUN_ID=$(basename "$WS")
    echo "Workspace found: $WS. Launching v4.0 Supervisor..."
    nohup bash orchestration/supervise_v4.sh $PID "$RUN_ID" "$WS" "gemini-cli" "$MODEL" > logs/sup_gemini_v4_trial.log 2>&1 &
    echo "v4.0 Supervisor started."
else
    echo "ERROR: Failed to find workspace."
    kill $PID 2>/dev/null
    exit 1
fi
