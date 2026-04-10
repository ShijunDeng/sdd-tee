#!/usr/bin/env bash
set -euo pipefail

# SDD-TEE v5.1 Automated Benchmark Orchestration
#
# Usage:
#   ./scripts/run_benchmark.sh <TOOL> <MODEL> [--api-base URL] [--dry-run-prompts] [--ar-limit N] [--original-repo PATH]
#
# Examples:
#   ./scripts/run_benchmark.sh claude-code claude-sonnet-4 --api-base http://localhost:4000
#   ./scripts/run_benchmark.sh gemini-cli gemini-3.1-pro
#   ./scripts/run_benchmark.sh claude-code claude-sonnet-4 --dry-run-prompts --ar-limit 1
#
# Supported tools: claude-code, gemini-cli, cursor-cli, opencode-cli
#
# Output:
#   results/runs/v5.1/{TOOL}_{MODEL}_{TIMESTAMP}_full.json

cd "$(dirname "$0")/.."

TOOL="${1:-}"
MODEL="${2:-}"
shift 2 || true

if [ -z "$TOOL" ] || [ -z "$MODEL" ]; then
    echo "Usage: $0 <TOOL> <MODEL> [--api-base URL] [--dry-run-prompts] [--ar-limit N]"
    echo ""
    echo "Supported tools:"
    echo "  claude-code   - Claude Code CLI (Anthropic models)"
    echo "  gemini-cli    - Gemini CLI (Google models)"
    echo "  cursor-cli    - Cursor CLI (OpenAI/Anthropic models)"
    echo "  opencode-cli  - OpenCode CLI (GLM/Kimi/MiniMax models)"
    echo ""
    echo "Examples:"
    echo "  $0 claude-code claude-sonnet-4"
    echo "  $0 gemini-cli gemini-3.1-pro --api-base http://localhost:4000"
    echo "  $0 claude-code claude-sonnet-4 --dry-run-prompts --ar-limit 1"
    exit 1
fi

# Parse optional arguments
API_BASE=""
DRY_RUN=""
AR_LIMIT=""
ORIGINAL_REPO=""
while [[ $# -gt 0 ]]; do
    case "$1" in
        --api-base)       API_BASE="$2"; shift 2 ;;
        --dry-run-prompts) DRY_RUN="--dry-run-prompts"; shift ;;
        --ar-limit)       AR_LIMIT="--ar-limit $2"; shift 2 ;;
        --original-repo)  ORIGINAL_REPO="--original-repo $2"; shift 2 ;;
        *)                echo "Unknown arg: $1"; exit 1 ;;
    esac
done

# ─── Preflight ───────────────────────────────────────────────────────────

echo "=== SDD-TEE v5.1 Benchmark Preflight ==="

if [ -n "$API_BASE" ]; then
    echo "[Check] LiteLLM proxy at $API_BASE..."
    if ! curl -s -o /dev/null -w "%{http_code}" "$API_BASE/health" 2>/dev/null | grep -q "200"; then
        echo "[WARN] LiteLLM proxy not responding at $API_BASE"
        echo "       Start: litellm --config configs/litellm_config.yaml --port 4000"
        echo "       Token data will rely on native CLI output (less accurate)."
    else
        echo "[OK] LiteLLM proxy is running."
    fi
fi

if [ ! -d "specs" ]; then
    echo "[ERROR] specs/ directory not found!"
    exit 1
fi
SPEC_COUNT=$(find specs -name "*.md" | wc -l)
echo "[OK] Found $SPEC_COUNT spec files"

echo ""
echo "=== Configuration ==="
echo "Tool:       $TOOL"
echo "Model:      $MODEL"
echo "API Base:   ${API_BASE:-none}"
echo "Dry Run:    ${DRY_RUN:-no}"
echo "AR Limit:   ${AR_LIMIT:-all}"
echo ""

# ─── Execute ─────────────────────────────────────────────────────────────

RUN_ARGS="--tool $TOOL --model $MODEL"
[ -n "$API_BASE" ] && RUN_ARGS="$RUN_ARGS --api-base $API_BASE"
[ -n "$DRY_RUN" ]  && RUN_ARGS="$RUN_ARGS --dry-run-prompts"
[ -n "$AR_LIMIT" ] && RUN_ARGS="$RUN_ARGS $AR_LIMIT"
[ -n "$ORIGINAL_REPO" ] && RUN_ARGS="$RUN_ARGS $ORIGINAL_REPO"

echo "=== Starting Benchmark ==="
python3 scripts/engine.py $RUN_ARGS

LAST_RUN=$(ls -t results/runs/v5.1/*_full.json 2>/dev/null | head -1)
if [ -n "$LAST_RUN" ]; then
    echo ""
    echo "=== Generating Reports ==="
    python3 scripts/report.py --data "$LAST_RUN" 2>/dev/null || true

    RUN_COUNT=$(ls results/runs/v5.1/*_full.json 2>/dev/null | wc -l)
    if [ "$RUN_COUNT" -gt 1 ]; then
        python3 scripts/compare.py \
            --runs results/runs/v5.1/*_full.json \
            --output results/reports/v5.1/compare_report.html 2>/dev/null || true
    fi

    echo ""
    echo "=== Benchmark Complete ==="
    echo "Data:    $LAST_RUN"
    echo "Reports: results/reports/v5.1/"
else
    echo "=== Run finished but no output file found ==="
fi
