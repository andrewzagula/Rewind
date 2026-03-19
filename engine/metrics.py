"""Compute performance metrics from an equity curve and trade list."""

from __future__ import annotations

import numpy as np


def compute_metrics(
    equity_curve: list[float],
    trades_pnl: list[float],
    risk_free_rate: float = 0.0,
    periods_per_year: int = 252,
) -> dict[str, float]:
    """Compute standard backtest performance metrics."""
    equity = np.array(equity_curve, dtype=np.float64)
    returns = np.diff(equity) / equity[:-1]

    total_return = (equity[-1] / equity[0]) - 1 if len(equity) > 1 else 0.0
    n_periods = len(returns)
    ann_factor = periods_per_year / n_periods if n_periods > 0 else 1.0
    annualized_return = (1 + total_return) ** ann_factor - 1

    vol = float(np.std(returns) * np.sqrt(periods_per_year)) if n_periods > 0 else 0.0
    sharpe = (annualized_return - risk_free_rate) / vol if vol > 0 else 0.0

    downside = returns[returns < 0]
    downside_vol = float(np.std(downside) * np.sqrt(periods_per_year)) if len(downside) > 0 else 0.0
    sortino = (annualized_return - risk_free_rate) / downside_vol if downside_vol > 0 else 0.0

    # Max drawdown
    peak = np.maximum.accumulate(equity)
    drawdown = (equity - peak) / peak
    max_drawdown = float(np.min(drawdown)) if len(drawdown) > 0 else 0.0

    calmar = annualized_return / abs(max_drawdown) if max_drawdown != 0 else 0.0

    # Trade stats
    pnl = np.array(trades_pnl, dtype=np.float64) if trades_pnl else np.array([])
    wins = pnl[pnl > 0]
    losses = pnl[pnl < 0]
    total_trades = len(pnl)
    win_rate = len(wins) / total_trades if total_trades > 0 else 0.0
    gross_profit = float(np.sum(wins)) if len(wins) > 0 else 0.0
    gross_loss = abs(float(np.sum(losses))) if len(losses) > 0 else 0.0
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else 0.0

    return {
        "total_return": round(total_return, 6),
        "annualized_return": round(annualized_return, 6),
        "sharpe_ratio": round(sharpe, 4),
        "sortino_ratio": round(sortino, 4),
        "max_drawdown": round(max_drawdown, 6),
        "calmar_ratio": round(calmar, 4),
        "volatility_annual": round(vol, 6),
        "total_trades": total_trades,
        "win_rate": round(win_rate, 4),
        "profit_factor": round(profit_factor, 4),
        "avg_trade_pnl": round(float(np.mean(pnl)), 6) if total_trades > 0 else 0.0,
        "avg_win": round(float(np.mean(wins)), 6) if len(wins) > 0 else 0.0,
        "avg_loss": round(float(np.mean(losses)), 6) if len(losses) > 0 else 0.0,
    }
