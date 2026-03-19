from engine.portfolio import Portfolio


def test_initial_state():
    p = Portfolio()
    assert p.cash == 100_000.0
    assert p.positions == {}


def test_buy_updates_position():
    p = Portfolio(cash=10_000)
    pnl = p.update_position("AAPL", 10, 150.0)
    assert pnl == 0.0
    assert p.cash == 10_000 - 1_500
    assert p.get_position("AAPL").quantity == 10
    assert p.get_position("AAPL").avg_price == 150.0


def test_sell_computes_pnl():
    p = Portfolio(cash=10_000)
    p.update_position("AAPL", 10, 100.0)  # buy at 100
    pnl = p.update_position("AAPL", -10, 120.0)  # sell at 120
    assert pnl == 200.0  # (120 - 100) * 10
    assert p.get_position("AAPL").quantity == 0


def test_equity():
    p = Portfolio(cash=5_000)
    p.update_position("AAPL", 10, 100.0)
    equity = p.equity({"AAPL": 110.0})
    assert equity == 4_000 + 1_100  # remaining cash + position value
