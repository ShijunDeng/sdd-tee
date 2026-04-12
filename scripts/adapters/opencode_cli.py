"""
OpenCode CLI adapter for SDD-TEE.

OpenCode CLI supports token telemetry via `run` subcommand with `--format json`:
  opencode run "prompt" --dir WORKSPACE --model MODEL --format json

The output contains usage data that can be parsed per-request.

Prompt handling:
- For short prompts (<8000 chars), pass directly as CLI argument
- For long prompts, write to a temporary file and use @filename syntax
  to avoid shell argument length limits
"""

import json
import os
import tempfile

from .base import BaseAdapter, StageRecord


class OpenCodeCliAdapter(BaseAdapter):
    def __init__(self, model: str):
        super().__init__("opencode-cli", model)

    def build_command(self, prompt: str, workspace: str) -> list[str]:
        # For long prompts, write to file to avoid shell arg limits
        if len(prompt) > 8000:
            prompt_file = os.path.join(workspace, ".sdd_prompt.md")
            with open(prompt_file, "w", encoding="utf-8") as f:
                f.write(prompt)
            return [
                "opencode", "run",
                f"@{prompt_file}",
                "--dir", workspace,
                "--model", self.model,
                "--format", "json",
                "--log-level", "DEBUG",
            ]
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

            # Only parse step_finish events — these are the authoritative per-request
            # token records from opencode CLI. Other JSON lines (debug logs, cumulative
            # stats, session summaries) are ignored to prevent double-counting.
            if obj.get("type") != "step_finish":
                continue

            tokens = obj.get("part", {}).get("tokens", {})
            if not isinstance(tokens, dict):
                continue

            inp = tokens.get("input", 0) or 0
            out = tokens.get("output", 0) or 0
            cache = tokens.get("cache", {})
            if not isinstance(cache, dict):
                cache = {}
            cr = cache.get("read", 0) or 0
            cw = cache.get("write", 0) or 0

            # Validation: cache tokens cannot exceed input (physically impossible).
            # When violated, the fields are likely misinterpreted (e.g. cumulative
            # session stats). Clamp to input to prevent inflated totals.
            gross_input = inp + cr  # opencode may report base input + cache separately
            if cw > gross_input:
                cw = gross_input
            if cr > gross_input:
                cr = gross_input
            # After clamping, ensure individual cache fields don't exceed total input
            total_prompt = inp + cr  # total prompt = fresh input + cached input
            if cw > total_prompt:
                cw = total_prompt
            if cr > total_prompt:
                cr = total_prompt

            total_input += inp
            total_output += out
            total_cache_read += cr
            total_cache_write += cw
            api_calls += 1

        record.input_tokens = total_input
        record.output_tokens = total_output
        record.cache_read_tokens = total_cache_read
        record.cache_write_tokens = total_cache_write
        record.api_calls = api_calls
        record.iterations = api_calls
        return record
