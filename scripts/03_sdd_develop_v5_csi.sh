#!/usr/bin/env bash
set -euo pipefail

# =====================================================================
# SDD-TEE V5 COLD-START INCREMENTAL (CSI) RUNNER
# Goal: Simulate real-world maintenance where AI starts from a blank session
#       and must pay the "token tax" to understand existing code.
# =====================================================================

TOOL="${1:?Usage: $0 <tool> <model>}"
MODEL="${2:?Usage: $0 <tool> <model>}"
PROJECT_ROOT="$(pwd)"
RESULTS_DIR="$PROJECT_ROOT/results/runs/v3.0"
WORKSPACE_BASE="$PROJECT_ROOT/workspaces/v3.0"
SPECS_DIR="./specs"

TIMESTAMP=$(date -u +%Y%m%dT%H%M%SZ)
MODEL_SAFE="${MODEL//\//_}"
RUN_ID="${TOOL}_${MODEL_SAFE}_CSI_${TIMESTAMP}"
WORKSPACE="$WORKSPACE_BASE/$RUN_ID"
LOG_DIR="$RESULTS_DIR/${RUN_ID}_logs"

mkdir -p "$WORKSPACE" "$RESULTS_DIR" "$LOG_DIR"

# ---------------------------------------------------------------------
# 工具执行器 (强制冷启动)
# ---------------------------------------------------------------------
run_tool_cold() {
    local stage="$1"
    local ar_list="$2"
    local raw_file="$LOG_DIR/${stage}_raw.json"
    local log_file="$LOG_DIR/${stage}.log"
    
    # 构建“陌生项目”提示词，强制模型去读存量代码
    local csi_prompt="[COLD-START CHALLENGE] 
You are assigned to an EXISTING project in this directory. 
1. FIRST, explore the codebase to understand existing patterns, utilities, and CRDs.
2. THEN, implement/verify the following requirements: $ar_list.
3. DO NOT assume anything is already in your memory. Read the files on disk.
Reference specs are in ./specs/."

    echo "  [$stage] Executing $TOOL (COLD START) ..."

    local start_time=$(date +%s)
    cd "$WORKSPACE"
    case "$TOOL" in
        cursor-cli)
            # NO --continue flag, forcing a new session every stage
            timeout 900 agent --model "$MODEL" --trust "$csi_prompt" > "$log_file" 2>&1 || true
            ;;
        opencode-cli)
            # New run command without session persistence
            timeout 900 opencode run --model "$MODEL" --format json --dir "$WORKSPACE" "$csi_prompt" < /dev/null > "$raw_file" 2>&1 || true
            ;;
        gemini-cli)
            # gemini-cli is stateless by default unless session_id is reused
            gemini --model "$MODEL" --prompt "$csi_prompt" --yolo --output-format json > "$raw_file" 2>&1 || true
            ;;
    esac
    cd - > /dev/null
    local end_time=$(date +%s)
    local dur=$((end_time - start_time))

    echo "{\"stage\": \"$stage\", \"duration_seconds\": $dur, \"mode\": \"CSI\"}" > "$LOG_DIR/${stage}.json"
}

# =====================================================================
# 主执行流
# =====================================================================

# 初始化 (工作空间保留，但后续每一轮都是新 Brain)
cd "$WORKSPACE" && git init --quiet && cp -r "$PROJECT_ROOT/$SPECS_DIR" ./specs && cd - > /dev/null

declare -a ROUNDS=(
    "AR-001,AR-002,AR-003,AR-004,AR-005,AR-006,AR-007,AR-008,AR-009,AR-010,AR-011"
    "AR-012,AR-013,AR-014,AR-015,AR-016,AR-017,AR-018,AR-019,AR-020,AR-021,AR-022"
    "AR-023,AR-024,AR-025,AR-026,AR-027,AR-028,AR-029,AR-030,AR-031,AR-032,AR-033"
    "AR-034,AR-035,AR-036,AR-037,AR-038,AR-039,AR-040,AR-041,AR-042,AR-043"
)

for i in "${!ROUNDS[@]}"; do
    ROUND_NUM=$((i+1))
    AR_LIST="${ROUNDS[$i]}"
    echo "━━━━━━━━━━━━━━━━ CSI Round $ROUND_NUM / 4 (Blank Brain) ━━━━━━━━━━━━━━━━"
    
    # 每一阶段都强制冷启动，模拟最极端的“接手存量”场景
    run_tool_cold "round${ROUND_NUM}_planning" "$AR_LIST"
    run_tool_cold "round${ROUND_NUM}_implementation" "$AR_LIST"
    run_tool_cold "round${ROUND_NUM}_verify" "$AR_LIST"
done

echo "CSI Evaluation Complete. Run audit to see the Maintenance Tax."
