# SDD-TEE: SDD Token Efficiency Evaluation
# ==========================================
# Usage:
#   make all                          # Run full pipeline (analyze → specs → develop → validate → report)
#   make run TOOL=claude-code MODEL=claude-sonnet-4-20250514
#   make run TOOL=aider MODEL=claude-sonnet-4-20250514
#   make report                       # Regenerate comparison reports
#   make matrix                       # Run all tool×model combinations

SHELL := /bin/bash

TOOL ?= claude-code
MODEL ?= claude-sonnet-4-20250514
SPECS_DIR ?= ./specs
SOURCE_DIR ?= /tmp/agentcube-benchmark-source

.PHONY: all analyze specs develop validate report clean matrix setup

# ---- Setup ----
setup:
	@echo "=== Installing dependencies ==="
	command -v node >/dev/null || (echo "ERROR: Node.js 20+ required"; exit 1)
	command -v python3 >/dev/null || (echo "ERROR: Python 3.10+ required"; exit 1)
	npm install -g @fission-ai/openspec@latest 2>/dev/null || true
	pip install matplotlib 2>/dev/null || true
	@echo "Setup complete."

# ---- Full Pipeline ----
all: analyze specs develop validate report

# ---- Stage 0: Analyze ----
analyze:
	@bash scripts/00_analyze_project.sh "$(SOURCE_DIR)" ./results/project_analysis

# ---- Stage 1: Generate Specs ----
specs:
	@bash scripts/01_generate_specs.sh "$(SOURCE_DIR)" "$(SPECS_DIR)"

# ---- Stage 2: SDD Development ----
develop:
	@bash scripts/02_sdd_develop.sh "$(TOOL)" "$(MODEL)" "$(SPECS_DIR)"

# ---- Stage 3: Validate ----
validate:
	@echo "Validating latest workspace for $(TOOL) + $(MODEL)..."
	@LATEST=$$(ls -td workspaces/$(TOOL)_$(MODEL)_* 2>/dev/null | head -1); \
	if [ -n "$$LATEST" ]; then \
		bash scripts/03_validate.sh "$$LATEST" "$(SOURCE_DIR)"; \
	else \
		echo "No workspace found for $(TOOL)_$(MODEL)_*"; \
	fi

# ---- Stage 4: Report ----
report:
	@python3 scripts/04_report.py ./results

# ---- Run a single tool×model combination ----
run: develop validate report

# ---- Run all configured combinations ----
TOOLS := claude-code aider
MODELS := claude-sonnet-4-20250514

matrix:
	@for tool in $(TOOLS); do \
		for model in $(MODELS); do \
			echo ""; \
			echo "========================================"; \
			echo "Running: $$tool + $$model"; \
			echo "========================================"; \
			$(MAKE) run TOOL=$$tool MODEL=$$model || true; \
		done; \
	done
	@$(MAKE) report

# ---- Utilities ----
clean:
	rm -rf workspaces/* results/runs/* results/reports/*

clean-all: clean
	rm -rf specs/* results/*
