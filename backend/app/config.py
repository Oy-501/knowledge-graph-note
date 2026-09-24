"""应用配置（双模式数据库自动探测）

数据库选型规则（DB_MODE）：
  - "auto"     （默认）启动时探测 PostgreSQL，不可达则回落 SQLite —— 开箱即用
  - "postgres"  强制使用 PostgreSQL（探测失败直接报错，便于 docker-compose 场景）
  - "sqlite"    强制使用 SQLite

优先级：显式设置 DATABASE_URL > DB_MODE 规则 > 自动探测结果。
"""
import os
import socket
from typing import List

from pydantic_settings import BaseSettings


def _pg_reachable(host: str, port: int, timeout: float = 1.2) -> bool:
    """探测 PostgreSQL 是否可达（纯 TCP 握手，无需驱动）"""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


class Settings(BaseSettings):
    # ---- Database ----
    DATABASE_URL: str = ""
    DB_MODE: str = "auto"  # auto | postgres | sqlite

    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_USER: str = "kg_user"
    POSTGRES_PASSWORD: str = "kg_pass"
    POSTGRES_DB: str = "knowledge_graph"

    SQLITE_PATH: str = "./kg.db"

    # ---- Server ----
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    DEBUG: bool = False

    CORS_ORIGINS: str = "http://localhost:5173,http://127.0.0.1:5173,http://localhost:3000"

    # ---- Vector Engine ----
    VECTOR_DIM: int = 768
    VECTOR_MODEL: str = "all-MiniLM-L6-v2"

    # ---- Knowledge Base ----
    KNOWLEDGE_SEED_PATH: str = ""

    # ---- Scoring defaults ----
    DEFAULT_ALPHA: float = 0.15
    DEFAULT_BETA: float = 0.25
    DEFAULT_GAMMA: float = 0.50
    DEFAULT_DELTA: float = 0.10
    DEFAULT_THRESHOLD: float = 0.15

    @property
    def cors_origins_list(self) -> List[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    @property
    def resolved_database_url(self) -> str:
        """决策最终数据库连接串"""
        if self.DATABASE_URL:
            return self.DATABASE_URL
        mode = self.DB_MODE.lower()
        if mode in ("auto", "postgres"):
            if _pg_reachable(self.POSTGRES_HOST, self.POSTGRES_PORT):
                return (
                    f"postgresql://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
                    f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
                )
            if mode == "postgres":
                raise RuntimeError(
                    f"PostgreSQL 不可达（{self.POSTGRES_HOST}:{self.POSTGRES_PORT}），"
                    f"但 DB_MODE=postgres 强制要求使用 PostgreSQL。"
                    f"请先 docker compose up -d db，或改 DB_MODE=auto/sqlite。"
                )
        return f"sqlite:///{self.SQLITE_PATH}"

    @property
    def db_is_sqlite(self) -> bool:
        return self.resolved_database_url.startswith("sqlite")

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
