import uuid

import pytest

from app.schemas.run import RunCreate
from app.services import run_service


def test_run_params_expand_execution_defaults() -> None:
    params = run_service.build_dataset_run_params(
        RunCreate(strategy_id=uuid.uuid4(), params={"symbol": "AAPL"}), dataset=None
    )

    execution = params["execution"]
    assert execution["preset"] == "realistic"
    assert execution["fill_mode"] == "next_open"
    assert execution["slippage_pct"] == 0.0005
    assert execution["enforce_cash"] is True
    assert params["symbol"] == "AAPL"


def test_run_params_accept_ideal_preset_and_overrides() -> None:
    ideal = run_service.build_dataset_run_params(
        RunCreate(strategy_id=uuid.uuid4(), params={"execution": "ideal"}), dataset=None
    )
    assert ideal["execution"]["preset"] == "ideal"
    assert ideal["execution"]["fill_mode"] == "close"

    custom = run_service.build_dataset_run_params(
        RunCreate(
            strategy_id=uuid.uuid4(),
            params={"execution": {"slippage_pct": 0.002, "allow_short": True}},
        ),
        dataset=None,
    )
    assert custom["execution"]["preset"] == "custom"
    assert custom["execution"]["slippage_pct"] == 0.002
    assert custom["execution"]["allow_short"] is True


def test_run_params_reject_invalid_execution() -> None:
    with pytest.raises(run_service.DatasetRunValidationError, match="Unknown execution setting"):
        run_service.build_dataset_run_params(
            RunCreate(strategy_id=uuid.uuid4(), params={"execution": {"nope": 1}}), dataset=None
        )
