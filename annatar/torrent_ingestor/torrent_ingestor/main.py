import asyncio
from os import environ
from datetime import datetime
from redis import asyncio as redis
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session

# Define SQLAlchemy model (for DB interaction)
Base = declarative_base()


# Define your Pydantic model (for validation)
class TorrentAddedEvent(BaseModel):
    info_hash: str
    title: str
    imdb: str
    indexer: str
    category: str
    season: int | None = None
    episode: int | None = None


class IngestedTorrent(Base):
    __tablename__ = "ingested_torrents"
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String)
    source = Column(String, default="Annatar Pubsub")
    category = Column(String)
    info_hash = Column(String)
    size = Column(Integer, default=0)
    seeders = Column(Integer, default=0)
    leechers = Column(Integer, default=0)
    imdb = Column(String, nullable=False)
    processed = Column(Boolean, default=False)
    createdAt = Column(DateTime, default=datetime.utcnow)
    updatedAt = Column(DateTime, default=datetime.utcnow)


async def write_to_postgres(
    session: sessionmaker[Session],
    queue: asyncio.Queue[TorrentAddedEvent],
) -> None:
    while True:
        event: TorrentAddedEvent = await queue.get()
        session().add(
            IngestedTorrent(
                name=event.title,
                info_hash=event.info_hash,
                imdb=event.imdb,
                category=event.category,
                updatedAt=datetime.utcnow(),
            )
        )
        queue.task_done()


async def redis_subscriber(
    redis_url: str, channel_name: str, queue: asyncio.Queue[TorrentAddedEvent]
) -> None:
    db = redis.from_url(redis_url)
    pubsub = db.pubsub()
    await pubsub.subscribe(channel_name)
    try:
        async for message in pubsub.listen():
            if message["type"] == "message":
                event_data = TorrentAddedEvent.model_validate(message["data"])
                await queue.put(event_data)
    finally:
        await pubsub.unsubscribe(channel_name)
        await db.close()


async def main():
    REDIS_URL = environ.get("REDIS_URL", "redis://localhost")
    if not REDIS_URL:
        raise ValueError("REDIS_URL env var is required.")

    # Database connection settings
    DATABASE_URL = environ.get("POSTGRES_URL")
    if not DATABASE_URL:
        raise ValueError("POSTGRES_URL env var is required.")
    engine = create_engine(
        DATABASE_URL, pool_size=10, max_overflow=0, pool_timeout=5, pool_recycle=3600
    )
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    # Initialize DB (create tables)
    Base.metadata.create_all(bind=engine, checkfirst=True)

    queue = asyncio.Queue[TorrentAddedEvent]()

    # Run the subscriber and the writer as concurrent tasks
    subscriber_task = asyncio.create_task(
        redis_subscriber(REDIS_URL, "events:v1:torrent:added", queue)
    )
    writer_task = asyncio.create_task(write_to_postgres(SessionLocal, queue))

    await asyncio.wait(
        [subscriber_task, writer_task], return_when=asyncio.FIRST_COMPLETED
    )


if __name__ == "__main__":
    asyncio.run(main())
