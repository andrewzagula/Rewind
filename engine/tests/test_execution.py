import pytest

from engine.execution import ExecutionConfig, ExecutionConfigError
from engine.executor import run_backtest
from engine.signal import Signal
from engine.strategy import Strategy


def bars(*closes: float, symbol: str = "TEST") -> list[dict]:
    return [
        {
            "symbol": symbol,
            "timestamp": f"2024-01-{index + 1:02d}",
            "open": close - 1.0,
            "high": close + 1.0,
            "low": close - 2.0,
            "close": close,
            "volume": 1_000,
        }
        for index, close in enumerate(closes)
    ]


class BuyOnce(Strategy):
    def __init__(self, quantity: float = 10) -> None:
        self.quantity = quantity

    def next(self, row, portfolio):
        if not portfolio.position_symbols and not getattr(self, "done", False):
            self.done = True
            return Signal(symbol=row["symbol"], side="buy", quantity=self.quantity)
        return None


class BuyThenSell(Strategy):
    def init(self, params):
        self.step = 0

    def next(self, row, portfolio):
        self.step += 1
        if self.step == 1:
            return Signal(symbol=row["symbol"], side="buy", quantity=10)
        if self.step == 3:
            return Signal(symbol=row["symbol"], side="sell", quantity=10)
        return None


class SellWithoutPosition(Strategy):
    def next(self, row, portfolio):
        return Signal(symbol=row["symbol"], side="sell", quantity=5)


# ---- config -----------------------------------------------------------------------------


def test_default_config_is_realistic_preset() -> None:
    config = ExecutionConfig.from_params({})
    assert config.preset == "realistic"
    assert config.fill_mode == "next_open"
    assert config.slippage_pct == 0.0005
    assert config.enforce_cash is True
    assert config.allow_short is False


def test_ideal_preset_by_name_and_object() -> None:
    assert ExecutionConfig.from_params({"execution": "ideal"}).preset == "ideal"
    config = ExecutionConfig.from_params({"execution": {"preset": "ideal"}})
    assert config.fill_mode == "close"
    assert config.fees("sell", 100, 50.0).total == 0.0
    assert config.enforce_cash is False


def test_overrides_produce_custom_preset_and_round_trip() -> None:
    config = ExecutionConfig.from_params(
        {"execution": {"slippage_pct": 0.001, "commission_per_share": "0.005", "allow_short": True}}
    )
    assert config.preset == "custom"
    assert config.slippage_pct == 0.001
    assert config.commission_per_share == 0.005
    assert config.allow_short is True
    # as_dict() feeds back through from_params unchanged.
    assert ExecutionConfig.from_params({"execution": config.as_dict()}) == config


@pytest.mark.parametrize(
    "raw, message",
    [
        ({"execution": {"bogus": 1}}, "Unknown execution setting"),
        ({"execution": {"fill_mode": "midpoint"}}, "fill_mode must be one of"),
        ({"execution": {"slippage_pct": -0.1}}, "slippage_pct must be between"),
        ({"execution": {"commission_per_trade": -1}}, "cannot be negative"),
        ({"execution": {"enforce_cash": "maybe"}}, "must be true or false"),
        ({"execution": "fantasy"}, "Unknown execution preset"),
        ({"execution": 42}, "preset name or an object"),
    ],
)
def test_invalid_config_raises(raw: dict, message: str) -> None:
    with pytest.raises(ExecutionConfigError, match=message):
        ExecutionConfig.from_params(raw)


def test_regulatory_fees_apply_to_sells_only() -> None:
    config = ExecutionConfig.realistic()
    assert config.fees("buy", 100, 150.0).total == 0.0
    sell = config.fees("sell", 100, 150.0)
    # SEC: 15,000 * 27.80 / 1,000,000 = 0.417 ; FINRA TAF: 100 * 0.000166 = 0.0166
    assert sell.regulatory == pytest.approx(0.417 + 0.0166, abs=1e-6)
    assert sell.commission == 0.0


def test_finra_taf_is_capped() -> None:
    config = ExecutionConfig.realistic()
    huge = config.fees("sell", 1_000_000, 10.0)
    assert huge.regulatory == pytest.approx(10_000_000 * config.sec_fee_rate + 8.30, abs=1e-6)


def test_commission_minimum_applies_when_charging() -> None:
    config = ExecutionConfig.from_params(
        {"execution": {"commission_per_share": 0.005, "commission_min": 1.0}}
    )
    assert config.fees("buy", 10, 100.0).commission == 1.0
    assert config.fees("buy", 1000, 100.0).commission == 5.0


def test_affordable_quantity_floors_whole_shares() -> None:
    config = ExecutionConfig.realistic()
    assert config.affordable_quantity(1_000.0, 150.0, 10) == 6.0
    assert config.affordable_quantity(100.0, 150.0, 10) == 0.0
    assert config.affordable_quantity(1_000.0, 150.0, 3) == 3.0


# ---- executor -----------------------------------------------------------------------------


def test_next_open_fill_uses_following_bar_open_with_slippage() -> None:
    result = run_backtest(BuyOnce(), bars(100.0, 110.0, 120.0), params={})

    assert len(result.trades) == 1
    trade = result.trades[0]
    assert trade["timestamp"] == "2024-01-02"
    assert trade["signal_timestamp"] == "2024-01-01"
    # Bar 2 opens at 109; buys pay 0.05% more.
    assert trade["reference_price"] == 109.0
    assert trade["price"] == pytest.approx(109.0 * 1.0005)
    assert trade["slippage"] == pytest.approx(109.0 * 0.0005 * 10)
    assert result.execution["preset"] == "realistic"


def test_ideal_preset_matches_frictionless_close_fill() -> None:
    result = run_backtest(BuyOnce(), bars(100.0, 110.0, 120.0), params={"execution": "ideal"})

    trade = result.trades[0]
    assert trade["timestamp"] == "2024-01-01"
    assert trade["price"] == 100.0
    assert trade["fees"] == 0.0
    assert result.metrics["total_fees"] == 0.0
    assert result.equity_curve[-1] == pytest.approx(100_000 + 10 * 20.0)


def test_signal_on_last_bar_is_rejected_in_next_open_mode() -> None:
    class BuyOnLastBar(Strategy):
        def next(self, row, portfolio):
            if row["timestamp"] == "2024-01-03":
                return Signal(symbol=row["symbol"], side="buy", quantity=1)
            return None

    result = run_backtest(BuyOnLastBar(), bars(100.0, 110.0, 120.0), params={})

    assert result.trades == []
    assert len(result.rejected_orders) == 1
    assert "No later bar" in result.rejected_orders[0]["reason"]
    assert result.metrics["rejected_orders"] == 1


def test_sell_fees_reduce_pnl_and_cash() -> None:
    result = run_backtest(
        BuyThenSell(),
        bars(100.0, 100.0, 100.0, 100.0, 100.0),
        params={"execution": {"slippage_pct": 0.0}},
    )

    buy, sell = result.trades
    assert buy["price"] == 99.0 and sell["price"] == 99.0
    assert buy["fees"] == 0.0
    expected_sell_fees = 990.0 * ExecutionConfig.realistic().sec_fee_rate + 10 * 0.000166
    assert sell["fees"] == pytest.approx(expected_sell_fees, abs=1e-6)
    assert sell["pnl"] == pytest.approx(-expected_sell_fees, abs=1e-6)
    assert result.metrics["total_fees"] == pytest.approx(expected_sell_fees, abs=1e-6)
    assert result.equity_curve[-1] == pytest.approx(100_000 - expected_sell_fees, abs=1e-6)


def test_buy_is_shrunk_to_what_cash_allows() -> None:
    result = run_backtest(
        BuyOnce(quantity=100),
        bars(100.0, 100.0, 100.0),
        params={"execution": {"slippage_pct": 0.0}},
        initial_cash=1_000.0,
    )

    trade = result.trades[0]
    assert trade["requested_quantity"] == 100.0
    assert trade["quantity"] == 10.0
    assert result.metrics["partial_fills"] == 1
    # 10 shares bought at the 99.0 open, marked at the 100.0 close, plus 10.0 leftover cash.
    assert result.equity_curve[-1] == pytest.approx(1_010.0)


def test_buy_is_rejected_when_partial_fills_disabled() -> None:
    result = run_backtest(
        BuyOnce(quantity=100),
        bars(100.0, 100.0, 100.0),
        params={"execution": {"allow_partial_fills": False}},
        initial_cash=1_000.0,
    )

    assert result.trades == []
    assert "Insufficient cash" in result.rejected_orders[0]["reason"]


def test_selling_without_a_position_is_rejected_unless_shorting_allowed() -> None:
    rejected = run_backtest(SellWithoutPosition(), bars(100.0, 100.0), params={})
    assert rejected.trades == []
    assert "No TEST position" in rejected.rejected_orders[0]["reason"]

    shorted = run_backtest(
        SellWithoutPosition(), bars(100.0, 100.0), params={"execution": {"allow_short": True}}
    )
    assert len(shorted.trades) == 1
    assert shorted.trades[0]["side"] == "sell"


def test_oversized_sell_is_clamped_to_holdings() -> None:
    class BuyTenSellTwenty(Strategy):
        def init(self, params):
            self.step = 0

        def next(self, row, portfolio):
            self.step += 1
            if self.step == 1:
                return Signal(symbol=row["symbol"], side="buy", quantity=10)
            if self.step == 3:
                return Signal(symbol=row["symbol"], side="sell", quantity=20)
            return None

    result = run_backtest(BuyTenSellTwenty(), bars(100.0, 100.0, 100.0, 100.0), params={})

    sell = result.trades[1]
    assert sell["requested_quantity"] == 20.0
    assert sell["quantity"] == 10.0
    assert result.metrics["partial_fills"] == 1


def test_strategy_sees_filled_position_before_next_bar_signal() -> None:
    """Pending fills apply before next() so a strategy does not double-buy."""
    result = run_backtest(BuyOnce(), bars(100.0, 100.0, 100.0, 100.0), params={})
    assert len(result.trades) == 1
