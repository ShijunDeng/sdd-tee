#!/usr/bin/env bash
set -euo pipefail

# =====================================================================
# SDD-TEE V2 REINFORCED RUNNER
# 增加了三项核心看护：Session 强制隔离、产出 Delta 审计、自动重试纠偏
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

mkdir -p "$WORKSPACE" "$RESULTS_DIR" "$LOG_DIR"

# --- 辅助函数：统计真实业务代码行数 ---
get_effective_loc() {
    find "$WORKSPACE" -name "*.go" -o -name "*.py" 2>/dev/null | grep -vE "venv|node_modules|specs" | xargs wc -l 2>/dev/null | tail -n 1 | awk '{print $1}' || echo 0
}

# --- 辅助函数：Session 清理逻辑 ---
reset_tool_session() {
    echo "  [Guard] Resetting $TOOL session context..."
    case "$TOOL" in
        gemini-cli)
            # 暴力清理 gemini-cli 的本地会话存储（基于其默认存储路径）
            rm -rf ~/.config/gemini/sessions/* 2>/dev/null || true ;;
        claude-code)
            # Claude Code 默认通过新目录隔离上下文
            ;;
    esac
}

# --- 强化版 Prompt 模板 ---
STRICT_INSTRUCTION="[SYSTEM: REALISM ENFORCEMENT]
1. DO NOT use placeholder comments (e.g., '// ... implementation here').
2. DO NOT use stubs or empty functions.
3. Every AR must result in actual code written to the file system.
4. If you fail to write code, this test fails.
"

# --- 执行引擎 (以 Gemini 为例) ---
run_step() {
    local stage="$1"
    local prompt="$2"
    local raw_file="$LOG_DIR/${stage}_raw.json"
    
    echo "  [$stage] Executing..."
    
    # 注入严格指令
    local final_prompt="${STRICT_INSTRUCTION}\n\n${prompt}"
    
    case "$TOOL" in
        gemini-cli)
            cd "$WORKSPACE"
            gemini --model "$MODEL" --prompt "$final_prompt" --yolo --output-format json > "$raw_file" 2>&1 || true
            cd - > /dev/null ;;
        opencode-cli)
            timeout 600 opencode run --model "$MODEL" --format json --dir "$WORKSPACE" "$final_prompt" < /dev/null > "$raw_file" 2>&1 || true ;;
        *)
            echo "Tool $TOOL runner not reinforced yet."; exit 1 ;;
    esac
}

# =====================================================================
# 主逻辑：4 Rounds × 3 Phases
# =====================================================================

declare -a ROUNDS=(
    "AR-001,AR-002,AR-003,AR-004,AR-005,AR-006,AR-007,AR-008,AR-009,AR-010,AR-011"
    "AR-012,AR-013,AR-014,AR-015,AR-016,AR-017,AR-018,AR-019,AR-020,AR-021,AR-022"
    "AR-023,AR-024,AR-025,AR-026,AR-027,AR-028,AR-029,AR-030,AR-031,AR-032,AR-033"
    "AR-034,AR-035,AR-036,AR-037,AR-038,AR-039,AR-040,AR-041,AR-042,AR-043"
)

# 初始化仓库
cd "$WORKSPACE" && git init --quiet && cp -r "$PROJECT_ROOT/$SPECS_DIR" ./specs && cd - > /dev/null

for i in "${!ROUNDS[@]}"; do
    ROUND_NUM=$((i+1))
    AR_LIST="${ROUNDS[$i]}"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━ Round $ROUND_NUM ━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    
    # 1. 每一轮强制重置会话，保证真实性
    reset_tool_session

    # 记录 Round 前的代码量
    LOC_START=$(get_effective_loc)

    # Phase 1: Planning
    run_step "round${ROUND_NUM}_planning" "Plan the implementation for ARs: $AR_LIST. Create PLAN.md."
    
    # Phase 2: Implementation (The Realism Gate)
    run_step "round${ROUND_NUM}_implementation" "Implement all ARs in $AR_LIST. Use 'write_to_file' for every file. NO STUBS."
    
    # [Realism Gate Check]
    LOC_END=$(get_effective_loc)
    DELTA=$((LOC_END - LOC_START))
    echo "  [Gate] LOC Delta: $DELTA lines."
    
    if [ "$DELTA" -le 10 ]; then
        echo "  [⚠ ALERT] Zero or near-zero code output detected! Triggering Correction Nudge..."
        run_step "round${ROUND_NUM}_retry" "Your previous response resulted in almost no code changes. You MUST provide the full implementation now for: $AR_LIST. Don't apologize, just write the files."
        LOC_AFTER_RETRY=$(get_effective_loc)
        echo "  [Gate] LOC Delta after retry: $((LOC_AFTER_RETRY - LOC_START)) lines."
    fi

    # Phase 3: Verification
    run_step "round${ROUND_NUM}_verify" "Verify and fix errors for $AR_LIST. Ensure it compiles."
done

echo "Evaluation Complete. Realism-checked data is in $LOG_DIR."
