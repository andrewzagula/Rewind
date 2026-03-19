"""Safely load and execute user-defined strategy code."""

from __future__ import annotations

from typing import Any

from engine.strategy import Strategy


def load_strategy_class(code: str) -> type[Strategy]:
    """Execute strategy code and return the Strategy subclass defined in it.

    Args:
        code: Python source code containing exactly one Strategy subclass.

    Returns:
        The Strategy subclass.

    Raises:
        ValueError: If no Strategy subclass is found in the code.
    """
    namespace: dict[str, Any] = {"Strategy": Strategy}
    exec(code, namespace)  # noqa: S102 — sandboxing handled at worker level

    strategy_classes = [
        v
        for k, v in namespace.items()
        if isinstance(v, type) and issubclass(v, Strategy) and v is not Strategy
    ]

    if not strategy_classes:
        raise ValueError("No Strategy subclass found in the provided code.")

    return strategy_classes[0]
