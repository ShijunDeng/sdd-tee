# SDD Benchmark Comparison Report

Generated: 2026-03-21 03:34:07 UTC

Target Project: [agentcube](https://github.com/ShijunDeng/agentcube)

## Run Overview

| Tool | Model | Total Duration | Files | LOC | Key Files Rate |
|------|-------|---------------|-------|-----|----------------|
| cursor-cli | claude-4.6-opus | 26m 19s | 110/275 | 8,199/64,625 | 100% |

## Per-Stage Duration

| Tool + Model | Analysis | Spec Gen | SDD Dev | Validation | Total |
|-------------|----------|----------|---------|-----------|-------|
| cursor-cli + claude-4.6-opus | 7s | 194s | 913s | 451s | 1579s |

## Quality Metrics

| Tool + Model | File Ratio | LOC Ratio | Dir Similarity | File Overlap | Py Syntax | YAML Syntax |
|-------------|-----------|-----------|----------------|-------------|-----------|-------------|
| cursor-cli + claude-4.6-opus | 0.4 | 0.1269 | 56.45% | 32.73% | 100% | 74% |

## Stage Descriptions

### cursor-cli + claude-4.6-opus

- **project_analysis** (7s): Clone and analyze target project structure — Pure script, no LLM tokens
- **spec_generation** (194s): Reverse-engineer OpenSpec specifications from source code (3 parallel subagents)
- **sdd_development** (913s): SDD end-to-end code generation (4 parallel subagents: Go types, Go packages, Python, Infrastructure)
- **validation** (451s): Validate generated code against original project — Pure script, no LLM tokens

## Efficiency Metrics

**cursor-cli + claude-4.6-opus**
- LOC per minute: 311.6
- Files per minute: 4.2

