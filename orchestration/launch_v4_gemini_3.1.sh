#!/bin/bash
# v4.0 Trial Run: Gemini 3.1 Pro

echo "Starting v4.0 Trial: Gemini-CLI with Gemini 3.1 Pro"
nohup bash scripts/03_sdd_develop_v4.sh gemini-cli gemini-3.1-pro specs > logs/gemini_v4_trial.log 2>&1 &
PID=$!

echo "Evaluation Engine started (PID: $PID). Waiting for workspace..."
sleep 30

WS=$(ls -td workspaces/v4.0/gemini-cli_gemini-3.1-pro_* 2>/dev/null | head -1)

if [ -n "$WS" ]; then
    RUN_ID=$(basename "$WS")
    echo "Workspace found: $WS. Launching v4.0 Supervisor..."
    nohup bash orchestration/supervise_v4.sh $PID "$RUN_ID" "$WS" "gemini-cli" "gemini-3.1-pro" > logs/sup_gemini_v4_trial.log 2>&1 &
    SUP_PID=$!
    echo "v4.0 Supervisor started (PID: $SUP_PID)."
else
    echo "ERROR: Failed to find workspace."
    kill $PID 2>/dev/null
    exit 1
fi
