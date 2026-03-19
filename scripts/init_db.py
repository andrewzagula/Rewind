"""Initialize the PostgreSQL database schema."""

import asyncio

from app.core.database import engine
from app.models import Base


async def init() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await engine.dispose()
    print("Database tables created.")


if __name__ == "__main__":
    asyncio.run(init())
