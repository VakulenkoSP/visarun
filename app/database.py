from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase
from .config import DATABASE_URL

engine = create_async_engine(DATABASE_URL, echo=False)
async_session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def init_db():
    from . import models
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with engine.begin() as conn:
        def migrate(sync_conn):
            import sqlalchemy as sa
            inspector = sa.inspect(sync_conn)
            if "bookings" in inspector.get_table_names():
                cols = [c["name"] for c in inspector.get_columns("bookings")]
                if "payment_method" not in cols:
                    sync_conn.execute(sa.text("ALTER TABLE bookings ADD COLUMN payment_method VARCHAR(30)"))
                if "payment_details" not in cols:
                    sync_conn.execute(sa.text("ALTER TABLE bookings ADD COLUMN payment_details VARCHAR(500)"))
                if "pending_add_amount" not in cols:
                    sync_conn.execute(sa.text("ALTER TABLE bookings ADD COLUMN pending_add_amount INTEGER"))
                if "pending_add_people" not in cols:
                    sync_conn.execute(sa.text("ALTER TABLE bookings ADD COLUMN pending_add_people INTEGER"))
                if "selected_seats" not in cols:
                    sync_conn.execute(sa.text("ALTER TABLE bookings ADD COLUMN selected_seats VARCHAR(500)"))
                if "payment_comment" not in cols:
                    sync_conn.execute(sa.text("ALTER TABLE bookings ADD COLUMN payment_comment VARCHAR(255)"))
            if "users" in inspector.get_table_names():
                user_cols = [c["name"] for c in inspector.get_columns("users")]
                if "full_name" not in user_cols:
                    sync_conn.execute(sa.text("ALTER TABLE users ADD COLUMN full_name VARCHAR(255)"))
            if "trips" in inspector.get_table_names():
                trip_cols = [c["name"] for c in inspector.get_columns("trips")]
                if "departure_time" not in trip_cols:
                    sync_conn.execute(sa.text("ALTER TABLE trips ADD COLUMN departure_time VARCHAR(5)"))
                if "bus_type" not in trip_cols:
                    sync_conn.execute(sa.text("ALTER TABLE trips ADD COLUMN bus_type VARCHAR(10) DEFAULT 'vip' NOT NULL"))
                if "seats_left" not in trip_cols:
                    sync_conn.execute(sa.text("ALTER TABLE trips ADD COLUMN seats_left INTEGER DEFAULT 20 NOT NULL"))
                if "seats_middle" not in trip_cols:
                    sync_conn.execute(sa.text("ALTER TABLE trips ADD COLUMN seats_middle INTEGER DEFAULT 0 NOT NULL"))
                if "seats_right" not in trip_cols:
                    sync_conn.execute(sa.text("ALTER TABLE trips ADD COLUMN seats_right INTEGER DEFAULT 20 NOT NULL"))
                for col in ["bus_type", "seats_left", "seats_middle", "seats_right"]:
                    if col not in trip_cols:
                        pass
        await conn.run_sync(migrate)



