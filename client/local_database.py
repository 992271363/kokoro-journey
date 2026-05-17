import os
from sqlalchemy import create_engine, text, event
from sqlalchemy.orm import sessionmaker
from local_models import Base
from data_dir import get_data_dir

data_dir = get_data_dir()
os.makedirs(data_dir, exist_ok=True)
db_path = os.path.join(data_dir, "local_client.db")

# DATABASE_URL 格式 (SQLite)
DATABASE_URL = f"sqlite:///{db_path}"
# 创建数据库引擎
# connect_args 是 SQLite 多线程使用的重要参数
engine = create_engine(
    DATABASE_URL, 
    connect_args={"check_same_thread": False}
)


@event.listens_for(engine, "connect")
def enable_sqlite_foreign_keys(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()

#创建数据库会话
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

#创建数据库表
def create_db_and_tables():
    """
    在应用首次启动时调用，用于创建数据库文件和所有表。
    """
    Base.metadata.create_all(bind=engine)

    # 增量迁移：给已有表添加新列（如果不存在）
    with engine.connect() as conn:
        try:
            conn.execute(text(
                "ALTER TABLE watched_applications ADD COLUMN is_watched BOOLEAN NOT NULL DEFAULT 1"
            ))
            conn.commit()
        except Exception:
            pass  # 列已存在则跳过


def delete_database():
    """删除本地数据库文件（用于数据库损坏时重置）。"""
    if os.path.exists(db_path):
        os.remove(db_path)
        print(f"[Local DB] 已删除数据库文件: {db_path}")

