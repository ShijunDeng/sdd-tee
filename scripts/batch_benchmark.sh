#!/usr/bin/env bash
set -euo pipefail

# SDD-TEE v5.1 Batch Benchmark Launcher
#
# Runs all tool×model combinations sequentially, generating a final comparison report.
#
# Usage:
#   ./scripts/batch_benchmark.sh [--api-base URL] [--tools T1,T2] [--models M1,M2] [--dry-run-prompts] [--original-repo PATH]

cd "$(dirname "$0")/.."

DEFAULT_COMBOS=(
    "claude-code:claude-sonnet-4"
    "claude-code:claude-4.6-opus-high-thinking"
    "gemini-cli:gemini-3.1-pro"
    "gemini-cli:gemini-2.5-pro"
    "cursor-cli:gpt-4.1"
    "opencode-cli:glm-5"
    "opencode-cli:kimi-k2.5"
)

API_BASE=""
DRY_RUN=""
ORIGINAL_REPO=""
TOOLS=""
MODELS=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --api-base)       API_BASE="$2"; shift 2 ;;
        --dry-run-prompts) DRY_RUN="--dry-run-prompts"; shift ;;
        --original-repo)  ORIGINAL_REPO="--original-repo $2"; shift 2 ;;
        --tools)           TOOLS="$2"; shift 2 ;;
        --models)          MODELS="$2"; shift 2 ;;
        *)                 echo "Unknown arg: $1"; exit 1 ;;
    esac
done

COMBOS=()
if [ -n "$TOOLS" ] || [ -n "$MODELS" ]; then
    IFS=',' read -ra TOOL_LIST <<< "${TOOLS:-claude-code,gemini-cli,cursor-cli,opencode-cli}"
    IFS=',' read -ra MODEL_LIST <<< "${MODELS:-claude-sonnet-4,gemini-3.1-pro,gpt-4.1,glm-5}"
    for t in "${TOOL_LIST[@]}"; do
        for m in "${MODEL_LIST[@]}"; do
            COMBOS+=("${t}:${m}")
        done
    done
else
    COMBOS=("${DEFAULT_COMBOS[@]}")
fi

echo "============================================================"
echo "  SDD-TEE v5.1 Batch Benchmark Launcher"
echo "============================================================"
echo ""
echo "Combinations: ${#COMBOS[@]}"
for combo in "${COMBOS[@]}"; do
    echo "  - $combo"
done
echo ""
echo "API Base:   ${API_BASE:-none}"
echo "Dry Run:    ${DRY_RUN:-no}"
echo ""

PASSED=0
FAILED=0
FAILED_LIST=()

for combo in "${COMBOS[@]}"; do
    IFS=':' read -r TOOL MODEL <<< "$combo"

    echo ""
    echo "================================================================"
    echo "  [${PASSED}+${FAILED}+1/${#COMBOS[@]}] $TOOL × $MODEL"
    echo "================================================================"

    CMD_ARGS="$TOOL $MODEL"
    [ -n "$API_BASE" ] && CMD_ARGS="$CMD_ARGS --api-base $API_BASE"
    [ -n "$DRY_RUN" ]  && CMD_ARGS="$CMD_ARGS --dry-run-prompts"
    [ -n "$ORIGINAL_REPO" ] && CMD_ARGS="$CMD_ARGS --original-repo ${ORIGINAL_REPO#--original-repo }"

    START_TIME=$(date +%s)
    if ./scripts/run_benchmark.sh $CMD_ARGS; then
        ELAPSED=$(( $(date +%s) - START_TIME ))
        echo "[OK] Completed in ${ELAPSED}s"
        PASSED=$((PASSED + 1))
    else
        ELAPSED=$(( $(date +%s) - START_TIME ))
        echo "[FAILED] $TOOL × $MODEL (took ${ELAPSED}s)"
        FAILED=$((FAILED + 1))
        FAILED_LIST+=("$TOOL:$MODEL")
    fi

    echo "  [Cooldown 10s...]"
    sleep 10
done

echo ""
echo "============================================================"
echo "  Batch Summary"
echo "============================================================"
echo "  Passed: $PASSED / ${#COMBOS[@]}"
echo "  Failed: $FAILED / ${#COMBOS[@]}"
if [ ${#FAILED_LIST[@]} -gt 0 ]; then
    echo "  Failed:"
    for f in "${FAILED_LIST[@]}"; do echo "    - $f"; done
fi

RUN_FILES=(results/runs/v5.1/*_full.json)
if [ ${#RUN_FILES[@]} -gt 0 ]; then
    echo ""
    echo "  Generating comparison report..."
    mkdir -p results/reports/v5.1

    python3 scripts/compare.py \
        --runs "${RUN_FILES[@]}" \
        --output results/reports/v5.1/compare_report.html 2>/dev/null || {
        echo "  [WARN] Comparison report generation failed"
    }

    for rf in "${RUN_FILES[@]}"; do
        python3 scripts/report.py --data "$rf" 2>/dev/null || true
    done

    echo ""
    echo "  Reports: results/reports/v5.1/"
fi

echo "============================================================"
