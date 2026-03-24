#!/bin/bash
# Task Group 1: Gemini 3.1 Pro & MiniMax M2.5
# Discarding old v3.0 data was already done.

mkdir -p results/runs/v3.0 results/reports/v3.0 workspaces/v3.0

# Task 2: Gemini 3.1 Pro
echo "Starting Task 2: Gemini 3.1 Pro..."
bash scripts/03_sdd_develop_v5_csi.sh gemini-cli gemini-3.1-pro > gemini_csi.log 2>&1 &
PID_G=$!
sleep 5
WS_G=$(ls -dt workspaces/v3.0/gemini-cli_gemini-3.1-pro_* 2>/dev/null | head -1)
RUN_G=$(basename "$WS_G")
bash supervise_v3_csi.sh $PID_G "$RUN_G" "$WS_G" "gemini-cli" "gemini-3.1-pro" > sup_gemini_csi.log 2>&1 &

# Task 3: MiniMax M2.5
echo "Starting Task 3: MiniMax M2.5..."
bash scripts/03_sdd_develop_v5_csi.sh opencode-cli bailian-coding-plan/MiniMax-M2.5 > minimax_csi.log 2>&1 &
PID_M=$!
sleep 5
WS_M=$(ls -dt workspaces/v3.0/opencode-cli_bailian-coding-plan_MiniMax-M2.5_* 2>/dev/null | head -1)
RUN_M=$(basename "$WS_M")
bash supervise_v3_csi.sh $PID_M "$RUN_M" "$WS_M" "opencode-cli" "bailian-coding-plan/MiniMax-M2.5" > sup_minimax_csi.log 2>&1 &

echo "Task Group 1 launched. Use 'tail -f *.log' to monitor."
