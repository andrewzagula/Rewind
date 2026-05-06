import uuid
from datetime import date
from types import SimpleNamespace

import pytest

from app.schemas.run import RunCreate
from app.services import run_service


def _dataset(symbol: str = "MSFT", timeframe: str = "1d") -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        symbols=[symbol],
        timeframe=timeframe,
        checksum="dataset-version",
        start_date=date(2020, 1, 1),
        end_date=date(2024, 12, 31),
    )


def test_build_dataset_run_params_defaults_symbol_and_timeframe() -> None:
    dataset = _dataset()
    data = RunCreate(strategy_id=uuid.uuid4(), dataset_id=dataset.id, params={})

    params = run_service.build_dataset_run_params(data, dataset)

    assert params["symbol"] == "MSFT"
    assert params["timeframe"] == "1d"


def test_build_dataset_run_params_rejects_wrong_symbol() -> None:
    dataset = _dataset("MSFT")
    data = RunCreate(
        strategy_id=uuid.uuid4(),
        dataset_id=dataset.id,
        params={"symbol": "AAPL"},
    )

    with pytest.raises(run_service.DatasetRunValidationError, match="Dataset does not contain"):
        run_service.build_dataset_run_params(data, dataset)


def test_build_dataset_run_params_rejects_wrong_timeframe() -> None:
    dataset = _dataset("MSFT", "1d")
    data = RunCreate(
        strategy_id=uuid.uuid4(),
        dataset_id=dataset.id,
        params={"timeframe": "1h"},
    )

    with pytest.raises(run_service.DatasetRunValidationError, match="Dataset timeframe is 1d"):
        run_service.build_dataset_run_params(data, dataset)


def test_build_dataset_run_params_rejects_empty_symbols() -> None:
    dataset = _dataset("MSFT")
    dataset.symbols = []
    data = RunCreate(strategy_id=uuid.uuid4(), dataset_id=dataset.id, params={})

    with pytest.raises(run_service.DatasetRunValidationError, match="at least one symbol"):
        run_service.build_dataset_run_params(data, dataset)
