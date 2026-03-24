#!/bin/bash
# Remaining tasks from next.md (Groups 2, 3, 4)
# This script should be run AFTER Task Group 1 finishes.

# Task Group 2
echo "Starting Task Group 2: Qwen3.5 Plus"
bash scripts/03_sdd_develop_v3.sh opencode-cli bailian-coding-plan/qwen3.5-plus specs > qwen_v3_g2.log 2>&1 &
PID2=$!
sleep 15
WS2=$(ls -td workspaces/v3.0/opencode-cli_bailian-coding-plan_qwen3.5-plus_* 2>/dev/null | head -1)
if [ -n "$WS2" ]; then
    RUN2=$(basename "$WS2")
    bash supervise_v3.sh $PID2 "$RUN2" "$WS2" "opencode-cli" "bailian-coding-plan/qwen3.5-plus" > sup_qwen_v3_g2.log 2>&1
fi

# Task Group 3
echo "Starting Task Group 3: GLM-5"
bash scripts/03_sdd_develop_v3.sh opencode-cli bailian-coding-plan/glm-5 specs > glm5_v3_g3.log 2>&1 &
PID3=$!
sleep 15
WS3=$(ls -td workspaces/v3.0/opencode-cli_bailian-coding-plan_glm-5_* 2>/dev/null | head -1)
if [ -n "$WS3" ]; then
    RUN3=$(basename "$WS3")
    bash supervise_v3.sh $PID3 "$RUN3" "$WS3" "opencode-cli" "bailian-coding-plan/glm-5" > sup_glm5_v3_g3.log 2>&1
fi

# Task Group 4
echo "Starting Task Group 4: GLM-4.7"
bash scripts/03_sdd_develop_v3.sh opencode-cli bailian-coding-plan/glm-4.7 specs > glm47_v3_g4.log 2>&1 &
PID4=$!
sleep 15
WS4=$(ls -td workspaces/v3.0/opencode-cli_bailian-coding-plan_glm-4.7_* 2>/dev/null | head -1)
if [ -n "$WS4" ]; then
    RUN4=$(basename "$WS4")
    bash supervise_v3.sh $PID4 "$RUN4" "$WS4" "opencode-cli" "bailian-coding-plan/glm-4.7" > sup_glm47_v3_g4.log 2>&1
fi

echo "All remaining tasks in next.md completed."
