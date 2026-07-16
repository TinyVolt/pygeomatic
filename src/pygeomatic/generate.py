"""Model-agnostic prompt → DSL loop.

`generate_dsl(prompt, complete)` asks any LLM (via the injected `complete`
callable) for a `build(gm)` function, executes it, and feeds errors back for
up to `max_attempts` tries. pygeomatic never imports a provider SDK — the
adapter is yours:

    def complete(system: str, messages: list[dict]) -> str:
        # messages are [{"role": "user"|"assistant", "content": str}, ...]
        # return the model's reply text
        ...
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable, Optional

from .prompting import system_prompt
from .runner import RunResult, run_generated

Complete = Callable[[str, list[dict]], str]

_CODE_BLOCK_RE = re.compile(r"```(?:python)?\s*\n(.*?)```", re.DOTALL)


def extract_code(reply: str) -> str:
    """The python code in the reply: last fenced block, else the raw text."""
    blocks = _CODE_BLOCK_RE.findall(reply)
    return (blocks[-1] if blocks else reply).strip()


@dataclass
class GenerateResult:
    dsl: list[str]
    code: str
    attempts: int
    messages: list[dict] = field(default_factory=list)


class GenerationError(RuntimeError):
    def __init__(self, message: str, attempts: list[RunResult], messages: list[dict]):
        super().__init__(message)
        self.attempts = attempts
        self.messages = messages


def generate_dsl(
    prompt: str,
    complete: Complete,
    *,
    max_attempts: int = 3,
    timeout: float = 20.0,
    system: Optional[str] = None,
) -> GenerateResult:
    """Turn a natural-language prompt into geomatic DSL commands.

    `complete(system, messages) -> str` is any LLM adapter. Raises
    GenerationError (with the full transcript) when every attempt fails.
    """
    system = system if system is not None else system_prompt()
    messages: list[dict] = [{"role": "user", "content": prompt}]
    runs: list[RunResult] = []

    for attempt in range(1, max_attempts + 1):
        reply = complete(system, messages)
        messages.append({"role": "assistant", "content": reply})
        result = run_generated(extract_code(reply), timeout=timeout)
        runs.append(result)
        if result.ok:
            return GenerateResult(
                dsl=result.dsl,
                code=result.code,
                attempts=attempt,
                messages=messages,
            )
        messages.append(
            {
                "role": "user",
                "content": (
                    "Running your code failed with:\n\n"
                    f"{result.error}\n\n"
                    "Fix the problem and resend the complete `build(gm)` "
                    "function as one fenced python code block."
                ),
            }
        )

    raise GenerationError(
        f"all {max_attempts} attempts failed; last error:\n{runs[-1].error}",
        attempts=runs,
        messages=messages,
    )
