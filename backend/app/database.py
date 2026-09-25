"""数据库连接与Session管理

双模式：PostgreSQL（可配 pgvector） / SQLite（JSON 文本存向量）。
由 app.config.Settings.resolved_database_url 自动决策。
"""
import os

from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.orm import sessionmaker, declarative_base

from app.config import settings

_DB_URL = settings.resolved_database_url
_IS_SQLITE = settings.db_is_sqlite

# SQLite 相对路径落库前，确保所在目录存在
if _IS_SQLITE and _DB_URL.startswith("sqlite:///"):
    db_file = _DB_URL.replace("sqlite:///", "", 1)
    if not db_file.startswith("/") and ":" not in db_file[:2]:
        db_dir = os.path.dirname(os.path.abspath(db_file))
        os.makedirs(db_dir, exist_ok=True)

engine = create_engine(
    _DB_URL,
    connect_args={"check_same_thread": False} if _IS_SQLITE else {},
    echo=False,  # SQL 回显量大，需要排查时改 True
    pool_pre_ping=True,
)

if _IS_SQLITE:
    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    """依赖注入：获取数据库会话"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """初始化所有表，并做轻量 schema 演进"""
    Base.metadata.create_all(bind=engine)
    _migrate()


# 列级迁移清单：表名 -> [(列名, ALTER 片段)]。create_all 不会修改已存在的表，
# 历史库通过这里补列（SQLite / PostgreSQL 通用，缺列判定走 inspector）。
_COLUMN_MIGRATIONS = {
    "files": [
        ("source_path", "ALTER TABLE files ADD COLUMN source_path VARCHAR(255)"),
        ("parse_note", "ALTER TABLE files ADD COLUMN parse_note VARCHAR(255)"),
    ],
    "notes": [
        ("validation_report", "ALTER TABLE notes ADD COLUMN validation_report JSON"),
    ],
    "nodes": [
        ("chunk_index", "ALTER TABLE nodes ADD COLUMN chunk_index INTEGER DEFAULT 0"),
    ],
}


def _migrate():
    """幂等列迁移：对已存在的表检查缺列并 ALTER TABLE 补齐"""
    try:
        insp = inspect(engine)
        existing_tables = set(insp.get_table_names())
    except Exception:
        return
    for table, adds in _COLUMN_MIGRATIONS.items():
        if table not in existing_tables:
            continue
        cols = {c["name"] for c in insp.get_columns(table)}
        stmts = [sql for col, sql in adds if col not in cols]
        if not stmts:
            continue
        with engine.begin() as conn:
            for sql in stmts:
                conn.execute(text(sql))
