"""FastAPI 应用入口"""
import sys
import os

# 确保 backend 目录在 Python 路径中
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from loguru import logger

from app.config import settings
from app.database import init_db, get_db
from app.seed import ensure_default_user, seed_knowledge_base
from app.services.kb_index import build_relations_from_entries
from app.api import files, knowledge, graph, notes, kb


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    logger.info(f"Starting Knowledge Graph API... (DB: {settings.resolved_database_url.split('://')[0]})")
    init_db()

    # 幂等引导：默认用户 + 种子知识库（L0）+ 知识库关系边（本体）
    db = next(get_db())
    try:
        ensure_default_user(db)
        seed_result = seed_knowledge_base(db)
        logger.info(f"Seed knowledge base: {seed_result}")
        rel_result = build_relations_from_entries(db)
        logger.info(f"KB relations: {rel_result}")
    finally:
        db.close()

    logger.info("Database initialized.")
    yield
    logger.info("Shutting down...")


app = FastAPI(
    title="Knowledge Graph API",
    description="知识图谱笔记系统后端服务",
    version="1.0.0",
    lifespan=lifespan
)

# CORS 中间件
# 显式清单之外，再放行本机任意端口 —— 前端 vite dev server 在 5173 被占用时会自动换端口
# （5174/5175…），固定白名单会导致换端口后接口全被浏览器拦截。
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(files.router, prefix="/api/files", tags=["Files"])
app.include_router(knowledge.router, prefix="/api/knowledge", tags=["Knowledge"])
app.include_router(graph.router, prefix="/api/graph", tags=["Graph"])
app.include_router(notes.router, prefix="/api/notes", tags=["Notes"])
app.include_router(kb.router, prefix="/api/kb", tags=["KnowledgeBase"])


@app.get("/api/health")
async def health_check():
    return {"status": "ok", "version": "1.0.0"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host=settings.HOST, port=settings.PORT, reload=settings.DEBUG)