import os
from sqlalchemy import create_engine, text, event
from sqlalchemy.orm import sessionmaker
from db.models import Base
from util.path import get_data_dir

data_dir = get_data_dir()
os.makedirs(data_dir, exist_ok=True)
db_path = os.path.join(data_dir, "local_client.db")

DATABASE_URL = f"sqlite:///{db_path}"
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False}
)


@event.listens_for(engine, "connect")
def enable_sqlite_foreign_keys(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def create_db_and_tables():
    Base.metadata.create_all(bind=engine)

    with engine.connect() as conn:
        try:
            conn.execute(text(
                "ALTER TABLE watched_applications ADD COLUMN is_watched BOOLEAN NOT NULL DEFAULT 1"
            ))
            conn.commit()
        except Exception:
            pass


def delete_database():
    if os.path.exists(db_path):
        os.remove(db_path)
        print(f"[Local DB] 已删除数据库文件: {db_path}")
