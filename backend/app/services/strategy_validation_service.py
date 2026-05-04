from __future__ import annotations

import sys
from pathlib import Path
from typing import Protocol


class StrategyValidationResult(Protocol):
    valid: bool
    errors: list[str]


class StrategyCodeValidationError(ValueError):
    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__("Strategy code is invalid: " + "; ".join(errors))


def validate_strategy_code_for_api(code: str) -> None:
    result = _validate_strategy_code(code)
    if not result.valid:
        raise StrategyCodeValidationError(result.errors)


def _validate_strategy_code(code: str) -> StrategyValidationResult:
    try:
        from engine.strategy_validator import validate_strategy_code
    except ModuleNotFoundError:
        _add_repo_roots_to_path()
        from engine.strategy_validator import validate_strategy_code

    return validate_strategy_code(code)


def _add_repo_roots_to_path() -> None:
    current = Path(__file__).resolve()
    candidates = [
        Path.cwd(),
        Path.cwd().parent,
        current.parents[3],
    ]
    for candidate in candidates:
        if (candidate / "engine" / "strategy_validator.py").exists():
            candidate_str = str(candidate)
            if candidate_str not in sys.path:
                sys.path.insert(0, candidate_str)
