"""分享空间：上传判定、热门列表、搜索、推荐与点赞。

设计要点：
  1. 上传先判定：质量分 >= 0.6 直接 approved，否则 pending（只对作者可见，等人工审核）。
  2. 点赞幂等：唯一约束 + 应用层查重，重复点赞不重复计数。
  3. 推荐可解释：热度 / 领域亲和 / 新鲜度三项加权，返回 reason 供前端展示。
"""
import math
import re
from collections import Counter
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.models import PostLike, SharedPost
from app.services.errors import AppError, clamp_paging, escape_like

_INDEX_HEAD = re.compile(r"^\s*(?:\d+[.、)]|[（(]\d+[)）]|[一二三四五六七八九十]+、)")
_DEF_WORDS = re.compile(r"(是指|指的是|表示|包括|由.+组成|用于|属于|是一种)")


def judge_post(title: str, summary: str, content: str) -> Tuple[str, float, str]:
    """轻量质量判定：决定直接进公共空间还是先挂起等审核。"""
    title = (title or "").strip()
    body = f"{summary or ''}\n{content or ''}".strip()
    score = 0.0
    reasons: List[str] = []

    if 4 <= len(title) <= 60 and not _INDEX_HEAD.match(title):
        score += 0.3
        reasons.append("标题形态正常")
    else:
        reasons.append("标题过短、过长或像编号")

    if len(body) >= 30:
        score += 0.3
        reasons.append("正文有实质内容")
    if _DEF_WORDS.search(body):
        score += 0.2
        reasons.append("含定义性表述")
    if len(body) >= 120:
        score += 0.2
        reasons.append("内容较完整")

    status = "approved" if score >= 0.6 else "pending"
    return status, round(score, 2), "；".join(reasons)


def _systems(db: Session, file_ids: List[Optional[int]]) -> Dict[int, Dict]:
    """批量取分享对应知识体系的规模与知识点标题。

    一个分享不是单个名词，而是一份文档解析出的节点集合（file_id）。
    这里返回节点数、内部连线数与前 8 个知识点标题，供卡片直接展示体系。
    """
    from app.models.models import Link, Node

    uniq = sorted({f for f in file_ids if f})
    if not uniq:
        return {}

    rows = db.query(Node.id, Node.title, Node.entity, Node.file_id).filter(
        Node.file_id.in_(uniq)).all()
    by_file: Dict[int, List] = {}
    for row in rows:
        by_file.setdefault(row.file_id, []).append(row)

    out: Dict[int, Dict] = {}
    for fid, nodes in by_file.items():
        ids = [n.id for n in nodes]
        links = db.query(func.count(Link.id)).filter(
            Link.source_id.in_(ids), Link.target_id.in_(ids)).scalar() or 0
        out[fid] = {
            "node_count": len(nodes),
            "link_count": links,
            "node_titles": [(n.title or n.entity or "") for n in nodes][:8],
        }
    return out


def post_brief(post: SharedPost, liked: bool = False, author: Optional[str] = None,
               system: Optional[Dict] = None) -> Dict:
    """分享卡片的统一序列化。"""
    system = system or {}
    return {
        "id": post.id,
        "title": post.title,
        "summary": post.summary or "",
        "content": post.content or "",
        "domain": post.domain or "general",
        "tags": post.tags or [],
        "status": post.status,
        "like_count": post.like_count or 0,
        "liked": liked,
        "author": author or f"用户 {post.user_id}",
        "node_id": post.node_id,
        "file_id": post.file_id,
        "node_count": system.get("node_count", 0),
        "link_count": system.get("link_count", 0),
        "node_titles": system.get("node_titles", []),
        "verdict_score": post.verdict_score or 0.0,
        "created_at": post.created_at.isoformat(timespec="seconds") if post.created_at else "",
    }


def _liked_ids(db: Session, user_id: int) -> set:
    rows = db.query(PostLike.post_id).filter(PostLike.user_id == user_id).all()
    return {pid for (pid,) in rows}


def _authors(db: Session, posts: List[SharedPost]) -> Dict[int, str]:
    from app.models.models import User

    ids = {p.user_id for p in posts}
    if not ids:
        return {}
    rows = db.query(User.id, User.username).filter(User.id.in_(ids)).all()
    return {uid: name for uid, name in rows}


def create_post(db: Session, user_id: int, title: str, summary: str, content: str,
                domain: str = "general", tags: Optional[List[str]] = None,
                node_id: Optional[int] = None, file_id: Optional[int] = None) -> Dict:
    """创建分享：先判定，再落库。"""
    title = (title or "").strip()
    if len(title) < 2:
        raise AppError("标题至少 2 个字", status_code=422, code="invalid_title")

    status, score, reason = judge_post(title, summary, content)
    post = SharedPost(
        user_id=user_id,
        title=title[:200],
        summary=(summary or "")[:2000],
        content=content or "",
        domain=(domain or "general")[:60],
        tags=tags or [],
        node_id=node_id,
        file_id=file_id,
        status=status,
        verdict_score=score,
        verdict_reason=reason,
    )
    db.add(post)
    db.commit()
    db.refresh(post)

    # 通过判定的内容自动进入作者的学习计划（到期提醒回看）
    if status == "approved":
        from app.services.learning_service import add_review
        try:
            add_review(db, user_id, post_id=post.id, title=title)
        except Exception:  # noqa: BLE001 — 复习计划失败不影响分享本身
            db.rollback()

    return post_brief(post, liked=False,
                      system=_systems(db, [post.file_id]).get(post.file_id))


def list_posts(db: Session, viewer_id: int, sort: str = "hot", q: str = "",
               domain: str = "", limit: int = 20, offset: int = 0,
               include_mine: bool = True) -> Dict:
    """公共列表：approved 对所有人可见，自己的 pending 也返回（标状态）。"""
    limit, offset = clamp_paging(limit, offset)
    query = db.query(SharedPost)

    if q:
        like = f"%{escape_like(q)}%"
        query = query.filter(or_(
            SharedPost.title.ilike(like, escape="\\"),
            SharedPost.summary.ilike(like, escape="\\"),
            SharedPost.domain.ilike(like, escape="\\"),
        ))
    if domain:
        query = query.filter(SharedPost.domain == domain)

    if include_mine:
        query = query.filter(or_(
            SharedPost.status == "approved",
            SharedPost.user_id == viewer_id,
        ))
    else:
        query = query.filter(SharedPost.status == "approved")

    total = query.count()
    if sort == "new":
        query = query.order_by(SharedPost.created_at.desc())
    else:
        query = query.order_by(SharedPost.like_count.desc(), SharedPost.created_at.desc())

    rows = query.offset(offset).limit(limit).all()
    liked = _liked_ids(db, viewer_id)
    authors = _authors(db, rows)
    systems = _systems(db, [p.file_id for p in rows])
    return {
        "total": total,
        "items": [post_brief(p, p.id in liked, authors.get(p.user_id), systems.get(p.file_id))
                  for p in rows],
    }


def recommend(db: Session, user_id: int, limit: int = 12) -> Dict:
    """按用户已上传内容的领域画像，推荐高赞且未点赞的分享。"""
    limit, _ = clamp_paging(limit, 0, max_limit=50)

    my_domains = [d for (d,) in db.query(SharedPost.domain)
                  .filter(SharedPost.user_id == user_id).all() if d]
    affinity = Counter(my_domains)
    liked = _liked_ids(db, user_id)

    query = db.query(SharedPost).filter(
        SharedPost.status == "approved",
        SharedPost.user_id != user_id,
    )
    if liked:
        query = query.filter(~SharedPost.id.in_(liked))
    rows = query.order_by(SharedPost.created_at.desc()).limit(300).all()

    max_like = max([p.like_count or 0 for p in rows] or [0])
    denom = math.log1p(max_like) if max_like > 0 else 1.0
    now = datetime.utcnow()

    scored = []
    for post in rows:
        hot = math.log1p(post.like_count or 0) / denom
        same_domain = 1.0 if affinity.get(post.domain) else 0.0
        days = max(0.0, (now - (post.created_at or now)).total_seconds() / 86400)
        fresh = math.exp(-days / 30.0)
        score = 0.55 * hot + 0.30 * same_domain + 0.15 * fresh
        scored.append((score, same_domain, post))

    scored.sort(key=lambda x: -x[0])
    picked = [p for _, _, p in scored[:limit]]
    authors = _authors(db, picked)
    systems = _systems(db, [p.file_id for p in picked])
    items = []
    for score, same_domain, post in scored[:limit]:
        brief = post_brief(post, False, authors.get(post.user_id), systems.get(post.file_id))
        brief["recommend_score"] = round(score, 3)
        brief["reason"] = "同领域内容" if same_domain else "近期热门"
        items.append(brief)
    return {"items": items, "profile_domains": [d for d, _ in affinity.most_common(5)]}


def like_post(db: Session, post_id: int, user_id: int) -> Dict:
    """点赞：同一用户只能点一次；重复调用返回已经点过。"""
    post = db.query(SharedPost).filter_by(id=post_id).first()
    if not post:
        raise AppError("分享不存在", status_code=404, code="not_found")
    if post.status != "approved":
        raise AppError("该分享尚未通过判定，暂不能点赞", status_code=409, code="not_approved")

    exists = db.query(PostLike).filter_by(post_id=post_id, user_id=user_id).first()
    if exists:
        return {"liked": True, "already": True, "like_count": post.like_count or 0}

    db.add(PostLike(post_id=post_id, user_id=user_id))
    try:
        db.query(SharedPost).filter_by(id=post_id).update(
            {SharedPost.like_count: SharedPost.like_count + 1})
        db.commit()
    except IntegrityError:
        # 并发下唯一约束兜底：回滚后按已点赞返回，不重复计数
        db.rollback()
        current = db.query(SharedPost).filter_by(id=post_id).first()
        return {"liked": True, "already": True, "like_count": (current.like_count if current else 0)}

    db.refresh(post)
    return {"liked": True, "already": False, "like_count": post.like_count or 0}


def unlike_post(db: Session, post_id: int, user_id: int) -> Dict:
    """取消点赞：没点过也按成功返回，计数不会减到负数。"""
    row = db.query(PostLike).filter_by(post_id=post_id, user_id=user_id).first()
    if row:
        db.delete(row)
        db.query(SharedPost).filter(
            SharedPost.id == post_id, SharedPost.like_count > 0
        ).update({SharedPost.like_count: SharedPost.like_count - 1})
        db.commit()
    post = db.query(SharedPost).filter_by(id=post_id).first()
    return {"liked": False, "like_count": (post.like_count if post else 0)}


def search(db: Session, viewer_id: int, q: str, limit: int = 20, offset: int = 0) -> Dict:
    """搜索其他用户的分享：标题 / 摘要 / 领域。"""
    return list_posts(db, viewer_id, sort="hot", q=q, limit=limit, offset=offset,
                      include_mine=True)
