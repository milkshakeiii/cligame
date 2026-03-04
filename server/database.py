from sqlmodel import SQLModel
from sqlalchemy.ext.asyncio import create_async_engine
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlalchemy.orm import sessionmaker
from server.config import settings

engine = create_async_engine(settings.database_url, echo=False)

async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def init_db(*, drop_all: bool = False):
    async with engine.begin() as conn:
        if drop_all:
            await conn.run_sync(SQLModel.metadata.drop_all)
        await conn.run_sync(SQLModel.metadata.create_all)


async def get_session():
    async with async_session() as session:
        yield session
