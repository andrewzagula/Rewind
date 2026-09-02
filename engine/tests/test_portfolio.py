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
    p.update_position("AAPL", 10, 100.0)
    pnl = p.update_position("AAPL", -10, 120.0)
    assert pnl == 200.0
    assert p.get_position("AAPL").quantity == 0


def test_equity():
    p = Portfolio(cash=5_000)
    p.update_position("AAPL", 10, 100.0)
    equity = p.equity({"AAPL": 110.0})
    assert equity == 4_000 + 1_100


def test_buy_fees_raise_cost_basis_and_reduce_cash():
    p = Portfolio(cash=10_000)
    p.update_position("AAPL", 10, 100.0, fees=5.0)
    assert p.cash == 10_000 - 1_000 - 5.0
    assert p.get_position("AAPL").avg_price == 100.5


def test_sell_fees_reduce_pnl_and_cash():
    p = Portfolio(cash=10_000)
    p.update_position("AAPL", 10, 100.0)
    pnl = p.update_position("AAPL", -10, 120.0, fees=2.0)
    assert pnl == 198.0
    assert p.cash == 10_000 - 1_000 + 1_200 - 2.0
    assert p.held_quantity("AAPL") == 0
    assert p.held_quantity("MSFT") == 0
