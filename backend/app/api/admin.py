"""后台管理 API：知识点审阅、操作审计、用户概览（口令保护）

后台的核心价值：让管理员看到**每条判断的依据**——
  · 候选知识点为什么被判"采纳/待审/驳回"（四路证据链）
  · 用户每次上传为什么被切割、切成了几片、每片抽了多少
  · 管理员自己做过哪些裁决与批量操作
"""
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from loguru import logger
from pydantic import BaseModel
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models.models import (
    AuditLog, File, KnowledgeBase, KnowledgeCandidate, Link, Node, User, UserProfile,
)
from app.services import audit as audit_svc
from app.services.errors import clamp_paging, escape_like
from app.services import knowledge_verifier

router = APIRouter()


# ---------------------------------------------------------------- 口令校验

def require_admin(x_admin_token: Optional[str] = Header(default=None, alias="X-Admin-Token"),
                  request: Request = None):
    """后台口令校验（失效安全 + 失败限流 + 恒定时间比较）。

    相对旧实现收紧了两点：

    1. **失效安全（fail-closed）**：旧实现是
       `if not expected: return True` —— 口令为空时**完全放开后台**，
       批量驳回、删除候选、改判定全部对任意能访问端口的人开放。
       配置缺失属于「加固未完成」，应当拒绝而不是放行。
       现在未配置口令直接 503，并明确告知如何配置。

    2. **失败限流**：旧实现允许无限次尝试，弱口令可被在线暴力破解。
       按客户端 IP 记录失败次数，超限返回 429。

    比较改用 hmac.compare_digest（恒定时间），避免 `!=` 逐字符比较
    通过响应时间泄露口令长度与前缀。
    """
    from app.services.security import (admin_limiter, admin_token_configured,
                                       client_key, verify_admin_token)

    if not admin_token_configured():
        raise HTTPException(
            status_code=503,
            detail="后端未配置管理口令（ADMIN_TOKEN），后台已按失效安全策略关闭。"
                   "请在 backend/.env 设置 ADMIN_TOKEN 后重启后端（默认值 kg-admin 建议改掉）。",
        )

    key = client_key(request) if request is not None else "unknown"
    allowed, retry_after = admin_limiter.check(key)
    if not allowed:
        logger.warning(f"后台口令尝试过于频繁，已临时拒绝：client={key}")
        raise HTTPException(
            status_code=429,
            detail=f"口令错误次数过多，请在 {retry_after} 秒后重试。",
            headers={"Retry-After": str(retry_after)},
        )

    if not verify_admin_token(x_admin_token):
        admin_limiter.hit(key)
        raise HTTPException(status_code=401, detail="管理口令不正确，请在后台入口重新输入")

    admin_limiter.reset(key)   # 校验成功 → 清空失败计数
    return True


@router.get("/auth")
def check_auth(_: bool = Depends(require_admin)):
    """校验口令（前端进后台时先探一次）"""
    return {"ok": True, "protected": bool((settings.ADMIN_TOKEN or "").strip())}


# ---------------------------------------------------------------- 概览

@router.get("/overview")
def overview(_: bool = Depends(require_admin), db: Session = Depends(get_db)):
    """后台首页：规模 + 待审 + 审计活跃度"""
    cand_total = db.query(KnowledgeCandidate).count()
    pending = db.query(KnowledgeCandidate).filter_by(status="open").count()
    accepted = db.query(KnowledgeCandidate).filter_by(status="accepted").count()
    rejected = db.query(KnowledgeCandidate).filter_by(status="rejected").count()
    web_ok = db.query(KnowledgeCandidate).filter_by(verdict_web="ok").count()
    web_na = db.query(KnowledgeCandidate).filter_by(verdict_web="unavailable").count()

    return {
        "ok": True,
        "scale": {
            "users": db.query(User).count(),
            "files": db.query(File).count(),
            "nodes": db.query(Node).count(),
            "links": db.query(Link).count(),
            "kb_entries": db.query(KnowledgeBase).count(),
            "audit_rows": db.query(AuditLog).count(),
        },
        "candidates": {
            "total": cand_total, "pending": pending,
            "accepted": accepted, "rejected": rejected,
            "auto_accept_rate": round(accepted / cand_total, 3) if cand_total else 0.0,
            "web_ok": web_ok, "web_unavailable": web_na,
        },
        "thresholds": {
            "auto_accept": settings.VERDICT_AUTO_ACCEPT,
            "reject_below": settings.VERDICT_REJECT_BELOW,
            "web_enabled": settings.VERDICT_USE_WEB,
        },
        "activity": audit_svc.recent_stats(db, days=7),
    }


# ---------------------------------------------------------------- 候选知识点


def _candidate_brief(c: KnowledgeCandidate) -> Dict:
    return {
        "id": c.id, "entity": c.entity, "description": (c.description or "")[:200],
        "domain": c.domain, "level": c.level,
        "file_id": c.file_id, "node_id": c.node_id, "chunk_index": c.chunk_index,
        "line_start": c.line_start, "line_end": c.line_end,
        "extract_confidence": c.extract_confidence,
        "score": c.verdict_score, "decision": c.verdict_decision, "status": c.status,
        "reason": c.verdict_reason, "stage": c.verdict_stage, "web": c.verdict_web,
        "reviewed_by": c.reviewed_by,
        "reviewed_at": c.reviewed_at.isoformat() if c.reviewed_at else None,
        "kb_entry_id": c.kb_entry_id,
        "created_at": c.created_at.isoformat() if c.created_at else None,
    }


@router.get("/candidates")
def list_candidates(
    status: str = "", decision: str = "", file_id: int = 0, keyword: str = "",
    web: str = "", limit: int = 30, offset: int = 0,
    _: bool = Depends(require_admin), db: Session = Depends(get_db),
):
    """候选知识点列表（后台待审队列）"""
    q = db.query(KnowledgeCandidate)
    if status:
        q = q.filter(KnowledgeCandidate.status == status)
    if decision:
        q = q.filter(KnowledgeCandidate.verdict_decision == decision)
    if file_id:
        q = q.filter(KnowledgeCandidate.file_id == file_id)
    if web:
        q = q.filter(KnowledgeCandidate.verdict_web == web)
    if keyword:
        like = f"%{escape_like(keyword)}%"   # 转义 % 与 _，避免通配符扩大匹配范围
        q = q.filter(or_(KnowledgeCandidate.entity.ilike(like, escape='\\'),
                         KnowledgeCandidate.description.ilike(like, escape='\\')))

    total = q.count()
    # 分页守卫：min() 只防上限，防不住 limit=-1（SQLite 里等价于「不限制」→ 整表返回）
    _lim, _off = clamp_paging(limit, offset, max_limit=200, default_limit=30)
    rows = (q.order_by(KnowledgeCandidate.verdict_score.asc().nullsfirst(),
                       KnowledgeCandidate.id.desc())
            .offset(_off).limit(_lim).all())
    return {
        "ok": True, "total": total,
        "candidates": [_candidate_brief(c) for c in rows],
        "files": {f.id: f.name for f in db.query(File).all()},
    }


@router.get("/candidates/{cand_id}")
def candidate_detail(cand_id: int, _: bool = Depends(require_admin),
                     db: Session = Depends(get_db)):
    """候选详情：完整证据链 + 原文"""
    c = db.query(KnowledgeCandidate).filter_by(id=cand_id).first()
    if not c:
        return {"ok": False, "message": "候选不存在"}
    file_row = db.query(File).filter_by(id=c.file_id).first() if c.file_id else None
    return {
        "ok": True,
        "candidate": {
            **_candidate_brief(c),
            "title": c.title,
            "keywords": c.keywords or [],
            "evidence": c.verdict_evidence or [],
            "source_text": c.source_text,
            "review_note": c.review_note,
            "file_name": file_row.name if file_row else "",
            "file_note": file_row.parse_note if file_row else "",
        },
    }


class ReviewPayload(BaseModel):
    action: str                    # accept | reject | pending
    note: str = ""
    reviewer: str = "admin"
    ingest: bool = True            # accept 时是否写入知识库


@router.post("/candidates/{cand_id}/review")
def review_candidate(cand_id: int, payload: ReviewPayload,
                     _: bool = Depends(require_admin), db: Session = Depends(get_db)):
    """管理员裁决单条候选（人工判定）"""
    c = db.query(KnowledgeCandidate).filter_by(id=cand_id).first()
    if not c:
        return {"ok": False, "message": "候选不存在"}
    if payload.action not in ("accept", "reject", "pending"):
        return {"ok": False, "message": "action 只能是 accept/reject/pending"}

    before = {"status": c.status, "decision": c.verdict_decision}
    ingested = None
    if payload.action == "accept":
        c.status = "accepted"
        c.verdict_decision = "accept"
        if payload.ingest:
            ingested = knowledge_verifier._ingest_to_kb(db, c)
    elif payload.action == "reject":
        c.status = "rejected"
        c.verdict_decision = "reject"
    else:
        c.status = "open"
        c.verdict_decision = "pending"

    c.verdict_stage = "human"
    c.reviewed_by = payload.reviewer
    c.reviewed_at = datetime.utcnow()
    c.review_note = payload.note
    db.commit()

    audit_svc.log_event(
        db, "review", actor="admin", user_id=c.user_id,
        target_type="candidate", target_id=c.id, target_name=c.entity,
        summary=f"人工裁决「{c.entity}」：{payload.action}" + (f"（{payload.note}）" if payload.note else ""),
        detail={
            "action": payload.action,
            "before": before,
            "after": {"status": c.status, "decision": c.verdict_decision},
            "auto_verdict": {"score": c.verdict_score, "reason": c.verdict_reason,
                             "evidence": c.verdict_evidence},
            "note": payload.note,
            "ingested_kb_entry_id": ingested,
            "override": (before["decision"] not in (payload.action, "pending")),
        },
        status="ok" if payload.action != "reject" else "warn",
    )
    return {"ok": True, "message": f"已{payload.action}", "ingested_kb_entry_id": ingested}


class BulkReviewPayload(BaseModel):
    ids: List[int] = []
    status: str = ""            # 按状态批量（ids 为空时生效）
    decision: str = ""
    limit: int = 200
    action: str = "accept"
    note: str = ""
    reviewer: str = "admin"
    ingest: bool = True


@router.post("/candidates/bulk-review")
def bulk_review(payload: BulkReviewPayload, _: bool = Depends(require_admin),
                db: Session = Depends(get_db)):
    """批量裁决（可指定 ids，或按状态/判定筛选取一批）"""
    q = db.query(KnowledgeCandidate)
    if payload.ids:
        q = q.filter(KnowledgeCandidate.id.in_(payload.ids))
    else:
        if payload.status:
            q = q.filter(KnowledgeCandidate.status == payload.status)
        if payload.decision:
            q = q.filter(KnowledgeCandidate.verdict_decision == payload.decision)
    _lim, _ = clamp_paging(payload.limit, max_limit=500, default_limit=200)
    rows = q.limit(_lim).all()
    if not rows:
        return {"ok": False, "message": "没有匹配的候选"}

    changed = []
    for c in rows:
        if payload.action == "accept":
            c.status = "accepted"
            c.verdict_decision = "accept"
            if payload.ingest:
                knowledge_verifier._ingest_to_kb(db, c)
        elif payload.action == "reject":
            c.status = "rejected"
            c.verdict_decision = "reject"
        else:
            c.status = "open"
            c.verdict_decision = "pending"
        c.verdict_stage = "human"
        c.reviewed_by = payload.reviewer
        c.reviewed_at = datetime.utcnow()
        c.review_note = payload.note
        changed.append(c.entity)
    db.commit()

    audit_svc.log_event(
        db, "review", actor="admin", user_id=1, target_type="candidate",
        summary=f"批量{payload.action} {len(changed)} 条候选知识点",
        detail={
            "count": len(changed),
            "action": payload.action,
            "filter": {"ids": payload.ids[:50], "status": payload.status,
                        "decision": payload.decision, "limit": payload.limit},
            "samples": changed[:20],
            "note": payload.note,
        },
    )
    return {"ok": True, "count": len(changed), "samples": changed[:10]}


class VerifyPayload(BaseModel):
    ids: List[int] = []
    status: str = "open"
    limit: int = 50
    use_web: Optional[bool] = None
    auto_ingest: bool = True


@router.post("/candidates/verify")
def verify_candidates(payload: VerifyPayload, _: bool = Depends(require_admin),
                      db: Session = Depends(get_db)):
    """对候选重跑智能判定（可强制开启/关闭联网）"""
    q = db.query(KnowledgeCandidate)
    if payload.ids:
        q = q.filter(KnowledgeCandidate.id.in_(payload.ids))
    elif payload.status:
        q = q.filter(KnowledgeCandidate.status == payload.status)
    _lim, _ = clamp_paging(payload.limit, max_limit=200, default_limit=50)
    rows = q.limit(_lim).all()
    if not rows:
        return {"ok": False, "message": "没有匹配的候选"}

    stats = knowledge_verifier.verify_batch(
        db, rows, use_web=payload.use_web, auto_ingest=payload.auto_ingest)
    audit_svc.log_event(
        db, "verdict", actor="admin", user_id=1, target_type="candidate",
        summary=f"重跑智能判定 {stats['total']} 条：采纳 {stats['accept']} / 待审 {stats['pending']} / 驳回 {stats['reject']}",
        detail={"stats": stats, "use_web": payload.use_web,
                "thresholds": {"auto_accept": settings.VERDICT_AUTO_ACCEPT,
                               "reject_below": settings.VERDICT_REJECT_BELOW}},
    )
    return {"ok": True, "stats": stats}


@router.delete("/candidates/{cand_id}")
def delete_candidate(cand_id: int, _: bool = Depends(require_admin),
                     db: Session = Depends(get_db)):
    """删除候选（不删对应图谱节点）"""
    c = db.query(KnowledgeCandidate).filter_by(id=cand_id).first()
    if not c:
        return {"ok": False, "message": "候选不存在"}
    name = c.entity
    db.delete(c)
    db.commit()
    audit_svc.log_event(db, "delete_candidate", actor="admin", target_type="candidate",
                        target_id=cand_id, target_name=name,
                        summary=f"删除候选「{name}」", status="warn")
    return {"ok": True, "message": f"已删除候选「{name}」"}


# ---------------------------------------------------------------- 操作审计

@router.get("/audit")
def list_audit(
    action: str = "", actor: str = "", target_type: str = "", keyword: str = "",
    status: str = "", days: int = 0, limit: int = 30, offset: int = 0,
    _: bool = Depends(require_admin), db: Session = Depends(get_db),
):
    """操作审计列表：谁在什么时候做了什么、依据是什么（summary 即为依据摘要）"""
    q = db.query(AuditLog)
    if action:
        q = q.filter(AuditLog.action == action)
    if actor:
        q = q.filter(AuditLog.actor == actor)
    if target_type:
        q = q.filter(AuditLog.target_type == target_type)
    if status:
        q = q.filter(AuditLog.status == status)
    if days:
        q = q.filter(AuditLog.created_at >= datetime.utcnow() - timedelta(days=days))
    if keyword:
        like = f"%{escape_like(keyword)}%"   # 转义 % 与 _，避免通配符扩大匹配范围
        q = q.filter(or_(AuditLog.summary.ilike(like, escape='\\'),
                         AuditLog.target_name.ilike(like, escape='\\'),
                         AuditLog.action.ilike(like, escape='\\')))

    total = q.count()
    _lim, _off = clamp_paging(limit, offset, max_limit=200, default_limit=30)
    rows = q.order_by(AuditLog.id.desc()).offset(_off).limit(_lim).all()
    actions = [a for (a,) in db.query(AuditLog.action).distinct().all()]
    return {
        "ok": True, "total": total,
        "actions": sorted(actions),
        "labels": {a: audit_svc.summarize_action(a) for a in actions},
        "logs": [{
            "id": r.id, "action": r.action, "action_label": audit_svc.summarize_action(r.action),
            "actor": r.actor, "user_id": r.user_id,
            "target_type": r.target_type, "target_id": r.target_id, "target_name": r.target_name,
            "summary": r.summary, "status": r.status, "duration_ms": r.duration_ms,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "has_detail": bool(r.detail),
        } for r in rows],
    }


@router.get("/audit/{log_id}")
def audit_detail(log_id: int, _: bool = Depends(require_admin),
                 db: Session = Depends(get_db)):
    """审计详情：完整依据（切割方案 / 判定证据链 / 裁决前后对比…）"""
    r = db.query(AuditLog).filter_by(id=log_id).first()
    if not r:
        return {"ok": False, "message": "日志不存在"}
    return {
        "ok": True,
        "log": {
            "id": r.id, "action": r.action, "action_label": audit_svc.summarize_action(r.action),
            "actor": r.actor, "user_id": r.user_id,
            "target_type": r.target_type, "target_id": r.target_id, "target_name": r.target_name,
            "summary": r.summary, "detail": r.detail or {}, "status": r.status,
            "duration_ms": r.duration_ms,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        },
    }


# ---------------------------------------------------------------- 用户与统计

@router.get("/users")
def list_users(_: bool = Depends(require_admin), db: Session = Depends(get_db)):
    """用户列表 + 各自的数据量与最近动作数"""
    users = db.query(User).all()
    profiles = {p.user_id: p for p in db.query(UserProfile).all()}
    out = []
    for u in users:
        uid = u.id
        last = (db.query(AuditLog)
                .filter(AuditLog.user_id == uid)
                .order_by(AuditLog.id.desc()).first())
        out.append({
            "id": uid, "username": u.username,
            "display_name": (profiles.get(uid).display_name if profiles.get(uid) else "") or u.username,
            "avatar_url": profiles.get(uid).avatar_url if profiles.get(uid) else "",
            "files": db.query(File).filter_by(user_id=uid).count(),
            "nodes": db.query(Node).filter_by(user_id=uid).count(),
            "candidates": db.query(KnowledgeCandidate).filter_by(user_id=uid).count(),
            "audit_rows": db.query(AuditLog).filter_by(user_id=uid).count(),
            "last_active": last.created_at.isoformat() if last and last.created_at else None,
            "created_at": u.created_at.isoformat() if u.created_at else None,
        })
    return {"ok": True, "users": out}


@router.get("/stats/verdicts")
def verdict_stats(_: bool = Depends(require_admin), db: Session = Depends(get_db)):
    """判定统计：分数分布 + 人工覆盖率 + 联网可用率"""
    rows = db.query(KnowledgeCandidate).all()
    buckets = {"0-0.35": 0, "0.35-0.6": 0, "0.6-0.8": 0, "0.8-1.0": 0, "未判定": 0}
    human = 0
    by_decision: Dict[str, int] = {}
    for c in rows:
        s = c.verdict_score
        if s is None:
            buckets["未判定"] += 1
        elif s < 0.35:
            buckets["0-0.35"] += 1
        elif s < 0.6:
            buckets["0.35-0.6"] += 1
        elif s < 0.8:
            buckets["0.6-0.8"] += 1
        else:
            buckets["0.8-1.0"] += 1
        if c.verdict_stage == "human":
            human += 1
        by_decision[c.verdict_decision or "pending"] = \
            by_decision.get(c.verdict_decision or "pending", 0) + 1

    total = len(rows)
    return {
        "ok": True,
        "total": total,
        "score_buckets": buckets,
        "by_decision": by_decision,
        "human_reviewed": human,
        "human_rate": round(human / total, 3) if total else 0.0,
        "auto_rate": round((total - human) / total, 3) if total else 0.0,
    }


@router.get("/files")
def admin_files(_: bool = Depends(require_admin), db: Session = Depends(get_db)):
    """文件与其解析情况（含切割备注、候选判定分布）"""
    files = db.query(File).order_by(File.id.desc()).limit(200).all()
    cand_rows = (db.query(KnowledgeCandidate.file_id, KnowledgeCandidate.status,
                          func.count(KnowledgeCandidate.id))
                 .group_by(KnowledgeCandidate.file_id, KnowledgeCandidate.status).all())
    dist: Dict[int, Dict[str, int]] = {}
    for fid, status, cnt in cand_rows:
        dist.setdefault(fid, {})[status] = cnt
    return {
        "ok": True,
        "files": [{
            "id": f.id, "name": f.name, "status": f.status,
            "node_count": f.node_count, "parse_note": f.parse_note,
            "uploaded_at": f.uploaded_at.isoformat() if f.uploaded_at else None,
            "candidate_stats": dist.get(f.id, {}),
        } for f in files],
    }
