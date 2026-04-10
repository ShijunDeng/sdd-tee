#!/usr/bin/env python3
"""
SDD-TEE Token Auditor — LiteLLM Proxy JSONL log parser.

This is the AUTHORITATIVE source of token data.
Every API call that passes through LiteLLM Proxy is logged to a JSONL file
with exact usage metadata from the model provider's response.

The auditor filters requests by time window and model, then aggregates
per-stage token counts. NO data is fabricated or estimated.

Usage:
    from scripts.auditor import TokenAuditor

    auditor = TokenAuditor("results/litellm_requests.jsonl")
    audit = auditor.get_tokens("claude-sonnet-4", start_time, end_time)
    print(f"Input: {audit.input_tokens}, Output: {audit.output_tokens}")
"""

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

# Official pricing per 1M tokens, USD.
# Sources:
#   Anthropic: https://www.anthropic.com/pricing
#   Google:    https://ai.google.dev/pricing
#   OpenAI:    https://openai.com/api/pricing
#   Zhipu:     https://open.bigmodel.cn/pricing
#   Moonshot:  https://platform.moonshot.cn/docs/pricing
#   MiniMax:   https://api.minimax.chat/docs/pricing
#   DashScope: https://help.aliyun.com/pricing
PRICING = {
    # Anthropic
    "claude-4.6-opus-high-thinking": {"input": 15.0, "output": 75.0, "cache_read": 1.50, "cache_write": 18.75},
    "claude-sonnet-4":               {"input": 3.0,  "output": 15.0, "cache_read": 0.30, "cache_write": 3.75},
    "claude-opus-4":                 {"input": 15.0, "output": 75.0, "cache_read": 1.50, "cache_write": 18.75},
    # Google
    "gemini-3.1-pro":                {"input": 1.25, "output": 10.0,  "cache_read": 0.10, "cache_write": 1.50},
    "gemini-2.5-pro":                {"input": 1.25, "output": 10.0,  "cache_read": 0.10, "cache_write": 1.50},
    # OpenAI
    "gpt-4.1":                       {"input": 2.0,  "output": 8.0,  "cache_read": 0.25, "cache_write": 2.50},
    "gpt-5.3-codex-spark-preview-xhigh": {"input": 2.0,  "output": 8.0,  "cache_read": 0.25, "cache_write": 2.50},
    # Zhipu
    "glm-5":                         {"input": 0.5,   "output": 2.0,  "cache_read": 0.1,  "cache_write": 0.5},
    "glm-4.7":                       {"input": 0.5,   "output": 2.0,  "cache_read": 0.1,  "cache_write": 0.5},
    # Moonshot
    "kimi-k2.5":                     {"input": 0.5,   "output": 2.0,  "cache_read": 0.1,  "cache_write": 0.5},
    # MiniMax
    "minimax-m2.5":                  {"input": 0.5,   "output": 2.0,  "cache_read": 0.1,  "cache_write": 0.5},
    # DashScope / Qwen
    "qwen3.5-plus":                  {"input": 0.5,   "output": 2.0,  "cache_read": 0.1,  "cache_write": 0.5},
}


@dataclass
class TokenAudit:
    """Aggregated token counts from real API responses. All fields are from provider responses."""
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    api_calls: int = 0
    model: str = ""
    records: list = None

    def __post_init__(self):
        if self.records is None:
            self.records = []

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    @property
    def net_input_tokens(self) -> int:
        """Billable input tokens (input minus cache hits)."""
        return max(0, self.input_tokens - self.cache_read_tokens)

    def compute_cost(self, model_name: str) -> float:
        """Compute cost in USD using official pricing."""
        pricing = get_pricing(model_name)
        if not pricing:
            return 0.0
        return (
            self.net_input_tokens * pricing["input"]
            + self.output_tokens * pricing["output"]
            + self.cache_read_tokens * pricing["cache_read"]
            + self.cache_write_tokens * pricing["cache_write"]
        ) / 1_000_000


def get_pricing(model_name: str) -> Optional[dict]:
    """Get pricing for a model. Returns None if model not found in PRICING table."""
    # Exact match
    if model_name in PRICING:
        return PRICING[model_name]
    # Partial match (model_name may include provider prefix)
    model_lower = model_name.lower()
    for key, pricing in PRICING.items():
        if key.lower() in model_lower or model_lower.split("/")[-1] == key.lower():
            return pricing
    return None


class TokenAuditor:
    """Read LiteLLM Proxy JSONL log and filter by time window + model."""

    def __init__(self, log_path: str):
        self.log_path = Path(log_path)

    def get_tokens(
        self,
        model: str,
        start_time: float,
        end_time: float,
    ) -> TokenAudit:
        """Get token counts for a specific time window.

        Args:
            model: Model name to filter by.
            start_time: Unix timestamp (inclusive).
            end_time: Unix timestamp (exclusive).

        Returns:
            TokenAudit with counts from real API responses.
            If log file doesn't exist or no matching requests, returns zeros.
        """
        audit = TokenAudit(model=model)

        if not self.log_path.exists():
            return audit

        for line in self.log_path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line.startswith("{"):
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue

            # Time filter
            ts = self._extract_timestamp(obj)
            if ts < start_time or ts >= end_time:
                continue

            # Model filter
            req_model = obj.get("model", obj.get("model_id", ""))
            if model and model not in req_model and req_model not in model:
                # Also check without provider prefix
                model_short = model.split("/")[-1] if "/" in model else model
                req_short = req_model.split("/")[-1] if "/" in req_model else req_model
                if model_short != req_short:
                    continue

            # Extract usage
            usage = self._extract_usage(obj)
            if usage:
                audit.input_tokens += usage.get("prompt_tokens", 0) or 0
                audit.output_tokens += usage.get("completion_tokens", 0) or 0
                audit.cache_read_tokens += usage.get("cache_read_input_tokens", 0) or 0
                audit.cache_write_tokens += usage.get("cache_creation_input_tokens", 0) or 0
                audit.api_calls += 1
                audit.records.append(obj)

        return audit

    def get_all_tokens(self, model: str) -> TokenAudit:
        """Get all token counts for a model, no time filter."""
        return self.get_tokens(model, 0.0, float("inf"))

    def _extract_timestamp(self, obj: dict) -> float:
        """Extract Unix timestamp from a LiteLLM log record."""
        # Try common timestamp fields
        for field in ["timestamp", "ts", "time", "created_at"]:
            val = obj.get(field)
            if val is not None:
                if isinstance(val, (int, float)):
                    return float(val)
                if isinstance(val, str):
                    try:
                        return datetime.fromisoformat(val.replace("Z", "+00:00")).timestamp()
                    except (ValueError, AttributeError):
                        pass
        # Try response.created
        resp = obj.get("response", {})
        if isinstance(resp, dict):
            created = resp.get("created")
            if created:
                return float(created)
        return 0.0

    def _extract_usage(self, obj: dict) -> Optional[dict]:
        """Extract usage dict from a LiteLLM log record."""
        # Top-level usage
        usage = obj.get("usage")
        if isinstance(usage, dict) and any(
            usage.get(k, 0) for k in ["prompt_tokens", "completion_tokens", "total_tokens"]
        ):
            return usage

        # Inside response object
        resp = obj.get("response")
        if isinstance(resp, dict):
            usage = resp.get("usage")
            if isinstance(usage, dict):
                return usage

        # Inside model_response
        mr = obj.get("model_response")
        if isinstance(mr, dict):
            usage = mr.get("usage")
            if isinstance(usage, dict):
                return usage

        return None
