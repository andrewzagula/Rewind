import uuid
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.dataset import Dataset


async def get_dataset(db: AsyncSession, dataset_id: uuid.UUID) -> Dataset | None:
    return await db.get(Dataset, dataset_id)


async def list_datasets(
    db: AsyncSession,
    limit: int = 100,
    offset: int = 0,
) -> tuple[list[Dataset], int]:
    total = await db.scalar(select(func.count()).select_from(Dataset))
    result = await db.execute(
        select(Dataset).order_by(Dataset.name.asc()).limit(limit).offset(offset)
    )
    return list(result.scalars().all()), total or 0


def resolve_dataset_path(file_path: str) -> Path:
    path = Path(file_path)
    if path.is_absolute():
        return path

    current = Path(__file__).resolve()
    candidates = [
        Path.cwd(),
        Path.cwd().parent,
        current.parents[3],
        current.parents[4] if len(current.parents) > 4 else current.parents[3],
    ]
    for candidate in candidates:
        resolved = candidate / path
        if resolved.exists():
            return resolved

    return current.parents[3] / path
