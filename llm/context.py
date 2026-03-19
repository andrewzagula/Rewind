"""Build context payloads for LLM prompts."""

from __future__ import annotations

import json
from typing import Any


def build_context(
    strategy_code: str = "",
    run_metrics: dict[str, Any] | None = None,
    recent_trades: list[dict[str, Any]] | None = None,
    dataset_info: dict[str, Any] | None = None,
) -> str:
    """Assemble context for injection into LLM system prompt."""
    sections = []

    if strategy_code:
        sections.append(f"## Current Strategy Code\n```python\n{strategy_code}\n```")

    if run_metrics:
        sections.append(f"## Run Metrics\n```json\n{json.dumps(run_metrics, indent=2)}\n```")

    if recent_trades:
        trades_str = json.dumps(recent_trades[:50], indent=2)
        sections.append(f"## Recent Trades (last 50)\n```json\n{trades_str}\n```")

    if dataset_info:
        sections.append(f"## Dataset\n```json\n{json.dumps(dataset_info, indent=2)}\n```")

    return "\n\n".join(sections)
