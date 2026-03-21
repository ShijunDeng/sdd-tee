# SDD-TEE: SDD Token Efficiency Evaluation
# CodeSpec 7-Stage × OpenSpec OPSX
#
# Reentrant design: clone → make setup → make preflight → make run → make collect → make report → make selftest
#
# Multi-tool evaluation:
#   make run TOOL=claude-code MODEL=claude-sonnet-4-20250514
#   make run TOOL=gemini-cli  MODEL=gemini-2.5-pro
#   make run TOOL=opencode-cli MODEL=opencode/big-pickle
#   make run TOOL=cursor-cli  MODEL=claude-4.6-opus-high-thinking

TOOL     ?= cursor-cli
MODEL    ?= claude-4.6-opus-high-thinking
SPECS    := specs
RESULTS  := results
RUNS     := $(RESULTS)/runs
REPORTS  := $(RESULTS)/reports
PROXY_PORT ?= 4000

.PHONY: all setup preflight run collect report mock compare proxy proxy-run selftest clean help

all: setup preflight run collect report selftest  ## Full pipeline (environment → evaluate → report → validate)

# --- Environment Setup (run once per new environment) ---
setup:  ## Install Python dependencies
	pip install -r requirements.txt
	@echo "Setup complete. Run 'make preflight' to verify environment."

preflight:  ## Verify environment can run evaluations
	python3 scripts/preflight.py --tool $(TOOL) --model $(MODEL)

# --- Prerequisites (one-time) ---
prerequisites: $(RESULTS)/project_analysis/analysis.json $(SPECS)/project.md

$(RESULTS)/project_analysis/analysis.json:
	bash scripts/01_analyze_project.sh

$(SPECS)/project.md:
	bash scripts/02_generate_specs.sh

# --- Evaluation (CLI tool runners) ---
run:  ## Run SDD evaluation (TOOL=cursor-cli|claude-code|gemini-cli|opencode-cli MODEL=xxx)
	@echo "Running evaluation: TOOL=$(TOOL) MODEL=$(MODEL)"
	bash scripts/03_sdd_develop.sh $(TOOL) $(MODEL) $(SPECS)
	@echo "Evaluation complete. Run 'make collect' to process data."

# --- Evaluation (LiteLLM Proxy — precise per-request token tracking) ---
proxy:  ## Start LiteLLM Proxy for precise token interception
	litellm --config litellm_config.yaml --port $(PROXY_PORT)

proxy-run:  ## Run evaluation through LiteLLM Proxy with per-request token tracking
	python3 scripts/10_litellm_runner.py \
		--model $(MODEL) \
		--api-base http://localhost:$(PROXY_PORT) \
		--specs-dir $(SPECS)

# --- Data Collection ---
collect:  ## Collect run data with precise token counts from workspace
	@RUN_JSON=$$(ls -t $(RUNS)/*.json 2>/dev/null | grep -v _full | grep -v _validation | grep -v _logs | head -1); \
	WS_DIR=$$(ls -dt workspaces/* 2>/dev/null | head -1); \
	if [ -n "$$RUN_JSON" ] && [ -n "$$WS_DIR" ]; then \
		echo "Collecting: $$RUN_JSON + $$WS_DIR"; \
		python3 scripts/09_collect_run_data.py "$$RUN_JSON" "$$WS_DIR" --specs-dir $(SPECS); \
	else \
		echo "No run data found. Run 'make run' first."; \
	fi

# --- Reporting ---
report:  ## Generate 10-section 5-dimension HTML report (with schema validation)
	@FULL_JSON=$$(ls -t $(RUNS)/*_full.json 2>/dev/null | head -1); \
	if [ -n "$$FULL_JSON" ]; then \
		RUN_ID=$$(python3 -c "import json; d=json.load(open('$$FULL_JSON')); print(d['meta']['run_id'])"); \
		python3 scripts/07_sdd_tee_report.py \
			--data "$$FULL_JSON" \
			--output "$(REPORTS)/$${RUN_ID}_report.html" \
			--data-output "$$FULL_JSON"; \
		echo "Report generated: $(REPORTS)/$${RUN_ID}_report.html"; \
	else \
		echo "No full data JSON found. Run 'make collect' first."; \
	fi

mock:  ## Generate mock data report (preview & schema test)
	python3 scripts/07_sdd_tee_report.py --mock

# --- Cross-run Comparison ---
compare:  ## Generate cross-run comparison report from all *_full.json files
	python3 scripts/11_compare_runs.py --output $(REPORTS)/compare_report.html

# --- Code Quality Validation ---
validate:  ## Run code quality checks on latest workspace
	@WS_DIR=$$(ls -dt workspaces/* 2>/dev/null | head -1); \
	if [ -n "$$WS_DIR" ]; then \
		python3 scripts/04_validate.py "$$WS_DIR"; \
	else \
		echo "No workspace found."; \
	fi

# --- Self-test (validates report against metrics design doc) ---
selftest:  ## Validate data + HTML against SDD-TEE schema contract
	@echo "=== SDD-TEE Self-Test ==="
	@FULL_JSON=$$(ls -t $(RUNS)/*_full.json 2>/dev/null | head -1); \
	REPORT_HTML=$$(ls -t $(REPORTS)/*_report.html 2>/dev/null | head -1); \
	if [ -n "$$FULL_JSON" ] && [ -n "$$REPORT_HTML" ]; then \
		python3 scripts/schema.py "$$FULL_JSON" "$$REPORT_HTML"; \
	elif [ -n "$$FULL_JSON" ]; then \
		python3 scripts/schema.py "$$FULL_JSON"; \
	else \
		echo "No data found. Run 'make mock' to test with mock data, then:"; \
		echo "  python3 scripts/schema.py results/reports/sdd_tee_report.json results/reports/sdd_tee_report.html"; \
	fi

project-report:  ## Generate project analysis HTML report
	python3 scripts/06_project_report.py

# --- Convenience: evaluate all 4 tools sequentially ---
eval-all:  ## Run evaluation for all 4 CLI tools (sequential)
	@echo "=== Evaluating all 4 CLI tools ==="
	$(MAKE) run TOOL=cursor-cli  MODEL=$(MODEL) && $(MAKE) collect && $(MAKE) report || echo "cursor-cli failed"
	$(MAKE) run TOOL=claude-code MODEL=claude-sonnet-4-20250514 && $(MAKE) collect && $(MAKE) report || echo "claude-code failed"
	$(MAKE) run TOOL=gemini-cli  MODEL=gemini-2.5-pro && $(MAKE) collect && $(MAKE) report || echo "gemini-cli failed"
	$(MAKE) run TOOL=opencode-cli MODEL=opencode/big-pickle && $(MAKE) collect && $(MAKE) report || echo "opencode-cli failed"
	$(MAKE) compare
	@echo "=== All evaluations complete. See results/reports/compare_report.html ==="

# --- Maintenance ---
clean:  ## Remove generated results (keeps specs)
	rm -rf $(RUNS)/*.json $(REPORTS)/*.html $(REPORTS)/*.json workspaces/

help:  ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'
