#!/bin/bash
# 启动 Gemini (任务2)
bash scripts/03_sdd_develop_v3.sh gemini-cli gemini-3.1-pro-preview specs > gemini_v3.log 2>&1 &
PID2=$!
sleep 5
WS2=$(ls -td workspaces/gemini-cli_gemini-3.1-pro-preview_* 2>/dev/null | head -1)
RUN2=$(basename "$WS2")
bash supervise_v3.sh $PID2 "$RUN2" "$WS2" "gemini-cli" "gemini-3.1-pro-preview" > sup_gemini_v3.log 2>&1 &
echo "Task 2 (Gemini) started. Engine: $PID2, Supervisor: $!"

# 启动 MiniMax (任务3)
bash scripts/03_sdd_develop_v3.sh opencode-cli opencode/minimax-m2.5-free specs > minimax_v3.log 2>&1 &
PID3=$!
sleep 5
WS3=$(ls -td workspaces/opencode-cli_opencode_minimax-m2.5-free_* 2>/dev/null | head -1)
RUN3=$(basename "$WS3")
bash supervise_v3.sh $PID3 "$RUN3" "$WS3" "opencode-cli" "opencode/minimax-m2.5-free" > sup_minimax_v3.log 2>&1 &
echo "Task 3 (MiniMax) started. Engine: $PID3, Supervisor: $!"

# 启动 Qwen (任务4)
bash scripts/03_sdd_develop_v3.sh opencode-cli bailian-coding-plan/qwen3.5-plus specs > qwen_v3.log 2>&1 &
PID4=$!
sleep 5
WS4=$(ls -td workspaces/opencode-cli_bailian-coding-plan_qwen3.5-plus_* 2>/dev/null | head -1)
RUN4=$(basename "$WS4")
bash supervise_v3.sh $PID4 "$RUN4" "$WS4" "opencode-cli" "bailian-coding-plan/qwen3.5-plus" > sup_qwen_v3.log 2>&1 &
echo "Task 4 (Qwen) started. Engine: $PID4, Supervisor: $!"
