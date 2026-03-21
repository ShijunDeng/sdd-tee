# SDD-TEE: SDD Token Efficiency Evaluation
# CodeSpec 7-Stage × OpenSpec OPSX
#
# Reentrant design: clone → make setup → make preflight → make run → make report → make selftest

TOOL     ?= cursor-cli
MODEL    ?= claude-4.6-opus-high-thinking
SPECS    := specs
RESULTS  := results
RUNS     := $(RESULTS)/runs
REPORTS  := $(RESULTS)/reports
PROXY_PORT ?= 4000

.PHONY: all setup preflight run collect report mock proxy proxy-run selftest clean help

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

# --- Evaluation (manual / Cursor CLI) ---
run:  ## Run SDD evaluation via subagent (TOOL=xxx MODEL=xxx)
	bash scripts/03_sdd_develop.sh $(TOOL) $(MODEL)
	python3 scripts/04_validate.py

# --- Evaluation (LiteLLM Proxy — precise token tracking) ---
proxy:  ## Start LiteLLM Proxy (requires ANTHROPIC_API_KEY)
	litellm --config litellm_config.yaml --port $(PROXY_PORT)

proxy-run:  ## Run evaluation through LiteLLM Proxy with per-request token tracking
	python3 scripts/10_litellm_runner.py \
		--model $(MODEL) \
		--api-base http://localhost:$(PROXY_PORT) \
		--specs-dir $(SPECS)

# --- Data Collection ---
collect:  ## Collect run data with precise token counts from workspace
	@RUN_JSON=$$(ls -t $(RUNS)/*_$(MODEL)_*.json 2>/dev/null | grep -v _full | grep -v _validation | head -1); \
	WS_DIR=$$(ls -dt workspaces/*_$(MODEL)_* 2>/dev/null | head -1); \
	if [ -n "$$RUN_JSON" ] && [ -n "$$WS_DIR" ]; then \
		python3 scripts/09_collect_run_data.py "$$RUN_JSON" "$$WS_DIR" --specs-dir $(SPECS); \
	else \
		echo "No run data found for MODEL=$(MODEL)"; \
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
	else \
		echo "No full data JSON found. Run 'make collect' first."; \
	fi

mock:  ## Generate mock data report (preview & schema test)
	python3 scripts/07_sdd_tee_report.py --mock

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

# --- Maintenance ---
clean:  ## Remove generated results (keeps specs)
	rm -rf $(RUNS)/*.json $(REPORTS)/*.html $(REPORTS)/*.json workspaces/

help:  ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'
