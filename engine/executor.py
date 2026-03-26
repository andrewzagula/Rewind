from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from engine.metrics import compute_metrics
from engine.portfolio import Portfolio
from engine.strategy import Strategy


@dataclass
class BacktestResult:
    equity_curve: list[float] = field(default_factory=list)
    trades: list[dict[str, Any]] = field(default_factory=list)
    metrics: dict[str, float] = field(default_factory=dict)


def run_backtest(
    strategy: Strategy,
    data: list[dict[str, Any]],
    params: dict[str, Any] | None = None,
    initial_cash: float = 100_000.0,
) -> BacktestResult:
    portfolio = Portfolio(cash=initial_cash)
    strategy.init(params or {})

    equity_curve: list[float] = []
    trades: list[dict[str, Any]] = []
    trades_pnl: list[float] = []

    for row in data:
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
        equity_curve.append(portfolio.equity(prices))

    metrics = compute_metrics(equity_curve, trades_pnl) if equity_curve else {}

    return BacktestResult(
        equity_curve=equity_curve,
        trades=trades,
        metrics=metrics,
    )
