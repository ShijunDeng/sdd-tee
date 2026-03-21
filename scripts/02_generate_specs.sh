#!/usr/bin/env bash
set -euo pipefail

# Stage 1: Reverse-engineer OpenSpec specifications from existing codebase
# Usage: ./scripts/01_generate_specs.sh [source_dir] [specs_output_dir]
#
# Prerequisites:
#   npm install -g @fission-ai/openspec@latest
#   pip install spec-gen  (or npm install -g spec-gen)
#
# This script:
# 1. Runs spec-gen static analysis (no tokens)
# 2. Runs spec-gen LLM-powered generation (tracks tokens)
# 3. Fetches DeepWiki documentation as supplementary reference

SOURCE_DIR="${1:-/tmp/agentcube-benchmark-source}"
SPECS_DIR="${2:-./specs}"
RESULTS_DIR="${3:-./results/runs}"
DEEPWIKI_URL="https://deepwiki.com/ShijunDeng/agentcube"

TIMESTAMP=$(date -u +%Y%m%dT%H%M%SZ)
STAGE_RESULT="$RESULTS_DIR/stage1_spec_gen_${TIMESTAMP}.json"

echo "=== Stage 1: Specification Reverse-Engineering ==="
echo "Source: $SOURCE_DIR"
echo "Output: $SPECS_DIR"

mkdir -p "$SPECS_DIR" "$RESULTS_DIR"

START_TIME=$(date +%s)

# Step 1: Static analysis with spec-gen (no token cost)
echo "[1/3] Running static analysis..."
if command -v spec-gen &>/dev/null; then
    spec-gen analyze "$SOURCE_DIR" --output "$SPECS_DIR/analysis" 2>&1 | tee "$SPECS_DIR/analysis.log"
else
    echo "WARN: spec-gen not installed. Skipping static analysis."
    echo "Install with: pip install spec-gen OR npm install -g spec-gen"
fi

# Step 2: LLM-powered spec generation (token cost tracked)
echo "[2/3] Generating OpenSpec specifications..."
SPEC_GEN_START=$(date +%s)

if command -v spec-gen &>/dev/null; then
    spec-gen generate "$SOURCE_DIR" \
        --output "$SPECS_DIR" \
        --format openspec \
        2>&1 | tee "$SPECS_DIR/generation.log"
else
    echo "WARN: spec-gen not installed. Creating spec scaffolding manually."
    mkdir -p "$SPECS_DIR"/{capabilities,changes}

    # Create minimal OpenSpec structure for manual completion
    cat > "$SPECS_DIR/project.yaml" << 'EOF'
name: agentcube
description: >
  AI Agent workload management platform on Kubernetes.
  Extends Volcano capabilities for scheduling, lifecycle management,
  and resource optimization of AI Agent workloads.
version: 0.1.0
languages:
  - go
  - python
  - typescript
frameworks:
  - kubernetes
  - helm
  - cobra
modules:
  - name: router
    path: cmd/router
    description: HTTP/gRPC router for agent runtime invocation
  - name: workload-manager
    path: cmd/workload-manager
    description: Kubernetes controller for agent workload lifecycle
  - name: cli
    path: cmd/cli
    description: Python CLI for agent runtime management
  - name: sdk-python
    path: sdk-python
    description: Python SDK for agent runtime development
  - name: client-go
    path: client-go
    description: Generated Go client for Kubernetes CRDs
  - name: pkg
    path: pkg
    description: Core Go packages (controllers, schedulers, APIs)
  - name: manifests
    path: manifests
    description: Helm charts and Kubernetes manifests
EOF

    echo "Scaffolding created. Run spec-gen or manually populate specs."
fi

SPEC_GEN_END=$(date +%s)
SPEC_GEN_DURATION=$((SPEC_GEN_END - SPEC_GEN_START))

# Step 3: Fetch DeepWiki documentation
echo "[3/3] Fetching DeepWiki documentation..."
DEEPWIKI_DIR="$SPECS_DIR/deepwiki_reference"
mkdir -p "$DEEPWIKI_DIR"

if command -v curl &>/dev/null; then
    # Use DeepWiki MCP API if available
    curl -s "https://mcp.deepwiki.com/sse" \
        -H "Content-Type: application/json" \
        -d "{\"tool\":\"deepwiki_fetch\",\"arguments\":{\"url\":\"$DEEPWIKI_URL\"}}" \
        > "$DEEPWIKI_DIR/deepwiki_raw.json" 2>/dev/null || echo "DeepWiki fetch failed (may need manual access)"
fi

END_TIME=$(date +%s)
TOTAL_DURATION=$((END_TIME - START_TIME))

# Write stage result
cat > "$STAGE_RESULT" << EOF
{
  "stage": "spec_generation",
  "timestamp": "$TIMESTAMP",
  "duration_seconds": $TOTAL_DURATION,
  "spec_gen_duration_seconds": $SPEC_GEN_DURATION,
  "source_dir": "$SOURCE_DIR",
  "specs_dir": "$SPECS_DIR",
  "notes": "Token usage tracked via LiteLLM proxy or tool native tracking. Check proxy logs for detailed breakdown."
}
EOF

echo "=== Stage 1 Complete ==="
echo "Duration: ${TOTAL_DURATION}s"
echo "Specs: $SPECS_DIR"
echo "Result: $STAGE_RESULT"
