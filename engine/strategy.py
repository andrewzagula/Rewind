"""Base Strategy class that all user strategies extend."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from engine.portfolio import Portfolio
    from engine.signal import Signal


class Strategy(ABC):
    """Base class for defining trading strategies.

    Subclass this and implement `init()` and `next()` to create a strategy.

    Example:
        class SMACrossover(Strategy):
            def init(self, params: dict) -> None:
                self.fast = params.get("fast_period", 10)
                self.slow = params.get("slow_period", 30)

            def next(self, row: dict, portfolio: Portfolio) -> Signal | None:
                if row["sma_fast"] > row["sma_slow"]:
                    return Signal(symbol=row["symbol"], side="buy", quantity=100)
                return None
    """

    def init(self, params: dict[str, Any]) -> None:
        """Called once before the backtest starts. Set up indicators and state."""

    @abstractmethod
    def next(self, row: dict[str, Any], portfolio: Portfolio) -> Signal | None:
        """Called for each bar. Return a Signal to trade, or None to hold."""
        ...
