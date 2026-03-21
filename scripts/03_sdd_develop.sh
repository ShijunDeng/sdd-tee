#!/usr/bin/env bash
set -euo pipefail

# Stage 2: SDD End-to-End Development with token tracking
# Usage: ./scripts/02_sdd_develop.sh <tool> <model> [specs_dir]
#
# Supported tools: claude-code, aider
# Example: ./scripts/02_sdd_develop.sh claude-code claude-sonnet-4-20250514

TOOL="${1:?Usage: $0 <tool> <model> [specs_dir]}"
MODEL="${2:?Usage: $0 <tool> <model> [specs_dir]}"
SPECS_DIR="${3:-./specs}"
RESULTS_DIR="./results/runs"
WORKSPACE_BASE="./workspaces"

TIMESTAMP=$(date -u +%Y%m%dT%H%M%SZ)
RUN_ID="${TOOL}_${MODEL}_${TIMESTAMP}"
WORKSPACE="$WORKSPACE_BASE/$RUN_ID"
RESULT_FILE="$RESULTS_DIR/${RUN_ID}.json"

echo "=== Stage 2: SDD Development ==="
echo "Tool:      $TOOL"
echo "Model:     $MODEL"
echo "Specs:     $SPECS_DIR"
echo "Workspace: $WORKSPACE"
echo "Run ID:    $RUN_ID"

mkdir -p "$WORKSPACE" "$RESULTS_DIR"

# Initialize workspace
cd "$WORKSPACE"
git init --quiet
cp -r "../../$SPECS_DIR" ./specs 2>/dev/null || true

TOTAL_START=$(date +%s)

run_with_claude_code() {
    local stage="$1"
    local prompt="$2"
    local stage_start stage_end

    stage_start=$(date +%s)
    echo "[$stage] Running with Claude Code..."

    # Claude Code supports --output-format json for structured output
    # and CLAUDE_CODE_OTEL_* env vars for OpenTelemetry tracking
    local output_file="../../results/runs/${RUN_ID}_${stage}_raw.json"

    CLAUDE_CODE_DISABLE_NONESSENTIAL=1 \
    claude --model "$MODEL" \
        --output-format json \
        --max-turns 50 \
        --print \
        -p "$prompt" \
        > "$output_file" 2>&1 || true

    stage_end=$(date +%s)
    echo "[$stage] Duration: $((stage_end - stage_start))s"

    # Extract token usage from Claude Code JSON output
    python3 -c "
import json, sys
try:
    with open('$output_file') as f:
        data = json.load(f)
    usage = data.get('usage', {})
    print(json.dumps({
        'stage': '$stage',
        'duration_seconds': $((stage_end - stage_start)),
        'input_tokens': usage.get('input_tokens', 0),
        'output_tokens': usage.get('output_tokens', 0),
        'cache_read_tokens': usage.get('cache_read_input_tokens', 0),
        'cache_write_tokens': usage.get('cache_creation_input_tokens', 0),
        'cost_usd': data.get('cost_usd', 0)
    }))
except Exception as e:
    print(json.dumps({
        'stage': '$stage',
        'duration_seconds': $((stage_end - stage_start)),
        'error': str(e)
    }))
" 2>/dev/null || echo "{\"stage\": \"$stage\", \"duration_seconds\": $((stage_end - stage_start))}"
}

run_with_aider() {
    local stage="$1"
    local prompt="$2"
    local stage_start stage_end

    stage_start=$(date +%s)
    echo "[$stage] Running with Aider..."

    # Aider logs token usage to .aider.chat.history.md
    aider --model "$MODEL" \
        --no-auto-commits \
        --no-git \
        --yes-always \
        --message "$prompt" \
        2>&1 | tee "../../results/runs/${RUN_ID}_${stage}_aider.log" || true

    stage_end=$(date +%s)
    echo "[$stage] Duration: $((stage_end - stage_start))s"

    # Parse Aider's token/cost output
    python3 -c "
import re, json
log_file = '../../results/runs/${RUN_ID}_${stage}_aider.log'
total_cost = 0
total_input = 0
total_output = 0
with open(log_file) as f:
    for line in f:
        cost_match = re.search(r'cost: \\\$([0-9.]+)', line)
        token_match = re.search(r'(\d[\d,]*) prompt tokens.*?(\d[\d,]*) completion tokens', line)
        if cost_match:
            total_cost += float(cost_match.group(1))
        if token_match:
            total_input += int(token_match.group(1).replace(',', ''))
            total_output += int(token_match.group(2).replace(',', ''))
print(json.dumps({
    'stage': '$stage',
    'duration_seconds': $((stage_end - stage_start)),
    'input_tokens': total_input,
    'output_tokens': total_output,
    'cost_usd': round(total_cost, 6)
}))
" 2>/dev/null || echo "{\"stage\": \"$stage\", \"duration_seconds\": $((stage_end - stage_start))}"
}

# Select runner based on tool
case "$TOOL" in
    claude-code) RUNNER=run_with_claude_code ;;
    aider)       RUNNER=run_with_aider ;;
    *)           echo "Unsupported tool: $TOOL"; exit 1 ;;
esac

# ---- OpenSpec SDD Workflow ----

# Phase 1: Planning (opsx:ff equivalent)
PLANNING_PROMPT="You are working on replicating the AgentCube project — a Kubernetes-native AI Agent workload management platform.

Read the specifications in the ./specs directory carefully. Based on these specs, create a detailed implementation plan that covers:
1. Project structure and directory layout
2. All Go packages (CRD types, controllers, router, workload manager, schedulers)
3. Python CLI and SDK
4. Kubernetes manifests and Helm charts
5. Build system (Makefile, Dockerfile)

Output the plan as PLAN.md in the workspace root. Be thorough — list every file that needs to be created."

echo ""
echo ">>> Phase 1: Planning"
PLAN_RESULT=$($RUNNER "planning" "$PLANNING_PROMPT")
echo "$PLAN_RESULT" > "../../results/runs/${RUN_ID}_planning.json"

# Phase 2: Implementation (opsx:apply equivalent)
IMPL_PROMPT="You are implementing the AgentCube project based on the specifications in ./specs and the plan in PLAN.md.

Implement the full project. Create all necessary files:
1. Go source code: CRD types, controllers, router, workload manager, scheduler, client-go
2. Python CLI (cmd/cli) with Click-based commands for runtime management
3. Python SDK (sdk-python) for agent runtime development
4. Kubernetes CRD YAML definitions
5. Helm charts (manifests/charts)
6. Dockerfiles, Makefile, go.mod, pyproject.toml
7. Example agents

Follow the specs precisely. Generate production-quality code with proper error handling."

echo ""
echo ">>> Phase 2: Implementation"
IMPL_RESULT=$($RUNNER "implementation" "$IMPL_PROMPT")
echo "$IMPL_RESULT" > "../../results/runs/${RUN_ID}_implementation.json"

# Phase 3: Refinement
REFINE_PROMPT="Review all generated code in this workspace. Fix any issues:
1. Ensure all imports are correct
2. Ensure Go code compiles (fix type errors, missing packages)
3. Ensure Python code passes basic syntax check
4. Ensure Kubernetes YAML is valid
5. Ensure consistency across modules

List any remaining issues."

echo ""
echo ">>> Phase 3: Refinement"
REFINE_RESULT=$($RUNNER "refinement" "$REFINE_PROMPT")
echo "$REFINE_RESULT" > "../../results/runs/${RUN_ID}_refinement.json"

cd - > /dev/null
TOTAL_END=$(date +%s)
TOTAL_DURATION=$((TOTAL_END - TOTAL_START))

# Aggregate results
python3 << PYEOF
import json, glob, os

run_id = "$RUN_ID"
results_dir = "$RESULTS_DIR"
workspace = "$WORKSPACE"

stages = {}
for stage_file in sorted(glob.glob(f"{results_dir}/{run_id}_*.json")):
    try:
        with open(stage_file) as f:
            data = json.load(f)
            stage_name = data.get("stage", os.path.basename(stage_file))
            stages[stage_name] = data
    except (json.JSONDecodeError, KeyError):
        pass

total_input = sum(s.get("input_tokens", 0) for s in stages.values())
total_output = sum(s.get("output_tokens", 0) for s in stages.values())
total_cost = sum(s.get("cost_usd", 0) for s in stages.values())

# Count generated files
gen_files = 0
gen_loc = 0
for root, dirs, files in os.walk(workspace):
    dirs[:] = [d for d in dirs if d not in ('.git', 'specs', 'node_modules')]
    for f in files:
        fpath = os.path.join(root, f)
        gen_files += 1
        try:
            with open(fpath) as fh:
                gen_loc += sum(1 for _ in fh)
        except:
            pass

result = {
    "run_id": run_id,
    "timestamp": "$TIMESTAMP",
    "project": "agentcube",
    "tool": "$TOOL",
    "model": "$MODEL",
    "stages": stages,
    "totals": {
        "duration_seconds": $TOTAL_DURATION,
        "input_tokens": total_input,
        "output_tokens": total_output,
        "cost_usd": round(total_cost, 6)
    },
    "quality": {
        "files_generated": gen_files,
        "loc_generated": gen_loc
    }
}

output_path = f"{results_dir}/{run_id}.json"
with open(output_path, "w") as f:
    json.dump(result, f, indent=2)
print(f"Run result: {output_path}")
PYEOF

echo ""
echo "=== Stage 2 Complete ==="
echo "Tool: $TOOL | Model: $MODEL | Duration: ${TOTAL_DURATION}s"
echo "Result: $RESULT_FILE"
