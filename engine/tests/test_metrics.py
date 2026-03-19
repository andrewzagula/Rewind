from engine.metrics import compute_metrics


def test_basic_metrics():
    equity = [100_000, 101_000, 102_000, 101_500, 103_000]
    pnl = [1000, 1000, -500, 1500]
    m = compute_metrics(equity, pnl)
    assert m["total_return"] > 0
    assert m["total_trades"] == 4
    assert m["win_rate"] == 0.75
    assert m["max_drawdown"] < 0


def test_empty_trades():
    equity = [100_000, 100_000, 100_000]
    m = compute_metrics(equity, [])
    assert m["total_trades"] == 0
    assert m["win_rate"] == 0.0
