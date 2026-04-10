"""
Claude Code CLI adapter for SDD-TEE.

Claude Code supports token telemetry via `--output-format json`:
  claude --print --dangerously-skip-permissions --output-format json -p "prompt"

The JSON output is NDJSON — one JSON object per line with usage data.
"""

import json
from typing import Optional

from .base import BaseAdapter, StageRecord


class ClaudeCodeAdapter(BaseAdapter):
    def __init__(self, model: str, api_base: Optional[str] = None):
        super().__init__("claude-code", model)
        self.api_base = api_base

    def build_command(self, prompt: str, workspace: str) -> list[str]:
        cmd = [
            "claude",
            "--print",
            "--dangerously-skip-permissions",
            "--output-format", "json",
            "--model", self.model,
            "-p", prompt,
        ]
        return cmd

    def _add_proxy_env(self, env: dict) -> dict:
        if self.api_base:
            env["ANTHROPIC_BASE_URL"] = self.api_base
        return env

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

            usage = obj.get("usage", {})
            if isinstance(usage, dict):
                total_input += usage.get("input_tokens", 0) or 0
                total_output += usage.get("output_tokens", 0) or usage.get("completion_tokens", 0) or 0
                total_cache_read += usage.get("cache_read_input_tokens", 0) or 0
                total_cache_write += usage.get("cache_creation_input_tokens", 0) or 0
                api_calls += 1

        record.input_tokens = total_input
        record.output_tokens = total_output
        record.cache_read_tokens = total_cache_read
        record.cache_write_tokens = total_cache_write
        record.api_calls = api_calls
        record.iterations = api_calls
        return record
