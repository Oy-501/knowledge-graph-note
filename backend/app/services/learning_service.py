"""学习提醒：SM-2 简化调度。

间隔推进：
  quality < 3（没记住）→ 间隔重置为 1 天，ease 下调；
  quality >= 3         → 1 天 → 3 天 → 6 天 → 之后按 ease 递增。
"""
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from app.models.models import LearningReview, Node, SharedPost
from app.services.errors import AppError


def next_interval(interval: int, ease: float, quality: int) -> tuple:
    """返回 (新间隔天数, 新 ease)。"""
    quality = max(0, min(5, int(quality)))
    if quality < 3:
        return 1, max(1.3, ease - 0.2)
    new_ease = ease + (0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02))
    new_ease = max(1.3, new_ease)
    if interval <= 1:
        return (1 if quality < 4 else 3), new_ease
    if interval == 3:
        return 6, new_ease
    return max(1, round(interval * new_ease)), new_ease


def add_review(db: Session, user_id: int, node_id: Optional[int] = None,
               post_id: Optional[int] = None, title: str = "") -> Dict:
    """把一条知识加入复习计划；已存在则直接返回。"""
    if not node_id and not post_id:
        raise AppError("需要 node_id 或 post_id", status_code=422, code="invalid_target")

    existing = db.query(LearningReview).filter_by(
        user_id=user_id, node_id=node_id, post_id=post_id).first()
    if existing:
        return _brief(existing, already=True)

    if not title:
        if node_id:
            node = db.query(Node).filter_by(id=node_id).first()
            title = (node.title or node.entity) if node else ""
        elif post_id:
            post = db.query(SharedPost).filter_by(id=post_id).first()
            title = post.title if post else ""

    row = LearningReview(
        user_id=user_id, node_id=node_id, post_id=post_id,
        title=(title or "")[:200], due_at=datetime.utcnow())
    db.add(row)
    db.commit()
    db.refresh(row)
    return _brief(row, already=False)


def due_reviews(db: Session, user_id: int, limit: int = 30) -> Dict:
    """今日到期（含已逾期）的复习项。"""
    now = datetime.utcnow()
    rows = (db.query(LearningReview)
            .filter(LearningReview.user_id == user_id, LearningReview.due_at <= now)
            .order_by(LearningReview.due_at.asc())
            .limit(max(1, min(int(limit), 100))).all())
    total = (db.query(LearningReview)
             .filter(LearningReview.user_id == user_id).count())
    return {"items": [_brief(r) for r in rows], "due": len(rows), "total": total}


def stats(db: Session, user_id: int) -> Dict:
    """学习概览：总数 / 今日到期 / 已掌握。"""
    now = datetime.utcnow()
    rows = db.query(LearningReview).filter_by(user_id=user_id).all()
    due = [r for r in rows if r.due_at and r.due_at <= now]
    mastered = [r for r in rows if (r.review_count or 0) >= 3 and (r.interval_days or 0) >= 21]
    return {"total": len(rows), "due": len(due), "mastered": len(mastered)}


def review(db: Session, review_id: int, user_id: int, quality: int) -> Dict:
    """提交一次复习自评，推进下次到期时间。"""
    row = db.query(LearningReview).filter_by(id=review_id, user_id=user_id).first()
    if not row:
        raise AppError("复习项不存在", status_code=404, code="not_found")

    interval, ease = next_interval(row.interval_days or 1, row.ease or 2.5, quality)
    row.interval_days = interval
    row.ease = ease
    row.review_count = (row.review_count or 0) + 1
    row.last_reviewed_at = datetime.utcnow()
    row.due_at = datetime.utcnow() + timedelta(days=interval)
    db.commit()
    db.refresh(row)
    return _brief(row)


def _brief(row: LearningReview, already: bool = False) -> Dict:
    return {
        "id": row.id,
        "node_id": row.node_id,
        "post_id": row.post_id,
        "title": row.title,
        "interval_days": row.interval_days,
        "ease": round(row.ease or 2.5, 2),
        "review_count": row.review_count,
        "due_at": row.due_at.isoformat(timespec="seconds") if row.due_at else "",
        "last_reviewed_at": (row.last_reviewed_at.isoformat(timespec="seconds")
                             if row.last_reviewed_at else ""),
        "already": already,
    }
