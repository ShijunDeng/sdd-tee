"""Dify tool: run code or shell commands in an AgentCube code interpreter sandbox."""

from __future__ import annotations

import json
from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin.errors.model import InvokeError

from agentcube import CodeInterpreterClient
from agentcube.clients.code_interpreter_data_plane import CodeInterpreterDataPlaneClient
from agentcube.clients.control_plane import ControlPlaneClient
from agentcube.exceptions import AgentCubeError


class AgentcubeCodeInterpreterTool(Tool):
    """Executes Python (or other) code and/or shell commands via ``CodeInterpreterClient``."""

    def _headers_from_credentials(self) -> dict[str, str]:
        creds = self.runtime.credentials or {}
        token = str(creds.get("api_key") or creds.get("bearer_token") or "").strip()
        if token:
            return {"Authorization": f"Bearer {token}"}
        return {}

    def _control_plane_url(self) -> str:
        url = str((self.runtime.credentials or {}).get("control_plane_url") or "").strip()
        if not url:
            raise InvokeError("Missing control_plane_url in provider credentials")
        return url

    def _namespace(self) -> str:
        ns = str((self.runtime.credentials or {}).get("namespace") or "").strip()
        if not ns:
            raise InvokeError("Missing namespace in provider credentials")
        return ns

    def execute(self, tool_parameters: dict[str, Any]) -> dict[str, Any]:
        """
        Perform remote execution and return structured output.

        Exactly one of ``code`` or ``command`` should normally be supplied; if both are set,
        the command runs after optional code execution in the same session.
        """
        language = str(tool_parameters.get("language") or "python").strip() or "python"
        code = str(tool_parameters.get("code") or "").strip()
        command = str(tool_parameters.get("command") or "").strip()
        cwd = str(tool_parameters.get("cwd") or "").strip() or None
        session_reuse = bool(tool_parameters.get("session_reuse"))
        interpreter_id = str(tool_parameters.get("interpreter_id") or "").strip() or None

        if not code and not command:
            raise InvokeError("Provide at least one of 'code' or 'command'")

        control_plane_url = self._control_plane_url()
        namespace = self._namespace()
        headers = self._headers_from_credentials()
        results: dict[str, Any] = {"language": language, "session_reuse": session_reuse}

        try:
            if interpreter_id:
                results["interpreter_id"] = interpreter_id
                cp = ControlPlaneClient(control_plane_url, headers=headers)
                dp = CodeInterpreterDataPlaneClient(
                    control_plane_url,
                    namespace=namespace,
                    interpreter_id=interpreter_id,
                    session=cp.session,
                    headers=headers,
                )
                try:
                    if code:
                        results["run_code"] = dp.run_code(code, language=language)
                    if command:
                        results["execute_command"] = dp.execute_command(command, cwd=cwd)
                finally:
                    dp.close()
                    if not session_reuse:
                        try:
                            cp.delete_session(interpreter_id)
                        except Exception:
                            pass
                    cp.close()
                return results

            with CodeInterpreterClient(
                control_plane_url,
                namespace=namespace,
                headers=headers,
            ) as client:
                results["interpreter_id"] = client.interpreter_id
                if code:
                    results["run_code"] = client.run_code(code, language=language)
                if command:
                    results["execute_command"] = client.execute_command(command, cwd=cwd)
            return results
        except AgentCubeError as exc:
            raise InvokeError(str(exc)) from exc
        except InvokeError:
            raise
        except Exception as exc:
            raise InvokeError(f"AgentCube execution failed: {exc}") from exc

    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        try:
            payload = self.execute(tool_parameters)
            yield self.create_json_message(payload)
        except InvokeError as exc:
            yield self.create_text_message(json.dumps({"error": str(exc)}, ensure_ascii=False))
        except Exception as exc:
            yield self.create_text_message(json.dumps({"error": str(exc)}, ensure_ascii=False))
