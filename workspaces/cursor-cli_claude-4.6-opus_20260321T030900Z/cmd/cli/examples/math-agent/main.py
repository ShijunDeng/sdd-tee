"""
LangChain + LangGraph agent that runs Python in a sandbox via CodeInterpreterClient.
"""

from __future__ import annotations

import os
from typing import Annotated, Any

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent
from pydantic import Field

from agentcube import CodeInterpreterClient

load_dotenv()


def _sandbox() -> CodeInterpreterClient:
    base = os.environ["AGENTCUBE_CONTROL_PLANE_URL"]
    ns = os.environ.get("AGENTCUBE_NAMESPACE", "default")
    return CodeInterpreterClient(base, namespace=ns)


@tool("run_python_code")
def run_python_code(
    code: Annotated[str, Field(description="Python source to execute remotely")],
) -> str:
    """Execute Python in the AgentCube code interpreter and return structured output."""
    with _sandbox() as ci:
        out = ci.run_code(code, language="python")
        return str(out.get("output") or out.get("stdout") or out)


def main() -> None:
    question = os.environ.get("MATH_QUESTION", "What is 128 * 457?")
    llm = ChatOpenAI(model=os.environ.get("OPENAI_MODEL", "gpt-4o-mini"), temperature=0)
    graph = create_react_agent(llm, [run_python_code])
    messages: list[Any] = [
        SystemMessage(
            content=(
                "You are a careful math assistant. Use run_python_code for any non-trivial "
                "arithmetic and show the final answer clearly."
            )
        ),
        HumanMessage(content=question),
    ]
    result = graph.invoke({"messages": messages})
    for msg in result.get("messages", []):
        content = getattr(msg, "content", None)
        if content:
            print(content)


if __name__ == "__main__":
    main()
