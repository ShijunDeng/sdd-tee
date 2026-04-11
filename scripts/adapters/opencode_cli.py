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

            # Format 1: step_finish events (opencode native JSONL)
            if obj.get("type") == "step_finish":
                tokens = obj.get("part", {}).get("tokens", {})
                if isinstance(tokens, dict):
                    total_input += tokens.get("input", 0) or 0
                    total_output += tokens.get("output", 0) or 0
                    cache = tokens.get("cache", {})
                    if isinstance(cache, dict):
                        total_cache_read += cache.get("read", 0) or 0
                        total_cache_write += cache.get("write", 0) or 0
                    api_calls += 1

            # Format 2: usage field — only match if key actually exists
            usage = obj.get("usage") or obj.get("token_count")
            if isinstance(usage, dict) and usage:
                total_input += usage.get("input_tokens", usage.get("prompt_tokens", 0)) or 0
                total_output += usage.get("output_tokens", usage.get("completion_tokens", 0)) or 0
                total_cache_read += usage.get("cache_read_tokens", usage.get("cached_tokens", 0)) or 0
                total_cache_write += usage.get("cache_write_tokens", 0) or 0
                api_calls += 1

            # Format 3: Direct token fields
            direct_counted = False
            if "input_tokens" in obj:
                total_input += obj.get("input_tokens", 0) or 0
                direct_counted = True
            if "output_tokens" in obj:
                total_output += obj.get("output_tokens", 0) or 0
            if "cache_read_tokens" in obj:
                total_cache_read += obj.get("cache_read_tokens", 0) or 0
            if "cache_write_tokens" in obj:
                total_cache_write += obj.get("cache_write_tokens", 0) or 0
            if direct_counted:
                api_calls += 1

        record.input_tokens = total_input
        record.output_tokens = total_output
        record.cache_read_tokens = total_cache_read
        record.cache_write_tokens = total_cache_write
        record.api_calls = api_calls
        record.iterations = api_calls
        return record
