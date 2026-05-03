from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from engine.metrics import compute_metrics
from engine.portfolio import Portfolio
from engine.strategy import Strategy


@dataclass
class BacktestResult:
    equity_curve: list[float] = field(default_factory=list)
    equity_points: list[dict[str, Any]] = field(default_factory=list)
    trades: list[dict[str, Any]] = field(default_factory=list)
    metrics: dict[str, float] = field(default_factory=dict)


def _timestamp_to_string(value: Any) -> str:
    if value is None:
        return ""
    if hasattr(value, "isoformat"):
        return str(value.isoformat())
    return str(value)


def run_backtest(
    strategy: Strategy,
    data: list[dict[str, Any]],
    params: dict[str, Any] | None = None,
    initial_cash: float = 100_000.0,
) -> BacktestResult:
    portfolio = Portfolio(cash=initial_cash)
    strategy.init(params or {})

    equity_curve: list[float] = []
    equity_points: list[dict[str, Any]] = []
    trades: list[dict[str, Any]] = []
    trades_pnl: list[float] = []

    for index, row in enumerate(data):
        signal = strategy.next(row, portfolio)

        if signal is not None:
            qty = signal.quantity if signal.side == "buy" else -signal.quantity
            price = row["close"]
            pnl = portfolio.update_position(signal.symbol, qty, price)

            trade = {
                "symbol": signal.symbol,
                "side": signal.side,
                "quantity": signal.quantity,
                "price": price,
                "timestamp": row.get("timestamp", ""),
                "pnl": pnl,
                "reason": signal.reason,
            }
            trades.append(trade)
            if signal.side == "sell":
                trades_pnl.append(pnl)

        prices = {row["symbol"]: row["close"]}
        equity = portfolio.equity(prices)
        equity_curve.append(equity)
        equity_points.append(
            {
                "index": index,
                "timestamp": _timestamp_to_string(row.get("timestamp")),
                "value": equity,
            }
        )

    metrics = compute_metrics(equity_curve, trades_pnl) if equity_curve else {}

    return BacktestResult(
        equity_curve=equity_curve,
        equity_points=equity_points,
        trades=trades,
        metrics=metrics,
    )
