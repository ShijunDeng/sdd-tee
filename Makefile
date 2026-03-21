# SDD-TEE: SDD Token Efficiency Evaluation
# CodeSpec 7-Stage × OpenSpec OPSX

TOOL     ?= claude-code
MODEL    ?= claude-sonnet-4-20250514
SPECS    := specs
RESULTS  := results
RUNS     := $(RESULTS)/runs
REPORTS  := $(RESULTS)/reports

.PHONY: all prerequisites run report mock clean help

all: prerequisites run report  ## Full pipeline: prerequisites → evaluate → report

# --- Prerequisites (one-time) ---
prerequisites: $(RESULTS)/project_analysis/analysis.json $(SPECS)/01_go_specification.md

$(RESULTS)/project_analysis/analysis.json:
	bash scripts/01_analyze_project.sh

$(SPECS)/01_go_specification.md:
	bash scripts/02_generate_specs.sh

# --- Evaluation ---
run:  ## Run SDD evaluation (TOOL=xxx MODEL=xxx)
	bash scripts/03_sdd_develop.sh $(TOOL) $(MODEL)
	python3 scripts/04_validate.py
	python3 scripts/05_aggregate.py

# --- Reporting ---
report:  ## Generate HTML reports
	python3 scripts/07_sdd_tee_report.py --data $(RUNS)/*.json --output $(REPORTS)/sdd_tee_report.html

mock:  ## Generate mock data report (preview)
	python3 scripts/07_sdd_tee_report.py --mock

project-report:  ## Generate project analysis HTML report
	python3 scripts/06_project_report.py

# --- Maintenance ---
clean:  ## Remove generated results (keeps specs)
	rm -rf $(RUNS)/*.json $(REPORTS)/*.html $(REPORTS)/*.json workspaces/

help:  ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'
