#!/usr/bin/env bash
set -euo pipefail

# Stage 0: Clone and analyze the target project
# Usage: ./scripts/00_analyze_project.sh [repo_url] [output_dir]

REPO_URL="${1:-https://github.com/ShijunDeng/agentcube.git}"
OUTPUT_DIR="${2:-./results/project_analysis}"
CLONE_DIR="/tmp/agentcube-benchmark-source"

echo "=== Stage 0: Project Analysis ==="
echo "Repo: $REPO_URL"
echo "Output: $OUTPUT_DIR"

mkdir -p "$OUTPUT_DIR"

if [ -d "$CLONE_DIR" ]; then
    echo "Source already cloned at $CLONE_DIR, pulling latest..."
    git -C "$CLONE_DIR" pull --quiet 2>/dev/null || true
else
    echo "Cloning repository..."
    git clone --quiet "$REPO_URL" "$CLONE_DIR"
fi

echo "Analyzing project structure..."

cat > "$OUTPUT_DIR/analysis.json" << ANALYSIS_EOF
{
  "repo_url": "$REPO_URL",
  "analyzed_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "stats": {
    "total_files": $(find "$CLONE_DIR" -type f -not -path '*/.git/*' | wc -l),
    "go_files": $(find "$CLONE_DIR" -type f -name '*.go' -not -path '*/.git/*' | wc -l),
    "go_loc": $(find "$CLONE_DIR" -type f -name '*.go' -not -path '*/.git/*' -exec cat {} + 2>/dev/null | wc -l),
    "python_files": $(find "$CLONE_DIR" -type f -name '*.py' -not -path '*/.git/*' | wc -l),
    "python_loc": $(find "$CLONE_DIR" -type f -name '*.py' -not -path '*/.git/*' -exec cat {} + 2>/dev/null | wc -l),
    "yaml_files": $(find "$CLONE_DIR" -type f -name '*.yaml' -not -path '*/.git/*' | wc -l),
    "yaml_loc": $(find "$CLONE_DIR" -type f -name '*.yaml' -not -path '*/.git/*' -exec cat {} + 2>/dev/null | wc -l),
    "ts_files": $(find "$CLONE_DIR" -type f \( -name '*.ts' -o -name '*.tsx' \) -not -path '*/.git/*' -not -path '*/node_modules/*' | wc -l),
    "ts_loc": $(find "$CLONE_DIR" -type f \( -name '*.ts' -o -name '*.tsx' \) -not -path '*/.git/*' -not -path '*/node_modules/*' -exec cat {} + 2>/dev/null | wc -l)
  },
  "top_directories": [
$(find "$CLONE_DIR" -type f -not -path '*/.git/*' | sed "s|$CLONE_DIR/||" | cut -d'/' -f1 | sort | uniq -c | sort -rn | head -10 | awk '{printf "    {\"name\": \"%s\", \"file_count\": %s}", $2, $1; if(NR<10) printf ","; printf "\n"}')
  ]
}
ANALYSIS_EOF

echo "File tree..."
find "$CLONE_DIR" -type f -not -path '*/.git/*' | sed "s|$CLONE_DIR/||" | sort > "$OUTPUT_DIR/file_tree.txt"

echo "Language distribution..."
find "$CLONE_DIR" -type f -not -path '*/.git/*' | sed 's/.*\.//' | sort | uniq -c | sort -rn > "$OUTPUT_DIR/language_distribution.txt"

echo "=== Stage 0 Complete ==="
echo "Results written to $OUTPUT_DIR/"
