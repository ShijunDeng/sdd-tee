#!/bin/bash
# 启动 GLM-4.7
bash scripts/03_sdd_develop_v3.sh opencode-cli bailian-coding-plan/glm-4.7 specs > glm_4.7_v3.log 2>&1 &
PID1=$!
sleep 3
WS1=$(ls -td workspaces/v2.0/opencode-cli_bailian-coding-plan_glm-4.7_* 2>/dev/null | head -1)
RUN1=$(basename "$WS1")
bash supervise_v3.sh $PID1 "$RUN1" "$WS1" "opencode-cli" "bailian-coding-plan/glm-4.7" > sup_glm4.7.log 2>&1 &

# 启动 GLM-5
bash scripts/03_sdd_develop_v3.sh opencode-cli bailian-coding-plan/glm-5 specs > glm_5_v3.log 2>&1 &
PID2=$!
sleep 3
WS2=$(ls -td workspaces/v2.0/opencode-cli_bailian-coding-plan_glm-5_* 2>/dev/null | head -1)
RUN2=$(basename "$WS2")
bash supervise_v3.sh $PID2 "$RUN2" "$WS2" "opencode-cli" "bailian-coding-plan/glm-5" > sup_glm5.log 2>&1 &
