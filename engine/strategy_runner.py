from __future__ import annotations

from typing import Any

from engine.strategy import Strategy


def load_strategy_class(code: str) -> type[Strategy]:
    namespace: dict[str, Any] = {"Strategy": Strategy}
    exec(code, namespace)

    strategy_classes = [
        v
        for k, v in namespace.items()
        if isinstance(v, type) and issubclass(v, Strategy) and v is not Strategy
    ]

    if not strategy_classes:
        raise ValueError("No Strategy subclass found in the provided code.")

    return strategy_classes[0]
