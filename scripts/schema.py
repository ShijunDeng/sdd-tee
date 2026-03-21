#!/usr/bin/env python3
"""
SDD-TEE Data Schema & Validation Contract

This module is the SINGLE SOURCE OF TRUTH that bridges:
  - docs/SDD开发Token消耗度量指标体系设计方案.md  (what we MUST track)
  - config.yaml                                    (how we configure)
  - 07_sdd_tee_report.py                           (how we render)
  - 09_collect_run_data.py / 10_litellm_runner.py  (how we collect)

Every field listed here is MANDATORY. If a report is generated without
any of these fields, validate_report_data() will raise with a precise
error pointing to the missing metric.

Usage:
  from schema import validate_report_data, REQUIRED_METRICS
  validate_report_data(data)  # raises SchemaError on violation
"""

import sys

__all__ = [
    "STAGES", "STAGE_FIELDS", "METRIC_IDS",
    "REQUIRED_GRAND_TOTALS", "REQUIRED_AR_FIELDS",
    "REQUIRED_REPORT_SECTIONS", "WARNING_RULES",
    "validate_report_data", "SchemaError",
]


# ============================================================================
# §1  Stage definitions (from 指标体系 §2.1)
# ============================================================================

STAGES = ["ST-0", "ST-1", "ST-2", "ST-3", "ST-4", "ST-5", "ST-6", "ST-7"]

STAGE_FIELDS = [
    "input_tokens",
    "output_tokens",
    "cache_read_tokens",
    "cache_write_tokens",
    "spec_context_tokens",
    "human_input_tokens",
    "iterations",
    "duration_seconds",
    "api_calls",
]

# ============================================================================
# §2  Metric IDs (from 指标体系 §2.2 - §2.5)
# ============================================================================

METRIC_IDS = {
    # Role dimension (§2.2)
    "RT-AI":    "AI Token 总量 = 总Token - RT-HUMAN - RT-SPEC",
    "RT-HUMAN": "人工输入 Token = ∑(human_input_tokens)",
    "RT-SPEC":  "预制规范 Token = ∑(spec_context_tokens)",
    "RT-RATIO": "人机 Token 比 = RT-HUMAN / RT-AI",
    "RT-ITER":  "平均迭代次数/AR = ∑(iterations) / AR数",

    # Efficiency dimension (§2.3)
    "ET-LOC":      "Token/代码行 = ST-5_total / LOC",
    "ET-FILE":     "Token/文件 = ST-5_total / 文件数",
    "ET-TASK":     "Token/任务 = ST-5_total / Task数",
    "ET-AR":       "Token/AR = ∑(ST-0~7) / AR数",
    "ET-TIME":     "Token/小时 = 总Token / 耗时(h)",
    "ET-COST-LOC": "成本/千行代码 = USD / (LOC/1000)",

    # Quality dimension (§2.4)
    "QT-COV":     "Token/覆盖率 = ST-5 / 覆盖率%",
    "QT-CONSIST": "Token/一致性 = ST-6 / 一致性%",
    "QT-AVAIL":   "Token/可用率 = ST-5 / 可用率%",
    "QT-BUG":     "Token/Bug = ST-5 / Bug数 (反向)",

    # Distribution dimension (§2.5)
    "PT-DESIGN": "设计占比 = (ST-1+ST-2+ST-3) / 总Token; 预期 15-30%",
    "PT-PLAN":   "规划占比 = (ST-0+ST-4) / 总Token; 预期 5-15%",
    "PT-DEV":    "开发占比 = ST-5 / 总Token; 预期 45-65%",
    "PT-VERIFY": "验证归档占比 = (ST-6+ST-7) / 总Token; 预期 8-18%",
    "PT-PEAK":   "峰值阶段 = argmax(ST-0~ST-7)",
    "PT-CACHE":  "Cache命中率 = cache_read / input_tokens; 预期 >70%",
}

# ============================================================================
# §3  Grand totals (required in data["grand_totals"])
# ============================================================================

REQUIRED_GRAND_TOTALS = [
    "ar_count",
    "input_tokens", "output_tokens",
    "cache_read_tokens", "cache_write_tokens",
    "total_tokens",
    "human_input_tokens", "spec_context_tokens",
    "total_duration_seconds",
    "total_cost_usd", "total_cost_cny",
    "total_loc", "total_files", "total_tasks",
    "total_iterations", "total_api_calls",
]

# ============================================================================
# §4  Per-AR required fields
# ============================================================================

REQUIRED_AR_FIELDS = [
    "ar_id", "ar_name", "module", "lang", "type", "size",
    "stages", "totals", "output", "quality", "metrics",
]

REQUIRED_AR_TOTALS = [
    "input_tokens", "output_tokens",
    "cache_read_tokens", "cache_write_tokens",
    "total_tokens", "human_input_tokens", "spec_context_tokens",
    "iterations", "duration_seconds", "api_calls", "cost_usd",
]

REQUIRED_AR_OUTPUT = ["actual_loc", "actual_files", "tasks_count"]

REQUIRED_AR_QUALITY = [
    "consistency_score", "code_usability", "test_coverage", "bugs_found",
]

REQUIRED_AR_METRICS = [
    "ET_LOC", "ET_FILE", "ET_TASK", "ET_AR", "ET_TIME", "ET_COST_LOC",
    "RT_RATIO", "RT_ITER",
    "QT_COV", "QT_CONSIST", "QT_AVAIL", "QT_BUG",
    "PT_DESIGN", "PT_PLAN", "PT_DEV", "PT_VERIFY",
]

# ============================================================================
# §5  Report HTML section IDs (must appear in rendered HTML)
# ============================================================================

REQUIRED_REPORT_SECTIONS = [
    ("overview",     "1. 评测概览"),
    ("stage",        "2. 阶段维度"),
    ("role",         "3. 角色维度"),
    ("efficiency",   "4. 效率维度"),
    ("quality",      "5. 质量维度"),
    ("distribution", "6. 阶段间 Token 分布"),
    ("baselines",    "7. 基线数据"),
    ("ar-detail",    "8. AR 需求明细"),
    ("warnings",     "9. 预警分析"),
    ("reference",    "10. 引用与说明"),
]

# ============================================================================
# §6  Warning rules (from 指标体系 §5)
# ============================================================================

WARNING_RULES = [
    {"id": "W-STAGE-BUDGET",  "condition": "单阶段 Token > 基线 150%",      "level": "yellow"},
    {"id": "W-TOTAL-BUDGET",  "condition": "总 Token > 预算 120%",          "level": "red"},
    {"id": "W-ET-LOC",        "condition": "Token/LOC > 基线 200%",         "level": "anomaly"},
    {"id": "W-USABILITY",     "condition": "代码可用率 < 75%",              "level": "quality"},
    {"id": "W-DEV-SKEW",      "condition": "开发占比 (PT-DEV) > 80%",      "level": "structure"},
    {"id": "W-CACHE-LOW",     "condition": "Cache 命中率 (PT-CACHE) < 50%", "level": "efficiency"},
]


# ============================================================================
# §7  Validation logic
# ============================================================================

class SchemaError(Exception):
    def __init__(self, errors):
        self.errors = errors
        msg = f"Schema validation failed with {len(errors)} error(s):\n"
        for e in errors:
            msg += f"  - {e}\n"
        super().__init__(msg)


def validate_report_data(data):
    """Validate that `data` dict contains ALL required fields.

    Raises SchemaError with a list of every missing field / violation.
    Returns list of warnings (non-fatal issues).
    """
    errors = []
    warnings = []

    # -- meta --
    if "meta" not in data:
        errors.append("Missing top-level 'meta'")
    else:
        for k in ("tool", "model", "generated_at", "methodology"):
            if k not in data["meta"]:
                errors.append(f"meta.{k} missing")

    # -- grand_totals --
    gt = data.get("grand_totals", {})
    if not gt:
        errors.append("Missing 'grand_totals'")
    else:
        for k in REQUIRED_GRAND_TOTALS:
            if k not in gt:
                errors.append(f"grand_totals.{k} missing")

    # -- stage_aggregates --
    sa = data.get("stage_aggregates", {})
    if not sa:
        errors.append("Missing 'stage_aggregates'")
    else:
        for sid in STAGES:
            if sid not in sa:
                errors.append(f"stage_aggregates.{sid} missing")

    # -- baselines --
    if "baselines" not in data:
        errors.append("Missing 'baselines'")

    # -- ar_results --
    ars = data.get("ar_results", [])
    if not ars:
        errors.append("'ar_results' is empty")
    else:
        for i, ar in enumerate(ars):
            prefix = f"ar_results[{i}] ({ar.get('ar_id','?')})"

            for k in REQUIRED_AR_FIELDS:
                if k not in ar:
                    errors.append(f"{prefix}.{k} missing")

            # stages
            stages = ar.get("stages", {})
            for sid in STAGES:
                if sid not in stages:
                    errors.append(f"{prefix}.stages.{sid} missing")
                else:
                    for fld in STAGE_FIELDS:
                        if fld not in stages[sid]:
                            errors.append(f"{prefix}.stages.{sid}.{fld} missing")

            # totals
            for k in REQUIRED_AR_TOTALS:
                if k not in ar.get("totals", {}):
                    errors.append(f"{prefix}.totals.{k} missing")

            # output
            for k in REQUIRED_AR_OUTPUT:
                if k not in ar.get("output", {}):
                    errors.append(f"{prefix}.output.{k} missing")

            # quality
            for k in REQUIRED_AR_QUALITY:
                if k not in ar.get("quality", {}):
                    errors.append(f"{prefix}.quality.{k} missing")

            # metrics
            for k in REQUIRED_AR_METRICS:
                if k not in ar.get("metrics", {}):
                    errors.append(f"{prefix}.metrics.{k} missing")

            # check only first 3 ARs in detail to limit output
            if i >= 2 and errors:
                errors.append(f"... (stopped checking after {i+1} ARs, fix above first)")
                break

    if errors:
        raise SchemaError(errors)

    # Non-fatal warnings
    if gt:
        cache_rate = gt.get("cache_read_tokens", 0) / max(gt.get("input_tokens", 1), 1)
        if cache_rate < 0.50:
            warnings.append(f"W-CACHE-LOW: Cache rate {cache_rate:.0%} < 50%")
        dev_rate = sa.get("ST-5", {}).get("total_tokens", 0) / max(gt.get("total_tokens", 1), 1)
        if dev_rate > 0.80:
            warnings.append(f"W-DEV-SKEW: Dev ratio {dev_rate:.0%} > 80%")

    return warnings


def validate_html_report(html_content):
    """Validate that rendered HTML contains all required sections."""
    errors = []
    for section_id, section_title in REQUIRED_REPORT_SECTIONS:
        if f'id="{section_id}"' not in html_content:
            errors.append(f"Missing HTML section id='{section_id}' ({section_title})")

    required_keywords = [
        "Token 类型分布", "Cache 命中率", "预制规范",
        "ET-LOC", "ET-FILE", "ET-TASK", "ET-AR", "ET-TIME",
        "RT-AI", "RT-HUMAN", "RT-RATIO",
        "QT-COV", "QT-CONSIST", "QT-AVAIL",
        "PT-DESIGN", "PT-DEV", "PT-VERIFY",
    ]
    for kw in required_keywords:
        if kw not in html_content:
            errors.append(f"Missing keyword in HTML: '{kw}'")

    if errors:
        raise SchemaError(errors)
    return True


# ============================================================================
# CLI: python3 scripts/schema.py <data.json> [report.html]
# ============================================================================

if __name__ == "__main__":
    import json

    if len(sys.argv) < 2:
        print("Usage: python3 scripts/schema.py <data.json> [report.html]")
        print("Validates data against SDD-TEE metrics schema.")
        sys.exit(0)

    # Validate JSON data
    with open(sys.argv[1]) as f:
        data = json.load(f)

    print(f"Validating {sys.argv[1]} against SDD-TEE schema...")
    try:
        warnings = validate_report_data(data)
        print(f"  DATA: PASS ({len(data.get('ar_results',[]))} ARs, "
              f"{len(STAGES)} stages × {len(STAGE_FIELDS)} fields × "
              f"{len(REQUIRED_AR_METRICS)} metrics)")
        for w in warnings:
            print(f"  WARN: {w}")
    except SchemaError as e:
        print(f"  DATA: FAIL")
        print(str(e))
        sys.exit(1)

    # Validate HTML if provided
    if len(sys.argv) > 2:
        with open(sys.argv[2], encoding="utf-8") as f:
            html = f.read()
        print(f"\nValidating {sys.argv[2]}...")
        try:
            validate_html_report(html)
            print(f"  HTML: PASS ({len(REQUIRED_REPORT_SECTIONS)} sections, keywords present)")
        except SchemaError as e:
            print(f"  HTML: FAIL")
            print(str(e))
            sys.exit(1)

    print("\nAll validations passed.")
