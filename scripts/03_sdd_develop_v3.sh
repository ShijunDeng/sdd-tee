#!/usr/bin/env bash
set -euo pipefail

# =====================================================================
# SDD-TEE V3 REINFORCED RUNNER (REALISM GUARD ARCHITECTURE)
# Supports: cursor-cli, claude-code, gemini-cli, opencode-cli
# Features: Session Isolation, LOC Delta Gate, Auto-Retry Penalty
# =====================================================================

TOOL="${1:?Usage: $0 <tool> <model> [specs_dir]}"
MODEL="${2:?Usage: $0 <tool> <model> [specs_dir]}"
SPECS_DIR="${3:-./specs}"
PROJECT_ROOT="$(pwd)"
RESULTS_DIR="$PROJECT_ROOT/results/runs"
WORKSPACE_BASE="$PROJECT_ROOT/workspaces"

TIMESTAMP=$(date -u +%Y%m%dT%H%M%SZ)
MODEL_SAFE="${MODEL//\//_}"
RUN_ID="${TOOL}_${MODEL_SAFE}_${TIMESTAMP}"
WORKSPACE="$WORKSPACE_BASE/$RUN_ID"
LOG_DIR="$RESULTS_DIR/${RUN_ID}_logs"
RESULT_FILE="$RESULTS_DIR/${RUN_ID}.json"

mkdir -p "$WORKSPACE" "$RESULTS_DIR" "$LOG_DIR"

# ---------------------------------------------------------------------
# 1. 真实性度量核心：精准统计业务代码行数
# ---------------------------------------------------------------------
get_effective_loc() {
    # 仅统计 Go 和 Python 源码，严格排除虚拟环境、缓存和规范文档
    local loc
    loc=$(find "$WORKSPACE" -type f \( -name "*.go" -o -name "*.py" \) \
          -not -path "*/venv/*" \
          -not -path "*/node_modules/*" \
          -not -path "*/.git/*" \
          -not -path "*/specs/*" \
          -not -path "*/__pycache__/*" \
          -exec cat {} + 2>/dev/null | wc -l)
    echo "${loc:-0}"
}

# ---------------------------------------------------------------------
# 2. 会话状态隔离：切断 AI 幻觉
# ---------------------------------------------------------------------
reset_tool_session() {
    echo "  [Guard] Enforcing Session Isolation for $TOOL..."
    case "$TOOL" in
        gemini-cli)
            # 彻底清理 Gemini 历史会话
            rm -rf ~/.config/gemini/sessions/* 2>/dev/null || true
            ;;
        claude-code|cursor-cli|opencode-cli)
            # 这些工具主要通过 CLI 单次调用保持独立，但为防万一，
            # 可以在 Prompt 中强调 "Ignore previous rounds, this is a fresh start."
            ;;
    esac
}

# ---------------------------------------------------------------------
# 3. 工具执行器包装 (含 Anti-Stub System Prompt)
# ---------------------------------------------------------------------
ANTI_STUB_PROMPT="[SYSTEM CRITICAL: REALISM ENFORCEMENT]
- YOU MUST WRITE THE FULL, PRODUCTION-READY CODE.
- DO NOT use placeholders like '// ... implementation here'.
- DO NOT leave functions empty or as stubs.
- EVERY Architectural Requirement (AR) MUST result in physical file changes.
- Failure to write complete code will result in test failure.
======================================================
"

run_tool() {
    local stage="$1"
    local raw_prompt="$2"
    local raw_file="$LOG_DIR/${stage}_raw.json"
    local log_file="$LOG_DIR/${stage}.log"
    local start_time end_time dur
    
    # 注入强制指令
    local final_prompt="${ANTI_STUB_PROMPT}\n${raw_prompt}"

    start_time=$(date +%s)
    echo "  [$stage] Executing $TOOL ..."

    cd "$WORKSPACE"
    case "$TOOL" in
        gemini-cli)
            gemini --model "$MODEL" --prompt "$final_prompt" --yolo --output-format json > "$raw_file" 2>&1 || true
            ;;
        cursor-cli)
            timeout 600 cursor agent --trust "$final_prompt" > "$log_file" 2>&1 || true
            ;;
        claude-code)
            CLAUDE_CODE_DISABLE_NONESSENTIAL=1 \
            timeout 900 claude --model "$MODEL" --output-format json --max-turns 30 --dangerously-skip-permissions --print -p "$final_prompt" > "$raw_file" 2>&1 || true
            ;;
        opencode-cli)
            timeout 600 opencode run --model "$MODEL" --format json --dir "$WORKSPACE" "$final_prompt" < /dev/null > "$raw_file" 2>&1 || true
            ;;
    esac
    cd - > /dev/null

    end_time=$(date +%s)
    dur=$((end_time - start_time))
    echo "  [$stage] Completed in ${dur}s."
    
    # 为了数据采集的健壮性，生成一个标准的 stage summary
    python3 -c "import json; print(json.dumps({'stage': '$stage', 'duration_seconds': $dur, 'tool': '$TOOL', 'input_tokens': 0, 'output_tokens': 0}))" > "$LOG_DIR/${stage}.json"
}

# =====================================================================
# 主执行流：带有门禁与重试机制的 Round 循环
# =====================================================================

# 初始化基线代码
cd "$WORKSPACE" && git init --quiet && cp -r "$PROJECT_ROOT/$SPECS_DIR" ./specs && cd - > /dev/null

declare -a ROUNDS=(
    "AR-001,AR-002,AR-003,AR-004,AR-005,AR-006,AR-007,AR-008,AR-009,AR-010,AR-011"
    "AR-012,AR-013,AR-014,AR-015,AR-016,AR-017,AR-018,AR-019,AR-020,AR-021,AR-022"
    "AR-023,AR-024,AR-025,AR-026,AR-027,AR-028,AR-029,AR-030,AR-031,AR-032,AR-033"
    "AR-034,AR-035,AR-036,AR-037,AR-038,AR-039,AR-040,AR-041,AR-042,AR-043"
)

TOTAL_START=$(date +%s)
ROUND_DATA=()

for i in "${!ROUNDS[@]}"; do
    ROUND_NUM=$((i+1))
    AR_LIST="${ROUNDS[$i]}"
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "  Round $ROUND_NUM / 4: $AR_LIST"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    
    ROUND_START=$(date +%s)
    
    # [看护点 1] 强制隔离
    reset_tool_session

    # [看护点 2] 记录门禁基准线
    LOC_START=$(get_effective_loc)
    echo "  [Gate] Base LOC before Implementation: $LOC_START"

    # Phase 1: Planning
    run_tool "round${ROUND_NUM}_planning" "Read specs in ./specs/ and create a detailed PLAN.md for these ARs: $AR_LIST. List every file to be created and the precise logic."

    # Phase 2: Implementation
    run_tool "round${ROUND_NUM}_implementation" "Implement all ARs in $AR_LIST based on the specs and PLAN.md. Write every file to the disk."

    # [看护点 3] 真实性审计
    LOC_END=$(get_effective_loc)
    LOC_DELTA=$((LOC_END - LOC_START))
    echo "  [Gate] LOC Delta after Implementation: $LOC_DELTA lines."

    if [ "$LOC_DELTA" -lt 20 ]; then
        echo "  [⚠ CRITICAL GUARD] Zero or near-zero code output detected (Delta: $LOC_DELTA)!"
        echo "  Triggering Penalty Nudge to force rewrite..."
        
        # 惩罚性重试 Prompt
        PENALTY_PROMPT="[URGENT CORRECTION] Your previous attempt FAILED to generate actual code files. The code size did not increase. You MUST RE-WRITE and actually output the complete source code to the disk for ARs: $AR_LIST. Do NOT explain, DO NOT apologize, JUST WRITE THE CODE."
        run_tool "round${ROUND_NUM}_implementation_retry" "$PENALTY_PROMPT"
        
        LOC_AFTER_RETRY=$(get_effective_loc)
        echo "  [Gate] LOC Delta after Penalty Retry: $((LOC_AFTER_RETRY - LOC_START)) lines."
    else
        echo "  [Gate] Verification Passed: Output is realistic."
    fi

    # Phase 3: Verification
    run_tool "round${ROUND_NUM}_verify" "Verify the implementation of $AR_LIST. Check imports, module references, and syntax. Fix any bugs."

    ROUND_END=$(date +%s)
    ROUND_DUR=$((ROUND_END - ROUND_START))
    ROUND_DATA+=("{\"round\": $ROUND_NUM, \"duration_seconds\": $ROUND_DUR}")
done

TOTAL_END=$(date +%s)
TOTAL_DURATION=$((TOTAL_END - TOTAL_START))

echo ""
echo "╔══════════════════════════════════════════════════════════╗"
echo "║  V3 REALISM-GUARD EVALUATION COMPLETE                    ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo "  Tool:     $TOOL"
echo "  Model:    $MODEL"
echo "  Duration: ${TOTAL_DURATION}s"
echo "  Final LOC: $(get_effective_loc)"
echo "  Logs:     $LOG_DIR"
echo "  Note: Use scripts/03_sdd_develop.sh for default execution, or manually collect data."
