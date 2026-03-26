from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from engine.portfolio import Portfolio
    from engine.signal import Signal


class Strategy(ABC):
    def init(self, params: dict[str, Any]) -> None:
        pass

    @abstractmethod
    def next(self, row: dict[str, Any], portfolio: Portfolio) -> Signal | None:
        ...
