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

            # Validation: the `total` field from opencode is the authoritative
            # per-step token count. We verify that our components sum correctly.
            # The `input` field only counts fresh (non-cached) prompt tokens,
            # while cache_read/cache_write track prompt cache reuse.
            # No clamping is applied because cache_write on the first step of a
            # session naturally exceeds the fresh input (it's the full prompt
            # being written to the provider's cache).
            step_total = inp + out + cr + cw
            if abs(step_total - tokens.get("total", step_total)) > 1:
                # If components don't match total, trust the total field and
                # derive input from it (output and cache are typically more reliable)
                total_reported = tokens.get("total", 0) or 0
                inp = max(0, total_reported - out - cr - cw)

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
