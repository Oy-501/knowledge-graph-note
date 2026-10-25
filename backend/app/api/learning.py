"""学习提醒 API：加入复习、今日到期、提交复习。"""
from typing import Optional

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.services import learning_service
from app.services.auth_service import current_user_id

router = APIRouter()


class AddIn(BaseModel):
    """加入复习计划的请求体。"""
    node_id: Optional[int] = None
    post_id: Optional[int] = None
    title: str = ""
    user_id: int = 1


class ReviewIn(BaseModel):
    """复习自评：quality 0-5，越高表示越熟练。"""
    quality: int = 4


@router.post("/add")
def add_review(payload: AddIn, request: Request, db: Session = Depends(get_db)):
    """把一条已通过的知识加入复习计划。"""
    uid = current_user_id(request, payload.user_id)
    return learning_service.add_review(db, uid, payload.node_id, payload.post_id, payload.title)


@router.get("/due")
def due(request: Request, user_id: int = 1, limit: int = 30,
        db: Session = Depends(get_db)):
    """今日到期（含逾期）的复习项。"""
    uid = current_user_id(request, user_id)
    return learning_service.due_reviews(db, uid, limit)


@router.get("/stats")
def stats(request: Request, user_id: int = 1, db: Session = Depends(get_db)):
    """学习概览：总数 / 到期 / 已掌握。"""
    uid = current_user_id(request, user_id)
    return learning_service.stats(db, uid)


@router.post("/{review_id}/review")
def review(review_id: int, payload: ReviewIn, request: Request,
           user_id: int = 1, db: Session = Depends(get_db)):
    """提交一次复习自评，推进下次到期时间。"""
    uid = current_user_id(request, user_id)
    return learning_service.review(db, review_id, uid, payload.quality)
