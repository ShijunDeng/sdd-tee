#!/usr/bin/env python3
"""
SDD-TEE CLI Adapters — Base classes and interfaces.

Each adapter runs a CLI tool as a subprocess, captures raw output to a log file,
and optionally parses native token data from the output. The authoritative
token source is always the LiteLLM Proxy JSONL log (see auditor.py).

Usage:
    adapter = ClaudeCodeAdapter(model, api_base)
    record = adapter.run(prompt, workspace, log_path)
    # record has input_tokens, output_tokens, etc. from native parsing
    # For authoritative data, use auditor.get_tokens(model, start, end)
"""

import os
import subprocess
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class StageRecord:
    """Token record for a single SDD stage execution.

    All token fields are initially 0. They are populated by:
    1. Native CLI output parsing (in adapter) — may be incomplete
    2. LiteLLM Proxy audit (in engine) — authoritative, overwrites native data

    data_source indicates where the token data came from:
    - "litellm_proxy": from LiteLLM Proxy JSONL log (authoritative)
    - "native_output": parsed from CLI tool's stdout/stderr (fallback, may be incomplete)
    - "none": no token data available (tool doesn't support tracking)
    """
    stage: str = ""
    stage_name: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    iterations: int = 0
    duration_seconds: float = 0.0
    api_calls: int = 0
    error: Optional[str] = None
    data_source: str = "none"


class BaseAdapter(ABC):
    """Base class for CLI tool adapters."""

    def __init__(self, tool_name: str, model: str):
        self.tool_name = tool_name
        self.model = model

    @abstractmethod
    def build_command(self, prompt: str, workspace: str) -> list[str]:
        """Build the CLI command to execute a prompt."""

    @abstractmethod
    def parse_native_output(self, log_text: str) -> StageRecord:
        """Parse native token data from CLI output.
        Returns StageRecord with token fields populated from CLI output,
        or a record with all zeros if parsing fails.
        """

    def run(
        self,
        prompt: str,
        workspace: str,
        log_path: str,
        stage: str = "",
        stage_name: str = "",
        timeout: int = 600,
    ) -> StageRecord:
        """Run a prompt through the CLI tool.

        Executes the command, captures stdout/stderr to log_path,
        and attempts native token parsing.
        Returns StageRecord with token data from native output.
        The engine will later overwrite this with authoritative proxy data.
        """
        start_time = time.time()
        cmd = self.build_command(prompt, workspace)
        record = StageRecord(stage=stage, stage_name=stage_name)

        # Set proxy env vars if configured
        env = os.environ.copy()
        env = self._add_proxy_env(env)

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=workspace,
                env=env,
            )
            # Write combined output to log
            log_text = f"EXIT_CODE: {result.returncode}\n"
            log_text += f"STDOUT:\n{result.stdout}\n"
            if result.stderr:
                log_text += f"\nSTDERR:\n{result.stderr}\n"
            Path(log_path).write_text(log_text, encoding="utf-8")

        except subprocess.TimeoutExpired:
            record.error = f"Timeout after {timeout}s"
            record.duration_seconds = timeout
            return record
        except FileNotFoundError as e:
            record.error = f"Command not found: {cmd[0]} — {e}"
            record.duration_seconds = time.time() - start_time
            return record
        except Exception as e:
            record.error = str(e)
            record.duration_seconds = time.time() - start_time
            return record

        record.duration_seconds = time.time() - start_time

        # Try native token parsing
        native = self.parse_native_output(log_text)
        if native.api_calls > 0:
            record.input_tokens = native.input_tokens
            record.output_tokens = native.output_tokens
            record.cache_read_tokens = native.cache_read_tokens
            record.cache_write_tokens = native.cache_write_tokens
            record.api_calls = native.api_calls
            record.iterations = native.api_calls
            record.data_source = "native_output"

        return record

    def _add_proxy_env(self, env: dict) -> dict:
        """Add LiteLLM proxy env vars if configured. Override in subclasses."""
        return env
