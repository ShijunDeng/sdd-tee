#!/bin/bash
# Task Group 1

# Task 2: Gemini
echo "Starting Task 2: Gemini with gemini-3.1-pro-preview"
nohup bash scripts/03_sdd_develop_v3.sh gemini-cli gemini-3.1-pro-preview specs > logs/gemini_v3_g1.log 2>&1 &
PID2=$!
sleep 15
WS2=$(ls -td workspaces/v3.0/gemini-cli_gemini-3.1-pro-preview_* 2>/dev/null | head -1)
if [ -n "$WS2" ]; then
    RUN2=$(basename "$WS2")
    nohup bash orchestration/supervise_v3.sh $PID2 "$RUN2" "$WS2" "gemini-cli" "gemini-3.1-pro-preview" > logs/sup_gemini_v3_g1.log 2>&1 &
    echo "Task 2 (Gemini) started. Engine PID: $PID2, Workspace: $WS2"
else
    echo "Failed to find workspace for Gemini"
fi

# Task 3: MiniMax
echo "Starting Task 3: OpenCode with MiniMax M2.5 (bailian-coding-plan/MiniMax-M2.5)"
nohup bash scripts/03_sdd_develop_v3.sh opencode-cli bailian-coding-plan/MiniMax-M2.5 specs > logs/minimax_v3_g1.log 2>&1 &
PID3=$!
sleep 15
WS3=$(ls -td workspaces/v3.0/opencode-cli_bailian-coding-plan_MiniMax-M2.5_* 2>/dev/null | head -1)
if [ -n "$WS3" ]; then
    RUN3=$(basename "$WS3")
    nohup bash orchestration/supervise_v3.sh $PID3 "$RUN3" "$WS3" "opencode-cli" "bailian-coding-plan/MiniMax-M2.5" > logs/sup_minimax_v3_g1.log 2>&1 &
    echo "Task 3 (MiniMax) started. Engine PID: $PID3, Workspace: $WS3"
else
    echo "Failed to find workspace for MiniMax"
fi

echo "Task Group 1 restarted with nohup. Use 'ps' to monitor or check logs."
