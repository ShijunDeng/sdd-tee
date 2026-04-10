"""
Gemini CLI adapter for SDD-TEE.

Gemini CLI outputs token usage via `--output-format json`.
The JSON contains step_finish events with token data.
"""

import json

from .base import BaseAdapter, StageRecord


class GeminiCliAdapter(BaseAdapter):
    def __init__(self, model: str):
        super().__init__("gemini-cli", model)

    def build_command(self, prompt: str, workspace: str) -> list[str]:
        return [
            "gemini",
            "--model", self.model,
            "--prompt", prompt,
            "--yolo",
            "--output-format", "json",
        ]

    def parse_native_output(self, log_text: str) -> StageRecord:
        record = StageRecord()
        total_input = 0
        total_output = 0
        total_cache_read = 0
        api_calls = 0

        for line in log_text.splitlines():
            line = line.strip()
            if not line.startswith("{"):
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue

            # Gemini CLI step_finish events
            if obj.get("type") == "step_finish":
                part = obj.get("part", {})
                tokens = part.get("tokens", {})
                if isinstance(tokens, dict):
                    total_input += tokens.get("input", 0) or 0
                    total_output += tokens.get("output", 0) or 0
                    cache = tokens.get("cache", {})
                    if isinstance(cache, dict):
                        total_cache_read += cache.get("read", 0) or 0
                    api_calls += 1
            # Also check for direct usage fields
            else:
                usage = obj.get("usage", obj.get("tokenCount", {}))
                if isinstance(usage, dict):
                    total_input += usage.get("input_tokens", usage.get("inputTokenCount", 0)) or 0
                    total_output += usage.get("output_tokens", usage.get("outputTokenCount", 0)) or 0
                    api_calls += 1

        record.input_tokens = total_input
        record.output_tokens = total_output
        record.cache_read_tokens = total_cache_read
        record.api_calls = api_calls
        record.iterations = api_calls
        return record
