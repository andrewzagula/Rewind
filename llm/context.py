from __future__ import annotations

import json
from typing import Any


def format_prompt_context(context: dict[str, Any]) -> str:
    if not context:
        return "No additional context was provided."

    return (
        "Use only the trusted Rewind context below. If needed fields are missing, "
        "state that limitation explicitly instead of inferring values.\n\n"
        f"```json\n{json.dumps(context, indent=2, sort_keys=True, default=str)}\n```"
    )


def build_context(
    strategy_code: str = "",
    run_metrics: dict[str, Any] | None = None,
    recent_trades: list[dict[str, Any]] | None = None,
    dataset_info: dict[str, Any] | None = None,
) -> str:
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
