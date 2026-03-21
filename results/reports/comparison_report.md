# SDD Benchmark Comparison Report

Generated: 2026-03-21 03:46:38 UTC

Target Project: [agentcube](https://github.com/ShijunDeng/agentcube)

## Run Overview

| Tool | Model | Total Duration | Files | LOC | Key Files Rate |
|------|-------|---------------|-------|-----|----------------|
| cursor-cli | claude-4.6-opus | 40m 0s | 362/275 | 36,918/64,625 | 100% |

## Per-Stage Duration

| Tool + Model | Analysis | Spec Gen | SDD Dev | Validation | Total |
|-------------|----------|----------|---------|-----------|-------|
| cursor-cli + claude-4.6-opus | 7s | 194s | 1412s | 451s | 2400s |

## Quality Metrics

| Tool + Model | File Ratio | LOC Ratio | Dir Similarity | File Overlap | Py Syntax | YAML Syntax |
|-------------|-----------|-----------|----------------|-------------|-----------|-------------|
| cursor-cli + claude-4.6-opus | 1.3164 | 0.5713 | 91.94% | 71.27% | 100% | 100% |

## Stage Descriptions

### cursor-cli + claude-4.6-opus

- **project_analysis** (7s): Clone and analyze target project structure — Pure script, no LLM tokens
- **spec_generation** (194s): Reverse-engineer OpenSpec specifications from source code — 3 parallel subagents: Go (types+controllers+router+store), Python (CLI+SDK+examples), Infrastructure (Helm+Docker+CI)
- **sdd_development** (1412s): SDD end-to-end code generation based on specs — Pass 1 (4 subagents): Go core types, Go packages, Python CLI+SDK, K8s manifests. Pass 2 (4 subagents): client-go generated code, Python integrations+tests, docs site+design docs, Go tests+configs.
- **validation** (451s): Validate generated code against original project — Pure script, no LLM tokens

## Efficiency Metrics

**cursor-cli + claude-4.6-opus**
- LOC per minute: 923.0
- Files per minute: 9.1

