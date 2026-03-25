#!/usr/bin/env bash
set -euo pipefail

# SDD-TEE v4.0 Robust Runner
TOOL=$1
MODEL=$2
SPECS_DIR=$3
RUN_ID="${TOOL}_${MODEL//\//-}_$(date +%Y%m%dT%H%M%SZ)"
WORKSPACE="workspaces/v4.0/${RUN_ID}"
RESULTS_DIR="results/runs/v4.0"
LOG_DIR="${RESULTS_DIR}/${RUN_ID}_logs"

mkdir -p "$WORKSPACE/specs" "$LOG_DIR"
cp -r "$SPECS_DIR"/* "$WORKSPACE/specs/"

echo "=== SDD-TEE v4.0 Reinforced Execution: $MODEL ==="

# Helper function to call the tool with correct syntax
call_tool() {
    local prompt=$1
    local log_file=$2
    if [ "$TOOL" == "gemini-cli" ]; then
        gemini "$WORKSPACE" --model "$MODEL" --prompt "$prompt" --yolo --output-format json > "$log_file" 2>&1
    elif [ "$TOOL" == "opencode-cli" ]; then
        # CRITICAL: Added explicit instruction to WRITE files
        local final_prompt="INSTRUCTIONS: You are a senior engineer. You must use tool calls to physically WRITE files to the disk. 
        $prompt"
        opencode run "$final_prompt" --dir "$WORKSPACE" --model "$MODEL" --format json > "$log_file" 2>&1
    else
        echo "Unknown tool: $TOOL"
        exit 1
    fi
}

# 模拟 4 个开发轮次
ROUNDS=(
    "AR-001,AR-002,AR-003,AR-004,AR-005,AR-006,AR-007,AR-008,AR-009,AR-010,AR-011"
    "AR-012,AR-013,AR-014,AR-015,AR-016,AR-017,AR-018,AR-019,AR-020,AR-021,AR-022"
    "AR-023,AR-024,AR-025,AR-026,AR-027,AR-028,AR-029,AR-030,AR-031,AR-032,AR-033"
    "AR-034,AR-035,AR-036,AR-037,AR-038,AR-039,AR-040,AR-041,AR-042,AR-043"
)

for i in "${!ROUNDS[@]}"; do
    ROUND_NUM=$((i+1))
    ARS="${ROUNDS[$i]}"
    echo "--- Round $ROUND_NUM / 4: $ARS ---"

    # [ST-1] Initial Planning
    echo "  [ST-1] Initial Planning..."
    PLAN_PROMPT="Analyze the specs for $ARS and create a detailed implementation PLAN.md in the root of the project."
    call_tool "$PLAN_PROMPT" "${LOG_DIR}/round${ROUND_NUM}_planning_raw.json"

    # [ST-1.5] Clarification Iteration
    echo "  [ST-1.5] Clarification Iteration (Simulated Conflict)..."
    CLARIFY_PROMPT="I noticed a potential conflict in the plan for $ARS. Should we prioritize using Middleware or Direct Handlers for the components? Compare both and justify your choice in PLAN.md before proceeding to code."
    call_tool "$CLARIFY_PROMPT" "${LOG_DIR}/round${ROUND_NUM}_clarify_raw.json"

    # [ST-5] Implementation
    echo "  [ST-5] Implementation (TDD Reinforced)..."
    APPLY_PROMPT="Now implement all files for $ARS following the clarified plan. 
    CRITICAL: You MUST use file-writing tools to create the source code and tests.
    Implement unit tests as defined in specs/testing/agentcube_tdd_manifest.md. Achieve Test-to-Code ratio > 0.4. Ensure full code and test suites, not stubs."
    call_tool "$APPLY_PROMPT" "${LOG_DIR}/round${ROUND_NUM}_implementation_raw.json"
    
    sleep 30
done

echo "=== v4.0 Primary Execution Complete ==="
echo "Workspace: $WORKSPACE"
