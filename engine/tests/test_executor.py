from engine.executor import run_backtest
from engine.portfolio import Portfolio
from engine.signal import Signal
from engine.strategy import Strategy


class AlwaysBuy(Strategy):
    def next(self, row, portfolio):
        if not portfolio.position_symbols:
            return Signal(symbol=row["symbol"], side="buy", quantity=10)
        return None


def test_run_backtest_basic():
    data = [
        {"symbol": "TEST", "close": 100.0, "timestamp": "2024-01-01"},
        {"symbol": "TEST", "close": 105.0, "timestamp": "2024-01-02"},
        {"symbol": "TEST", "close": 110.0, "timestamp": "2024-01-03"},
    ]
    result = run_backtest(AlwaysBuy(), data)
    assert len(result.equity_curve) == 3
    assert len(result.trades) == 1  # buys once, then holds
    assert result.trades[0]["side"] == "buy"
    assert result.metrics  # non-empty
