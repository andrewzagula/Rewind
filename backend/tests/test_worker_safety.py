import pytest

try:
    from worker import DATA_DIR, execute_backtest_with_timeout
except ModuleNotFoundError:
    from backend.worker import DATA_DIR, execute_backtest_with_timeout


VALID_STRATEGY_CODE = """from engine import Signal, Strategy


class BuyOnceStrategy(Strategy):
    def init(self, params: dict) -> None:
        self.has_bought = False

    def next(self, row: dict, portfolio) -> Signal | None:
        if not self.has_bought:
            self.has_bought = True
            return Signal(symbol=row["symbol"], side="buy", quantity=1)
        return None
"""

INFINITE_STRATEGY_CODE = """from engine import Strategy


class InfiniteStrategy(Strategy):
    def init(self, params: dict) -> None:
        pass

    def next(self, row: dict, portfolio):
        while True:
            pass
"""


def test_execute_backtest_with_timeout_returns_payload_for_valid_strategy() -> None:
    result = execute_backtest_with_timeout(
        strategy_code=VALID_STRATEGY_CODE,
        params={"symbol": "AAPL"},
        symbol="AAPL",
        timeframe="1d",
        initial_cash=100_000.0,
        data_dir=DATA_DIR,
        timeout_seconds=5,
    )

    assert result["metrics"]
    assert result["equity_curve"]
    assert result["equity_points"]
    assert len(result["trades"]) == 1


def test_execute_backtest_with_timeout_terminates_long_running_strategy() -> None:
    with pytest.raises(
        TimeoutError,
        match="Strategy execution timed out after 0.2 seconds",
    ):
        execute_backtest_with_timeout(
            strategy_code=INFINITE_STRATEGY_CODE,
            params={"symbol": "AAPL"},
            symbol="AAPL",
            timeframe="1d",
            initial_cash=100_000.0,
            data_dir=DATA_DIR,
            timeout_seconds=0.2,
        )


def test_execute_backtest_with_timeout_uses_explicit_dataset_file_path() -> None:
    result = execute_backtest_with_timeout(
        strategy_code=VALID_STRATEGY_CODE,
        params={"symbol": "MSFT"},
        symbol="MSFT",
        timeframe="1d",
        initial_cash=100_000.0,
        data_dir=DATA_DIR,
        data_file_path=DATA_DIR / "MSFT_1d.parquet",
        timeout_seconds=5,
    )

    assert result["metrics"]
    assert result["trades"][0]["symbol"] == "MSFT"
