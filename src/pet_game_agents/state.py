"""Shared LangGraph state for the pet-game build pipeline."""

from __future__ import annotations

import operator
from typing import Annotated, Any, Literal, NotRequired, TypedDict


class TestReport(TypedDict, total=False):
    passed: bool
    playable: bool
    category: Literal["code", "art", "design"]
    summary: str
    issues: list[str]
    pytest_exit_code: int
    pytest_output: str
    scripted_result: dict[str, Any]


class BuildState(TypedDict):
    """State that flows through the agent graph."""

    species: str
    theme: str
    auto_approve: bool
    output_dir: str
    mode: Literal["mock", "llm"]
    max_retries: int
    retries: int
    design: dict[str, Any] | None
    files_written: list[str]
    test_report: TestReport | None
    playable: bool
    failure_category: Literal["code", "art", "design"] | None
    status: Literal["running", "playable", "failed"]
    log: Annotated[list[str], operator.add]
    # Test-only hook: write broken code this many times before a good build.
    inject_coder_failures: NotRequired[int]


def initial_state(
    *,
    species: str,
    theme: str,
    auto_approve: bool,
    output_dir: str,
    mode: Literal["mock", "llm"],
    max_retries: int,
    inject_coder_failures: int = 0,
) -> BuildState:
    return BuildState(
        species=species,
        theme=theme,
        auto_approve=auto_approve,
        output_dir=output_dir,
        mode=mode,
        max_retries=max_retries,
        retries=0,
        design=None,
        files_written=[],
        test_report=None,
        playable=False,
        failure_category=None,
        status="running",
        log=[],
        inject_coder_failures=inject_coder_failures,
    )
