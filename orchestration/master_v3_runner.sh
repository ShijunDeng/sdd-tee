#!/bin/bash
# Master runner for v3.0 - Automated Orchestrator

echo "Starting Task Group 1 (Gemini & MiniMax)..."
bash launch_v3_group1.sh

# Give it a moment to start and print PIDs
sleep 20

# We need to find the PIDs of 03_sdd_develop_v3.sh
PID_GEMINI=$(ps aux | grep "03_sdd_develop_v3.sh gemini-cli" | grep -v grep | awk '{print $2}' | head -1)
PID_MINIMAX=$(ps aux | grep "03_sdd_develop_v3.sh opencode-cli bailian-coding-plan/MiniMax-M2.5" | grep -v grep | awk '{print $2}' | head -1)

if [ -z "$PID_GEMINI" ] && [ -z "$PID_MINIMAX" ]; then
    echo "ERROR: Could not find Task Group 1 processes. Check logs."
    exit 1
fi

echo "Monitoring Task Group 1. Gemini PID: $PID_GEMINI, MiniMax PID: $PID_MINIMAX"

while ps -p $PID_GEMINI > /dev/null || ps -p $PID_MINIMAX > /dev/null; do
    echo "[$(date)] Task Group 1 still running..."
    sleep 600
done

echo "Task Group 1 completed. Starting remaining tasks (Groups 2, 3, 4)..."
nohup bash orchestration/launch_v3_remaining.sh > logs/master_v3_remaining.log 2>&1 &
echo "Master runner finished. Task groups 2-4 are running in background."
