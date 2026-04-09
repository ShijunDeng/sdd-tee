#!/bin/bash
# SDD-TEE v4.0 Pipeline RESUME
LOG_DIR="logs/pipeline_v2"
mkdir -p "$LOG_DIR"
GLOBAL_LOG="$LOG_DIR/resume.log"
exec >> "$GLOBAL_LOG" 2>&1

# 只跑剩下的模型
models=("bailian-coding-plan/glm-4.7" "bailian-coding-plan/qwen3.5-plus" "gemini-3.1-pro")
tools=("opencode-cli" "opencode-cli" "gemini-cli")

echo "[$(date)] Pipeline RESUME Started."

for i in "${!models[@]}"; do
    MODEL="${models[$i]}"
    TOOL="${tools[$i]}"
    RUN_NAME=$(echo $MODEL | sed 's/\//-/g')
    
    echo "[$(date)] >>> STARTING MODEL: $MODEL <<<"
    bash scripts/03_sdd_develop_v4.sh "$TOOL" "$MODEL" specs > "$LOG_DIR/${RUN_NAME}.log" 2>&1 &
    PID=$!
    
    sleep 30
    WS=$(ls -td workspaces/v4.0/${TOOL}_${RUN_NAME}_* 2>/dev/null | head -1)
    if [ -n "$WS" ]; then
        RUN_ID=$(basename "$WS")
        bash orchestration/supervise_v4.sh "$PID" "$RUN_ID" "$WS" "$TOOL" "$MODEL" >> "$LOG_DIR/${RUN_NAME}_sup.log" 2>&1
        echo "[$(date)] Model $MODEL Completed."
    fi
    sync && sleep 60
done
echo "[$(date)] All Remaining tests Finished."
