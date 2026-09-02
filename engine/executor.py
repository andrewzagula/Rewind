from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from engine.execution import ExecutionConfig
from engine.metrics import compute_metrics
from engine.portfolio import Portfolio
from engine.signal import Signal
from engine.strategy import Strategy


@dataclass
class BacktestResult:
    equity_curve: list[float] = field(default_factory=list)
    equity_points: list[dict[str, Any]] = field(default_factory=list)
    trades: list[dict[str, Any]] = field(default_factory=list)
    rejected_orders: list[dict[str, Any]] = field(default_factory=list)
    metrics: dict[str, float] = field(default_factory=dict)
    execution: dict[str, Any] = field(default_factory=dict)


@dataclass
class _PendingOrder:
    signal: Signal
    signal_timestamp: Any


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
    execution: ExecutionConfig | None = None,
) -> BacktestResult:
    """Run a strategy over bars.

    In ``next_open`` fill mode (the default), a signal produced while looking at bar *i*
    fills at bar *i+1*'s open. Pending fills are applied before the strategy sees the new
    bar, so the strategy always observes the portfolio it actually has. In ``close`` mode
    the signal fills at the same bar's close.
    """
    params = params or {}
    execution = execution or ExecutionConfig.from_params(params)
    portfolio = Portfolio(cash=initial_cash)
    strategy.init(params)

    result = BacktestResult(execution=execution.as_dict())
    trades_pnl: list[float] = []
    totals = {"fees": 0.0, "slippage": 0.0, "partial_fills": 0}
    pending: list[_PendingOrder] = []

    for index, row in enumerate(data):
        for order in pending:
            reference = row.get("open", row["close"])
            _fill(
                order.signal,
                reference,
                row,
                order.signal_timestamp,
                execution,
                portfolio,
                result,
                trades_pnl,
                totals,
            )
        pending = []

        signal = strategy.next(row, portfolio)
        if signal is not None:
            if execution.fill_mode == "close":
                _fill(
                    signal,
                    row["close"],
                    row,
                    row.get("timestamp"),
                    execution,
                    portfolio,
                    result,
                    trades_pnl,
                    totals,
                )
            else:
                pending.append(_PendingOrder(signal=signal, signal_timestamp=row.get("timestamp")))

        prices = {row["symbol"]: row["close"]}
        equity = portfolio.equity(prices)
        result.equity_curve.append(equity)
        result.equity_points.append(
            {
                "index": index,
                "timestamp": _timestamp_to_string(row.get("timestamp")),
                "value": equity,
            }
        )

    for order in pending:
        _reject(
            order.signal,
            order.signal_timestamp,
            "No later bar was available to fill the order.",
            result,
        )

    metrics = compute_metrics(result.equity_curve, trades_pnl) if result.equity_curve else {}
    if metrics:
        metrics["total_fees"] = round(totals["fees"], 6)
        metrics["total_slippage_cost"] = round(totals["slippage"], 6)
        metrics["partial_fills"] = totals["partial_fills"]
        metrics["rejected_orders"] = len(result.rejected_orders)
    result.metrics = metrics
    return result


def _fill(
    signal: Signal,
    reference_price: float,
    row: dict[str, Any],
    signal_timestamp: Any,
    execution: ExecutionConfig,
    portfolio: Portfolio,
    result: BacktestResult,
    trades_pnl: list[float],
    totals: dict[str, Any],
) -> None:
    requested = float(signal.quantity)
    if requested <= 0:
        _reject(signal, signal_timestamp, "Order quantity must be positive.", result)
        return

    price = execution.fill_price(signal.side, float(reference_price))
    quantity = requested

    if signal.side == "buy":
        if execution.enforce_cash:
            fees = execution.fees("buy", quantity, price)
            if quantity * price + fees.total > portfolio.cash + 1e-9:
                affordable = (
                    execution.affordable_quantity(portfolio.cash, price, quantity)
                    if execution.allow_partial_fills
                    else 0.0
                )
                if affordable <= 0:
                    _reject(
                        signal,
                        signal_timestamp,
                        f"Insufficient cash: {quantity:g} x {price:.2f} needs "
                        f"{quantity * price + fees.total:.2f} but only "
                        f"{portfolio.cash:.2f} is available.",
                        result,
                    )
                    return
                quantity = affordable
    else:
        held = portfolio.held_quantity(signal.symbol)
        if not execution.allow_short:
            if held <= 0:
                _reject(signal, signal_timestamp, f"No {signal.symbol} position to sell.", result)
                return
            if quantity > held + 1e-9:
                if not execution.allow_partial_fills:
                    _reject(
                        signal,
                        signal_timestamp,
                        f"Sell of {quantity:g} exceeds the {held:g} shares held.",
                        result,
                    )
                    return
                quantity = held

    fees = execution.fees(signal.side, quantity, price)
    signed = quantity if signal.side == "buy" else -quantity
    pnl = portfolio.update_position(signal.symbol, signed, price, fees=fees.total)
    slippage_cost = abs(price - float(reference_price)) * quantity

    totals["fees"] += fees.total
    totals["slippage"] += slippage_cost
    if quantity < requested - 1e-9:
        totals["partial_fills"] += 1

    trade = {
        "symbol": signal.symbol,
        "side": signal.side,
        "quantity": quantity,
        "requested_quantity": requested,
        "price": price,
        "reference_price": float(reference_price),
        "timestamp": row.get("timestamp", ""),
        "signal_timestamp": signal_timestamp,
        "pnl": pnl,
        "fees": round(fees.total, 6),
        "commission": fees.commission,
        "regulatory_fees": fees.regulatory,
        "slippage": round(slippage_cost, 6),
        "reason": signal.reason,
    }
    result.trades.append(trade)
    if signal.side == "sell":
        trades_pnl.append(pnl)


def _reject(signal: Signal, signal_timestamp: Any, reason: str, result: BacktestResult) -> None:
    result.rejected_orders.append(
        {
            "symbol": signal.symbol,
            "side": signal.side,
            "quantity": float(signal.quantity),
            "timestamp": _timestamp_to_string(signal_timestamp),
            "reason": reason,
            "strategy_reason": signal.reason,
        }
    )
