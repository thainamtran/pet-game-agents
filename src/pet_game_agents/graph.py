"""LangGraph workflow: intake → design → code → art → test, with retry routing."""

from __future__ import annotations

import json
import uuid
from collections.abc import Callable
from typing import Any

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, Interrupt

from .agents.artist import artist_node
from .agents.coder import coder_node
from .agents.designer import designer_node
from .agents.manager import manager_node, route_after_manager
from .agents.tester import tester_node
from .config import Settings
from .human import default_decision, intake_node, normalize_decision, prompt_stdin
from .state import BuildState, initial_state
from .templates import write_text


def build_graph(settings: Settings | None = None, *, checkpointer: InMemorySaver | None = None):
    """Compile the multi-agent StateGraph.

    Nodes are agents. Edges follow design → code → art → test, then the
    Manager sends the work back to Coder (or GameDesigner) on failure,
    until the game is playable or max retries are exhausted.
    """
    settings = settings or Settings.from_env()

    def designer(state: BuildState) -> dict[str, Any]:
        return designer_node(state, settings)

    def coder(state: BuildState) -> dict[str, Any]:
        return coder_node(state, settings)

    def artist(state: BuildState) -> dict[str, Any]:
        return artist_node(state, settings)

    graph = StateGraph(BuildState)
    graph.add_node("intake", intake_node)
    graph.add_node("designer", designer)
    graph.add_node("coder", coder)
    graph.add_node("artist", artist)
    graph.add_node("tester", tester_node)
    graph.add_node("manager", manager_node)

    graph.add_edge(START, "intake")
    graph.add_edge("intake", "designer")
    graph.add_edge("designer", "coder")
    graph.add_edge("coder", "artist")
    graph.add_edge("artist", "tester")
    graph.add_edge("tester", "manager")
    graph.add_conditional_edges(
        "manager",
        route_after_manager,
        {"design": "designer", "code": "coder", "done": END},
    )
    return graph.compile(checkpointer=checkpointer or InMemorySaver())


def interrupt_payloads(result: dict[str, Any]) -> list[Any]:
    raw = result.get("__interrupt__") or []
    values = []
    for item in raw:
        if isinstance(item, Interrupt):
            values.append(item.value)
        elif isinstance(item, dict) and "value" in item:
            values.append(item["value"])
        else:
            values.append(item)
    return values


def run_pipeline(
    *,
    settings: Settings | None = None,
    auto_approve: bool | None = None,
    species: str | None = None,
    theme: str | None = None,
    output_dir: str | None = None,
    mode: str | None = None,
    max_retries: int | None = None,
    human_handler: Callable[[dict[str, Any]], Any] | None = None,
    thread_id: str | None = None,
    inject_coder_failures: int = 0,
) -> BuildState:
    """Run the full build. Pauses only for major decisions unless auto-approved."""
    overrides: dict[str, Any] = {}
    if auto_approve is not None:
        overrides["auto_approve"] = auto_approve
    if species is not None:
        overrides["species"] = species
    if theme is not None:
        overrides["theme"] = theme
    if output_dir is not None:
        overrides["output_dir"] = output_dir
    if mode is not None:
        overrides["mode"] = mode
    if max_retries is not None:
        overrides["max_retries"] = max_retries
    settings = settings or Settings.from_env(**overrides)

    resolved = settings.resolved_mode()
    if resolved == "llm":
        settings.require_llm_key()

    graph = build_graph(settings)
    config = {
        "configurable": {"thread_id": thread_id or str(uuid.uuid4())},
        "recursion_limit": 50,
    }
    state = initial_state(
        species=settings.species,
        theme=settings.theme,
        auto_approve=settings.auto_approve,
        output_dir=str(settings.output_dir),
        mode=resolved,
        max_retries=settings.max_retries,
        inject_coder_failures=inject_coder_failures,
    )
    result: dict[str, Any] = graph.invoke(state, config)
    while interrupt_payloads(result):
        payload = interrupt_payloads(result)[0]
        if not isinstance(payload, dict):
            payload = {"question": str(payload), "defaults": {"species": settings.species, "theme": settings.theme}}
        if settings.auto_approve:
            decision = default_decision(payload)
        elif human_handler is not None:
            decision = normalize_decision(human_handler(payload), payload)
        else:
            decision = prompt_stdin(payload)
        result = graph.invoke(Command(resume=decision), config)

    # Persist a machine-readable build log next to the game.
    log = list(result.get("log") or [])
    write_text(
        settings.output_dir / "pipeline_log.json",
        json.dumps(
            {
                "status": result.get("status"),
                "playable": result.get("playable"),
                "species": result.get("species"),
                "theme": result.get("theme"),
                "retries": result.get("retries"),
                "mode": result.get("mode"),
                "log": log,
                "test_report": result.get("test_report"),
            },
            indent=2,
        )
        + "\n",
    )
    return result  # type: ignore[return-value]
