"""
OpenCode CLI adapter for SDD-TEE.

OpenCode CLI supports token telemetry via `run` subcommand with `--format json`:
  opencode run "prompt" --dir WORKSPACE --model MODEL --format json

The output contains usage data that can be parsed per-request.
"""

import json

from .base import BaseAdapter, StageRecord


class OpenCodeCliAdapter(BaseAdapter):
    def __init__(self, model: str):
        super().__init__("opencode-cli", model)

    def build_command(self, prompt: str, workspace: str) -> list[str]:
        return [
            "opencode", "run",
            prompt,
            "--dir", workspace,
            "--model", self.model,
            "--format", "json",
            "--log-level", "DEBUG",
        ]

    def parse_native_output(self, log_text: str) -> StageRecord:
        record = StageRecord()
        total_input = 0
        total_output = 0
        total_cache_read = 0
        total_cache_write = 0
        api_calls = 0

        for line in log_text.splitlines():
            line = line.strip()
            if not line.startswith("{"):
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue

            # Try usage field
            usage = obj.get("usage", obj.get("token_count", {}))
            if isinstance(usage, dict):
                total_input += usage.get("input_tokens", usage.get("prompt_tokens", 0)) or 0
                total_output += usage.get("output_tokens", usage.get("completion_tokens", 0)) or 0
                total_cache_read += usage.get("cache_read_tokens", usage.get("cached_tokens", 0)) or 0
                total_cache_write += usage.get("cache_write_tokens", 0) or 0
                api_calls += 1

            # Direct fields
            if "input_tokens" in obj:
                total_input += obj.get("input_tokens", 0) or 0
            if "output_tokens" in obj:
                total_output += obj.get("output_tokens", 0) or 0
            if "cache_read_tokens" in obj:
                total_cache_read += obj.get("cache_read_tokens", 0) or 0
            if "cache_write_tokens" in obj:
                total_cache_write += obj.get("cache_write_tokens", 0) or 0

        record.input_tokens = total_input
        record.output_tokens = total_output
        record.cache_read_tokens = total_cache_read
        record.cache_write_tokens = total_cache_write
        record.api_calls = api_calls
        record.iterations = api_calls
        return record
