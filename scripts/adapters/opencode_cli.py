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
import select
import signal
import subprocess
import threading
import time
from pathlib import Path

from .base import BaseAdapter, StageRecord
try:
    from auditor import compute_token_cost
except ImportError:
    from scripts.auditor import compute_token_cost


class OpenCodeCliAdapter(BaseAdapter):
    def __init__(self, model: str):
        super().__init__("opencode-cli", model)

    def build_command(self, prompt: str, workspace: str) -> list[str]:
        os.makedirs(workspace, exist_ok=True)
        # For long prompts, write to file to avoid shell arg limits
        base = [
            "opencode", "run",
            "--dir", workspace,
            "--model", self.model,
            "--format", "json",
            "--log-level", "DEBUG",
            "--dangerously-skip-permissions",
        ]
        if len(prompt) > 8000:
            prompt_file = os.path.join(workspace, ".sdd_prompt.md")
            with open(prompt_file, "w", encoding="utf-8") as f:
                f.write(prompt)
            return base + [
                "Execute the SDD benchmark instructions in the attached prompt file. Write required files to disk.",
                "--file", prompt_file,
            ]
        return base + [prompt]

    def run(
        self,
        prompt: str,
        workspace: str,
        log_path: str,
        stage: str = "",
        stage_name: str = "",
        timeout: int = 600,
        max_retries: int = 1,
    ) -> StageRecord:
        """Run opencode and stop waiting once its JSON stream reports final stop.

        Some opencode runs keep language-server children alive after emitting the
        final `step_finish` event with `reason=stop`. Waiting for process exit in
        that state turns a completed model stage into a timeout and corrupts
        duration/retry data, so this adapter treats that final JSON event as the
        authoritative completion signal and terminates the lingering process group
        after a short grace period.
        """
        start_time = time.time()
        cmd = self.build_command(prompt, workspace)
        record = StageRecord(stage=stage, stage_name=stage_name)

        env = os.environ.copy()
        env = self._add_proxy_env(env)
        env["GIT_CEILING_DIRECTORIES"] = str(Path(workspace).resolve().parent)

        current_timeout = timeout
        for attempt in range(1, max_retries + 1):
            proc: subprocess.Popen | None = None
            stdout_lines: list[str] = []
            stderr_parts: list[str] = []
            forced_after_stop = False
            timed_out = False

            try:
                proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    cwd=workspace,
                    env=env,
                    start_new_session=True,
                )

                def drain_stderr() -> None:
                    if proc and proc.stderr:
                        stderr_parts.append(proc.stderr.read())

                stderr_thread = threading.Thread(target=drain_stderr, daemon=True)
                stderr_thread.start()

                deadline = time.time() + current_timeout
                final_stop_at: float | None = None
                while True:
                    if proc.stdout:
                        ready, _, _ = select.select([proc.stdout], [], [], 0.2)
                        if ready:
                            line = proc.stdout.readline()
                            if line:
                                stdout_lines.append(line)
                                if self._is_final_stop_event(line):
                                    final_stop_at = time.time()

                    if proc.poll() is not None:
                        break

                    if final_stop_at is not None and time.time() - final_stop_at >= 2:
                        forced_after_stop = True
                        self._terminate_process_group(proc)
                        break

                    if time.time() >= deadline:
                        timed_out = True
                        self._terminate_process_group(proc, kill=True)
                        break

                if proc.stdout:
                    tail = proc.stdout.read()
                    if tail:
                        stdout_lines.append(tail)
                try:
                    proc.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    self._terminate_process_group(proc, kill=True)
                stderr_thread.join(timeout=1)

                stdout = "".join(stdout_lines)
                stderr = "".join(stderr_parts)
                if timed_out:
                    log_text = f"EXIT_CODE: TIMEOUT\nSTDOUT:\n{stdout}\n"
                    if stderr:
                        log_text += f"\nSTDERR:\n{stderr}\n"
                    Path(log_path).write_text(log_text, encoding="utf-8")
                    if attempt < max_retries:
                        time.sleep(30)
                        current_timeout *= 2
                        continue
                    record.error = f"Failed after {max_retries} attempts: Timeout after {current_timeout}s"
                    record.duration_seconds = time.time() - start_time
                    self._apply_native_usage(record, log_text)
                    if record.api_calls == 0:
                        record.api_calls = 1
                        record.iterations = 1
                        record.data_source = "process_timeout_no_usage"
                    return record

                exit_code = 0 if forced_after_stop else proc.returncode
                record.exit_code = exit_code
                log_text = f"EXIT_CODE: {exit_code}\n"
                if forced_after_stop:
                    log_text += "NOTE: opencode process group terminated after final step_finish stop event.\n"
                log_text += f"STDOUT:\n{stdout}\n"
                if stderr:
                    log_text += f"\nSTDERR:\n{stderr}\n"
                Path(log_path).write_text(log_text, encoding="utf-8")
                if exit_code != 0:
                    record.error = f"Command exited with code {exit_code}"
                break

            except FileNotFoundError as e:
                record.error = f"Command not found: {cmd[0]} — {e}"
                record.duration_seconds = time.time() - start_time
                return record

            except Exception as e:
                if proc and proc.pid:
                    self._terminate_process_group(proc, kill=True)
                if attempt < max_retries:
                    time.sleep(30)
                    continue
                record.error = f"Failed after {max_retries} attempts: {e}"
                record.duration_seconds = time.time() - start_time
                return record

        record.duration_seconds = time.time() - start_time
        try:
            log_text = Path(log_path).read_text(encoding="utf-8")
        except OSError:
            log_text = ""
        self._apply_native_usage(record, log_text)
        return record

    @staticmethod
    def _is_final_stop_event(line: str) -> bool:
        line = line.strip()
        if not line.startswith("{"):
            return False
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            return False
        return (
            obj.get("type") == "step_finish"
            and obj.get("part", {}).get("reason") == "stop"
        )

    @staticmethod
    def _terminate_process_group(proc: subprocess.Popen, kill: bool = False) -> None:
        if proc.poll() is not None:
            return
        try:
            os.killpg(proc.pid, signal.SIGKILL if kill else signal.SIGTERM)
            if not kill:
                try:
                    proc.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass

    def _apply_native_usage(self, record: StageRecord, log_text: str) -> None:
        native = self.parse_native_output(log_text)
        if native.api_calls <= 0:
            return
        record.input_tokens = native.input_tokens
        record.output_tokens = native.output_tokens
        record.cache_read_tokens = native.cache_read_tokens
        record.cache_write_tokens = native.cache_write_tokens
        record.cost_usd = native.cost_usd
        record.api_calls = native.api_calls
        record.iterations = native.api_calls
        record.data_source = native.data_source if native.data_source != "none" else "native_output"

    def parse_native_output(self, log_text: str) -> StageRecord:
        record = StageRecord()
        total_input = 0
        total_output = 0
        total_cache_read = 0
        total_cache_write = 0
        total_cost = 0.0
        api_calls = 0
        started_calls = 0

        for line in log_text.splitlines():
            line = line.strip()
            if not line.startswith("{"):
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue

            if obj.get("type") == "step_start":
                started_calls += 1
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
            total_cost += compute_token_cost(self.model, inp, out, cr, cw)
            api_calls += 1

        record.input_tokens = total_input
        record.output_tokens = total_output
        record.cache_read_tokens = total_cache_read
        record.cache_write_tokens = total_cache_write
        record.cost_usd = total_cost
        record.api_calls = api_calls
        record.iterations = api_calls
        if api_calls == 0 and started_calls > 0:
            # A timed-out opencode run may expose only step_start and never emit
            # step_finish token usage. Count the attempted call without inventing
            # token or cost data.
            record.api_calls = started_calls
            record.iterations = started_calls
            record.data_source = "native_partial_timeout"
        return record
