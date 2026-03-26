#!/bin/bash
# SDD-TEE v4.0 Robust Pipeline v2
LOG_DIR="logs/pipeline_v2"
mkdir -p "$LOG_DIR"
GLOBAL_LOG="$LOG_DIR/global.log"
exec >> "$GLOBAL_LOG" 2>&1

models=("bailian-coding-plan/glm-5" "bailian-coding-plan/glm-4.7" "bailian-coding-plan/qwen3.5-plus" "gemini-3.1-pro")
tools=("opencode-cli" "opencode-cli" "opencode-cli" "gemini-cli")

echo "[$(date)] Pipeline v2 Started."

for i in "${!models[@]}"; do
    MODEL="${models[$i]}"
    TOOL="${tools[$i]}"
    RUN_NAME=$(echo $MODEL | sed 's/\//-/g')
    
    echo "[$(date)] >>> STARTING MODEL: $MODEL <<<"
    
    # 显式重定向各模型日志
    bash scripts/03_sdd_develop_v4.sh "$TOOL" "$MODEL" specs > "$LOG_DIR/${RUN_NAME}.log" 2>&1 &
    PID=$!
    
    echo "[$(date)] Engine Started (PID: $PID). Monitoring..."
    
    # 启动监督进程
    sleep 30
    WS=$(ls -td workspaces/v4.0/${TOOL}_${RUN_NAME}_* 2>/dev/null | head -1)
    if [ -n "$WS" ]; then
        RUN_ID=$(basename "$WS")
        # 监督进程会阻塞直到 PID 结束
        bash orchestration/supervise_v4.sh "$PID" "$RUN_ID" "$WS" "$TOOL" "$MODEL" >> "$LOG_DIR/${RUN_NAME}_sup.log" 2>&1
        echo "[$(date)] Model $MODEL Completed."
    else
        echo "[$(date)] ERROR: Failed to find workspace for $MODEL."
        kill $PID 2>/dev/null
    fi
    
    # 任务间强制休息以释放内存缓存
    echo "[$(date)] Task cleanup and rest for 60s..."
    sync && echo 3 > /proc/sys/vm/drop_caches 2>/dev/null || true
    sleep 60
done

echo "[$(date)] Pipeline v2 Finished."
