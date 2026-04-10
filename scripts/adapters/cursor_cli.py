"""
Cursor CLI adapter for SDD-TEE.

Cursor CLI (`cursor agent`) has NO native token reporting in its output.
Token tracking requires LiteLLM Proxy interception via environment variables:
  - ANTHROPIC_BASE_URL=http://localhost:4000/v1  (for Claude models)
  - OPENAI_BASE_URL=http://localhost:4000/v1     (for OpenAI models)

If the proxy is not configured, token data will be zero with data_source="none".
NO estimated or fabricated data.
"""

from typing import Optional

from .base import BaseAdapter, StageRecord


class CursorCliAdapter(BaseAdapter):
    def __init__(self, model: str, api_base: Optional[str] = None):
        super().__init__("cursor-cli", model)
        self.api_base = api_base

    def build_command(self, prompt: str, workspace: str) -> list[str]:
        return ["cursor", "agent", prompt]

    def _add_proxy_env(self, env: dict) -> dict:
        if self.api_base:
            # Determine provider based on model name
            model_lower = self.model.lower()
            if any(kw in model_lower for kw in ["claude", "opus", "sonnet"]):
                env["ANTHROPIC_BASE_URL"] = self.api_base
            else:
                env["OPENAI_BASE_URL"] = self.api_base
        return env

    def parse_native_output(self, log_text: str) -> StageRecord:
        """Cursor CLI does not output token data. Returns zeros."""
        return StageRecord()
