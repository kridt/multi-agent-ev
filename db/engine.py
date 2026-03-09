"""SQLAlchemy engine factory."""

from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from config.settings import settings


def create_engine(url: str | None = None) -> AsyncEngine:
    db_url = url or settings.database_url
    connect_args = {}
    if db_url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
    return create_async_engine(db_url, echo=False, connect_args=connect_args)


engine = create_engine()
