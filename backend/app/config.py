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


# backend/ 目录的绝对路径。所有相对路径（数据库、.env）都以此为基准，
# 避免"结果取决于从哪个目录启动"这类隐蔽问题。
BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _pg_reachable(host: str, port: int, timeout: float = 1.2) -> bool:
    """探测 PostgreSQL 是否可达（纯 TCP 握手，无需驱动）"""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


class Settings(BaseSettings):
    # ---- Database ----
    # 显式连接串（如 postgresql://user:pass@host:5432/kg），为空则由 DB_MODE 决策
    DATABASE_URL: str = ""
    DB_MODE: str = "auto"  # auto | postgres | sqlite

    # PostgreSQL 探测参数（仅 DB_MODE=auto 或 postgres 时使用）
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_USER: str = "kg_user"
    POSTGRES_PASSWORD: str = "kg_pass"
    POSTGRES_DB: str = "knowledge_graph"

    # SQLite 兜底文件
    SQLITE_PATH: str = "./kg.db"

    # ---- Server ----
    HOST: str = "127.0.0.1"   # 默认只绑本机回环，避免无意中暴露到局域网（需外部访问再显式改 0.0.0.0）
    PORT: int = 8000
    DEBUG: bool = False

    # ---- CORS ----
    CORS_ORIGINS: str = "http://localhost:5173,http://127.0.0.1:5173,http://localhost:3000"

    # ---- Vector Engine（语义向量，决定 inference 的 β 维）----
    # 模型必须支持中文：本项目知识库是中文语料，all-MiniLM-L6-v2 是纯英文模型，
    # 拿它编码中文等于随机向量。多语模型同时对英文基准语料（graphrag_bench）可用。
    VECTOR_MODEL: str = "paraphrase-multilingual-MiniLM-L12-v2"
    VECTOR_CACHE_DIR: str = "./models"          # 模型权重缓存（相对 backend/，可离线复用）
    VECTOR_BACKEND: str = "auto"                # auto | transformers | tfidf（tfidf 用于强制验证降级路径）
    # huggingface.co 在部分网络下不可达；hf-mirror.com 是可用镜像。留空则不改环境变量。
    HF_ENDPOINT: str = "https://hf-mirror.com"
    HF_HUB_OFFLINE: bool = False                # 模型已下载好、要断网运行就置 True

    # ---- Knowledge Base ----
    KNOWLEDGE_SEED_PATH: str = ""

    # ---- 上传与解析上限（防止大文件把服务拖死：内存 / O(n²) 关联 / 前端渲染）----
    MAX_PARSE_LINES: int = 20000       # 单个文件最多解析的行数
    MAX_NODES_PER_FILE: int = 600      # 单个文件（单片）最多抽取的知识点数量
    MAX_NODES_PER_FILE_TOTAL: int = 3000  # 一个文件切割后允许的知识点总量上限
    MAX_LINK_CANDIDATES: int = 300     # 每个新节点最多比较的既有节点数（超出则按关键词交集剪枝）
    LINK_PAIR_BUDGET: int = 120000     # 单次关联推理的最大节点对数
    LINK_TIME_BUDGET_S: float = 20.0   # 单次关联推理的时间上限（秒）
    MAX_LINKS_PER_NODE: int = 8        # 每个新节点最多保留的连线数（按分数取前 N，避免连线爆炸）
    LINK_OUTPUT_LIMIT: int = 4000      # 单次关联推理最多产出的连线数
    MAX_NODES_FOR_KB_LINK: int = 4000  # 知识锚定连线最多处理的节点数

    # ---- 智能切割（大文件不再拒绝，改为按结构切分后逐片解析）----
    SPLIT_TARGET_LINES: int = 6000      # 单片目标行数（切分阈值也是它）
    SPLIT_TARGET_CHARS: int = 1_200_000  # 单片目标字符数（≈1.1MB 纯文本计量）
    SPLIT_MAX_PIECES: int = 40          # 单文件最多切多少片（防呆）
    SPLIT_OVERLAP_LINES: int = 2        # 相邻片重叠行数（保住跨界的句子）
    MAX_UPLOAD_MB_HARD: int = 100       # 硬上限：超过直接拒绝（切割也没意义）

    # ---- 知识点智能判定 ----
    VERDICT_AUTO_ACCEPT: float = 0.80   # ≥ 该分数且无冲突 → 自动入知识库
    VERDICT_REJECT_BELOW: float = 0.35  # < 该分数 → 自动驳回
    VERDICT_USE_WEB: bool = True        # 是否启用联网判定（抓不到会自动降级并标注）
    VERDICT_WEB_TIMEOUT: float = 6.0    # 单次联网抓取超时（秒）
    VERDICT_WEB_CACHE_TTL: int = 900    # 搜索结果缓存（秒）
    VERDICT_MAX_WEB_CALLS: int = 30     # 单批判定最多联网几次（避免整批卡住）

    # ---- 认证与会话 ----
    SESSION_TTL_DAYS: int = 7           # 会话有效期（天）；每次鉴权命中滑动续期
    # 是否开放注册入口（登录页会出现「注册」页签）。
    # 默认关闭：这是单机个人应用，多一个可自助注册的入口就多一份暴露面；
    # 需要新账号时把这里改成 True 重启，或直接在数据库里手工建号。
    REGISTRATION_OPEN: bool = False

    # ---- 安全开关（默认按「默认安全」原则取最严值）----
    # 写操作（POST/PUT/PATCH/DELETE）是否必须携带有效登录会话。
    # 关闭后任意能访问端口的人都能删知识库条目、重建知识库 —— 仅在本机
    # 单人调试且明确知情时才建议关闭。
    PROTECT_WRITES: bool = True
    # ⚠ 兼容保留的管理口令：写操作现在主要用**登录会话**（X-Session-Token），
    # 这个口令留给脚本与 curl 作为第二通道（X-Admin-Token），
    # 日常使用登录页就不再需要它了。留着请改成强口令，不用可以置空。
    ADMIN_TOKEN: str = "kg-admin"
    UPLOAD_DIR: str = "./uploads"       # 头像/背景图等用户上传文件目录
    MAX_IMAGE_MB: int = 5               # 图片上传上限
    AUDIT_KEEP_ROWS: int = 20000        # 审计日志保留条数（超出清理最旧的）

    # ---- 相册与媒体 ----
    MAX_MEDIA_MB: int = 500             # 单个媒体文件上限（流式限额读取）
    MEDIA_QUOTA_MB: int = 2048          # 每用户媒体总配额
    VIDEO_TRANSCODE_MB: int = 50        # 超过该大小的视频触发 720p 转码
    FFMPEG_PATH: str = ""               # ffmpeg 可执行文件路径；留空按 PATH 与常见目录自动探测

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
        # 1) 显式覆盖
        if self.DATABASE_URL:
            return self.DATABASE_URL

        mode = self.DB_MODE.lower()

        # 2) 强制 / 自动探测 PostgreSQL
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

        # 3) SQLite 兜底
        return f"sqlite:///{self.resolved_sqlite_path}"

    @property
    def db_is_sqlite(self) -> bool:
        return self.resolved_database_url.startswith("sqlite")

    @property
    def resolved_upload_dir(self) -> str:
        """上传目录的**绝对路径**（单一事实来源）。

        此前 main.py / profile.py / system.py 各自用 dirname(dirname(__file__))
        推算相对路径，因文件所在层级不同（app/ 与 app/api/）算出了两个目录
        （backend/uploads 与 backend/app/uploads），会出现「图片存到 A 处、
        静态服务却挂在 B 处」→ 上传成功但访问 404。统一从这里取，base 固定 backend/。
        """
        root = self.UPLOAD_DIR
        if os.path.isabs(root):
            return root
        return os.path.join(BACKEND_DIR, root.lstrip("./"))

    @property
    def resolved_model_dir(self) -> str:
        """向量模型缓存目录的**绝对路径**（与 upload_dir 同理，不让 cwd 参与决策）"""
        root = self.VECTOR_CACHE_DIR
        if os.path.isabs(root):
            return root
        return os.path.join(BACKEND_DIR, root.lstrip("./"))

    @property
    def resolved_sqlite_path(self) -> str:
        """SQLite 文件的**绝对路径**（相对路径按 backend/ 解析，而不是当前工作目录）。

        为什么必须绝对化：SQLITE_PATH 默认是 "./kg.db"，若按 cwd 解析，
        从项目根目录跑一次脚本就会在根目录另开一个 kg.db（甚至是空库）。
        真出过这事：在根目录跑体检，静默生成了一个 0 字节的 kg.db，
        体检随即报「缺表：users、files…」——看起来像数据全丢了，
        实际只是连错了库。若后端哪天也从根目录启动，那就是真的读到空库。
        与 resolved_upload_dir 同理：路径只在一处解析，别让 cwd 参与决策。
        """
        path = self.SQLITE_PATH
        if os.path.isabs(path):
            return path
        return os.path.join(BACKEND_DIR, path.lstrip("./"))

    class Config:
        # 用绝对路径指向 backend/.env：否则从其他目录启动时读不到配置，
        # 会静默退回默认值（例如口令变成默认的 kg-admin）
        env_file = os.path.join(BACKEND_DIR, ".env")
        env_file_encoding = "utf-8"


settings = Settings()
