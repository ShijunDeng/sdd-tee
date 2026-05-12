# SDD-TEE: SDD Token Efficiency Evaluation
# CodeSpec 7-Stage × OpenSpec OPSX
#
# Usage:
#   make run-v51 TOOL=claude-code MODEL=claude-sonnet-4
#   make run-v51-proxy TOOL=gemini-cli MODEL=gemini-3.1-pro
#   make batch-v51                           # all combos
#   make dry-v51 TOOL=claude-code MODEL=claude-sonnet-4  # test prompts

TOOL     ?= claude-code
MODEL    ?= claude-sonnet-4
SPECS    := specs
RESULTS  := results
RUNS     := $(RESULTS)/runs
REPORTS  := $(RESULTS)/reports
PROXY_PORT ?= 4000
ORIG_REPO ?=

.PHONY: help setup preflight proxy \
        run-v51 run-v51-proxy run-v51-dry \
        batch-v51 batch-v51-proxy \
        report-v51 compare-v51 export-v51 \
        clean-v51 clean-generated clean selftest mock

# --- Environment ---
setup:  ## Install Python dependencies
	pip install -r requirements.txt

preflight:  ## Verify environment
	python3 scripts/preflight.py --tool $(TOOL) --model $(MODEL)

# --- LiteLLM Proxy ---
proxy:  ## Start LiteLLM Proxy
	litellm --config configs/litellm_config.yaml --port $(PROXY_PORT)

# --- v5.1 Benchmark ---
run-v51:  ## Run benchmark: TOOL=xxx MODEL=xxx [ORIG_REPO=path] [AR_LIMIT=N]
	bash scripts/run_benchmark.sh $(TOOL) $(MODEL) $(if $(AR_LIMIT),--ar-limit $(AR_LIMIT),) $(if $(ORIG_REPO),--original-repo $(ORIG_REPO),)

run-v51-proxy:  ## Run benchmark through LiteLLM Proxy
	bash scripts/run_benchmark.sh $(TOOL) $(MODEL) --api-base http://localhost:$(PROXY_PORT) $(if $(ORIG_REPO),--original-repo $(ORIG_REPO),)

run-v51-dry:  ## Dry run (test prompts, no API calls)
	bash scripts/run_benchmark.sh $(TOOL) $(MODEL) --dry-run-prompts

batch-v51:  ## Run all tool×model combinations
	bash scripts/batch_benchmark.sh

batch-v51-proxy:  ## Run all combos through LiteLLM Proxy
	bash scripts/batch_benchmark.sh --api-base http://localhost:$(PROXY_PORT)

# --- Reporting ---
report-v51:  ## Generate report from latest run
	@FULL_JSON=$$(ls -t $(RUNS)/v5.1/*_full.json 2>/dev/null | head -1); \
	if [ -n "$$FULL_JSON" ]; then \
		python3 scripts/report.py --data "$$FULL_JSON" 2>/dev/null || true; \
		echo "Report: $(REPORTS)/v5.1/"; \
	else \
		echo "No v5.1 data found. Run 'make run-v51' first."; \
	fi

compare-v51:  ## Generate cross-run comparison report
	@RUN_COUNT=$$(ls $(RUNS)/v5.1/*_full.json 2>/dev/null | wc -l); \
	if [ "$$RUN_COUNT" -gt 0 ]; then \
		mkdir -p $(REPORTS)/v5.1; \
		python3 scripts/compare.py \
			--runs $(RUNS)/v5.1/*_full.json \
			--output $(REPORTS)/v5.1/compare_report.html; \
		echo "Report: $(REPORTS)/v5.1/compare_report.html"; \
	else \
		echo "No v5.1 runs found."; \
	fi

export-v51:  ## Export v5.1 runs to CSV/JSON/Markdown
	python3 scripts/export.py --format all --output $(REPORTS)/v5.1

# --- Testing ---
mock:  ## Generate mock data report
	python3 scripts/report.py --mock

selftest:  ## Validate latest data against schema
	@FULL_JSON=$$(ls -t $(RUNS)/v5.1/*_full.json 2>/dev/null | head -1); \
	if [ -n "$$FULL_JSON" ]; then \
		python3 scripts/schema.py "$$FULL_JSON"; \
	else \
		echo "No data found. Run 'make mock' or 'make run-v51' first."; \
	fi

# --- Maintenance ---
clean-v51:
	rm -rf workspaces/v5.1/* results/runs/v5.1/* $(REPORTS)/v5.1/*

clean-generated:  ## Remove rebuildable local caches and generated artifacts
	rm -rf workspaces/* docs/build docs/.docusaurus .pytest_cache sdk-python/.pytest_cache sdk-python/.coverage

clean:  ## Remove all generated results
	rm -rf $(RUNS)/v5.1/* $(REPORTS)/v5.1/* workspaces/v5.1/*

help:  ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-22s\033[0m %s\n", $$1, $$2}'
