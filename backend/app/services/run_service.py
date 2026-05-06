import uuid

from sqlalchemy import asc, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.dataset import Dataset
from app.models.run import Run
from app.models.trade import Trade
from app.schemas.run import RunCreate


class DatasetRunValidationError(Exception):
    pass


def build_dataset_run_params(data: RunCreate, dataset: Dataset | None) -> dict:
    params = dict(data.params or {})
    if dataset is None:
        return params

    if not dataset.symbols:
        raise DatasetRunValidationError("Dataset must include at least one symbol")

    dataset_symbol = dataset.symbols[0]
    requested_symbol = params.get("symbol")
    requested_timeframe = params.get("timeframe")

    if requested_symbol is not None and requested_symbol not in dataset.symbols:
        raise DatasetRunValidationError(
            f"Dataset does not contain symbol {requested_symbol!s}"
        )
    if requested_timeframe is not None and requested_timeframe != dataset.timeframe:
        raise DatasetRunValidationError(
            f"Dataset timeframe is {dataset.timeframe}, not {requested_timeframe!s}"
        )

    params.setdefault("symbol", dataset_symbol)
    params.setdefault("timeframe", dataset.timeframe)
    return params


async def create_run(
    db: AsyncSession,
    data: RunCreate,
    dataset: Dataset | None = None,
) -> Run:
    params = build_dataset_run_params(data, dataset)
    run = Run(
        strategy_id=data.strategy_id,
        dataset_id=dataset.id if dataset is not None else None,
        dataset_version=dataset.checksum if dataset is not None else "",
        params=params,
        status="pending",
    )
    db.add(run)
    await db.commit()
    await db.refresh(run)
    return run


async def get_run(db: AsyncSession, run_id: uuid.UUID) -> Run | None:
    return await db.get(Run, run_id)


async def list_runs(
    db: AsyncSession,
    strategy_id: uuid.UUID | None = None,
    limit: int = 20,
    offset: int = 0,
) -> tuple[list[Run], int]:
    base = select(Run)
    count_q = select(func.count()).select_from(Run)
    if strategy_id is not None:
        base = base.where(Run.strategy_id == strategy_id)
        count_q = count_q.where(Run.strategy_id == strategy_id)
    total = await db.scalar(count_q)
    result = await db.execute(
        base.order_by(Run.created_at.desc()).limit(limit).offset(offset)
    )
    return list(result.scalars().all()), total or 0


async def get_run_trades(
    db: AsyncSession,
    run_id: uuid.UUID,
    limit: int = 100,
    offset: int = 0,
    sort_by: str = "timestamp",
    sort_dir: str = "asc",
) -> tuple[list[Trade], int]:
    count_q = select(func.count()).select_from(Trade).where(Trade.run_id == run_id)
    total = await db.scalar(count_q)
    sort_columns = {
        "timestamp": Trade.timestamp,
        "symbol": Trade.symbol,
        "side": Trade.side,
        "quantity": Trade.quantity,
        "price": Trade.price,
        "pnl": Trade.pnl,
    }
    sort_column = sort_columns.get(sort_by, Trade.timestamp)
    ordering = desc(sort_column) if sort_dir == "desc" else asc(sort_column)
    result = await db.execute(
        select(Trade)
        .where(Trade.run_id == run_id)
        .order_by(ordering, Trade.id)
        .limit(limit)
        .offset(offset)
    )
    return list(result.scalars().all()), total or 0
