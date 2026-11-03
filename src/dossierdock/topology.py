"""Deterministic multi-agent topology helpers."""

from __future__ import annotations

from dossierdock.config import AgentConfig


def agent_start_order(agents: tuple[AgentConfig, ...]) -> tuple[str, ...]:
    """Return a deterministic dependency-safe startup order.

    The manifest loader already rejects invalid or cyclic graphs. Preserving the
    manifest order for agents that become ready together keeps the resulting
    runbook stable and reviewable.
    """
    remaining = {agent.name: set(agent.depends_on) for agent in agents}
    order: list[str] = []

    while remaining:
        ready = [agent.name for agent in agents if agent.name in remaining and not remaining[agent.name]]
        if not ready:  # Defensive fallback; config validation rejects cycles.
            raise ValueError("Agent graph has no dependency-safe startup order.")
        for name in ready:
            order.append(name)
            del remaining[name]
        completed = set(ready)
        for dependencies in remaining.values():
            dependencies.difference_update(completed)

    return tuple(order)


def agent_graph(agents: tuple[AgentConfig, ...]) -> dict[str, object]:
    """Build a public, secret-free description of agent orchestration."""
    return {
        "agent_count": len(agents),
        "startup_order": list(agent_start_order(agents)),
        "agents": [
            {
                "name": agent.name,
                "role": agent.role,
                "depends_on": list(agent.depends_on),
                "healthcheck": agent.healthcheck,
                "timeout_seconds": agent.timeout_seconds,
            }
            for agent in agents
        ],
    }


def format_agent_graph(agents: tuple[AgentConfig, ...]) -> str:
    """Format an operator-friendly deployment runbook for agent startup."""
    if not agents:
        return "No explicit agents declared; deploy the service as a single runtime."

    by_name = {agent.name: agent for agent in agents}
    lines = ["Agent deployment order:"]
    for index, name in enumerate(agent_start_order(agents), start=1):
        agent = by_name[name]
        dependency_text = ", ".join(agent.depends_on) if agent.depends_on else "none"
        lines.append(
            f"{index}. {agent.name} — {agent.role} (after: {dependency_text}; "
            f"health: {agent.healthcheck}; timeout: {agent.timeout_seconds}s)"
        )
    return "\n".join(lines)
