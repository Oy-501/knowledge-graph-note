"""分享空间 API：上传、列表、搜索、推荐、点赞。"""
from typing import List, Optional

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.services import share_service
from app.services.auth_service import current_user_id

router = APIRouter()


class PostIn(BaseModel):
    """上传分享的请求体。"""
    title: str
    summary: str = ""
    content: str = ""
    domain: str = "general"
    tags: List[str] = []
    node_id: Optional[int] = None
    file_id: Optional[int] = None
    user_id: int = 1


@router.post("/posts")
def create_post(payload: PostIn, request: Request, db: Session = Depends(get_db)):
    """上传一条分享：先判定，approved 才进入公共空间。"""
    uid = current_user_id(request, payload.user_id)
    return share_service.create_post(
        db, uid, payload.title, payload.summary, payload.content,
        payload.domain, payload.tags, payload.node_id, payload.file_id)


@router.get("/posts")
def list_posts(request: Request, user_id: int = 1, sort: str = "hot", q: str = "",
               domain: str = "", limit: int = 20, offset: int = 0,
               db: Session = Depends(get_db)):
    """公共列表：热门或最新，可按关键词与领域过滤。"""
    uid = current_user_id(request, user_id)
    return share_service.list_posts(db, uid, sort, q, domain, limit, offset)


@router.get("/search")
def search_posts(request: Request, user_id: int = 1, q: str = "",
                 limit: int = 20, offset: int = 0, db: Session = Depends(get_db)):
    """搜索分享：标题、摘要、领域。"""
    uid = current_user_id(request, user_id)
    return share_service.search(db, uid, q, limit, offset)


@router.get("/recommend")
def recommend_posts(request: Request, user_id: int = 1, limit: int = 12,
                    db: Session = Depends(get_db)):
    """按用户上传画像推荐高赞分享。"""
    uid = current_user_id(request, user_id)
    return share_service.recommend(db, uid, limit)


@router.post("/posts/{post_id}/like")
def like(post_id: int, request: Request, user_id: int = 1,
         db: Session = Depends(get_db)):
    """点赞：每个用户对同一条分享只能点一次。"""
    uid = current_user_id(request, user_id)
    return share_service.like_post(db, post_id, uid)


@router.delete("/posts/{post_id}/like")
def unlike(post_id: int, request: Request, user_id: int = 1,
           db: Session = Depends(get_db)):
    """取消点赞。"""
    uid = current_user_id(request, user_id)
    return share_service.unlike_post(db, post_id, uid)
