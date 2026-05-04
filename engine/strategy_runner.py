from __future__ import annotations

import builtins
from typing import Any

from engine.signal import Signal
from engine.strategy import Strategy
from engine.strategy_validator import DISALLOWED_IMPORT_ROOTS, require_valid_strategy_code

SAFE_BUILTIN_NAMES = {
    "__build_class__",
    "Exception",
    "False",
    "None",
    "True",
    "ValueError",
    "abs",
    "all",
    "any",
    "bool",
    "dict",
    "enumerate",
    "float",
    "getattr",
    "hasattr",
    "int",
    "isinstance",
    "len",
    "list",
    "max",
    "min",
    "object",
    "range",
    "round",
    "set",
    "setattr",
    "str",
    "sum",
    "super",
    "tuple",
    "zip",
}


def _safe_import(
    name: str,
    globals: dict[str, Any] | None = None,
    locals: dict[str, Any] | None = None,
    fromlist: tuple[str, ...] = (),
    level: int = 0,
) -> Any:
    root_name = name.split(".", maxsplit=1)[0]
    if root_name in DISALLOWED_IMPORT_ROOTS:
        raise ImportError(f"Importing '{name}' is not allowed in strategy code.")
    return builtins.__import__(name, globals, locals, fromlist, level)


def _safe_builtins() -> dict[str, Any]:
    safe = {name: getattr(builtins, name) for name in SAFE_BUILTIN_NAMES}
    safe["__import__"] = _safe_import
    return safe


def load_strategy_class(code: str) -> type[Strategy]:
    require_valid_strategy_code(code)
    namespace: dict[str, Any] = {
        "Signal": Signal,
        "Strategy": Strategy,
        "__builtins__": _safe_builtins(),
        "__name__": "rewind_strategy",
    }
    exec(code, namespace)

    strategy_classes = [
        v
        for k, v in namespace.items()
        if isinstance(v, type) and issubclass(v, Strategy) and v is not Strategy
    ]

    if not strategy_classes:
        raise ValueError("No Strategy subclass found in the provided code.")

    return strategy_classes[0]
