"""操作审计：记录「谁做了什么、依据是什么」

后台管理页靠这里还原"用户操作的根据"：
  - 上传：为什么切割成 N 片（行数/字符数/切点/标题上下文）
  - 解析：抽了多少知识点、哪些进了候选、知识库锚定/关联结果
  - 判定：四路证据（知识库/图谱/规则/联网）的逐条明细与最终分数
  - 管理员动作：批量通过/驳回/编辑，以及原因备注
  - 删除、知识库重建、个人资料修改等

detail 直接存 JSON，前端可展开查看证据链；查询支持 action / target / 关键词 / 时间。
"""
from datetime import datetime, timedelta
from typing import Dict, Optional

from loguru import logger

from app.config import settings


def log_event(
    db,
    action: str,
    *,
    actor: str = "user",
    user_id: int = 1,
    target_type: Optional[str] = None,
    target_id: Optional[int] = None,
    target_name: Optional[str] = None,
    summary: str = "",
    detail: Optional[Dict] = None,
    status: str = "ok",
    duration_ms: Optional[int] = None,
    commit: bool = True,
):
    """写一条审计记录（永不抛异常，避免影响主流程）"""
    try:
        from app.models.models import AuditLog

        row = AuditLog(
            user_id=user_id, actor=actor, action=action,
            target_type=target_type, target_id=target_id, target_name=target_name,
            summary=(summary or "")[:500], detail=detail or {},
            status=status, duration_ms=duration_ms,
        )
        db.add(row)
        if commit:
            db.commit()
        return row.id
    except Exception as exc:  # 审计失败不能拖垮业务
        logger.warning(f"写审计失败（{action}）：{exc}")
        try:
            db.rollback()
        except Exception:
            pass
        return None


def trim(db, keep: Optional[int] = None):
    """只保留最近 N 条审计（默认 settings.AUDIT_KEEP_ROWS）"""
    try:
        from app.models.models import AuditLog
        keep = keep or settings.AUDIT_KEEP_ROWS
        total = db.query(AuditLog).count()
        if total <= keep:
            return 0
        cutoff_rows = (db.query(AuditLog.id).order_by(AuditLog.id.desc())
                       .offset(keep).limit(1).all())
        if not cutoff_rows:
            return 0
        cutoff_id = cutoff_rows[0][0]
        removed = db.query(AuditLog).filter(AuditLog.id <= cutoff_id).delete(
            synchronize_session=False)
        db.commit()
        return removed
    except Exception as exc:
        logger.warning(f"清理审计失败：{exc}")
        return 0


def summarize_action(action: str) -> str:
    """动作 → 中文标签（后台展示用）"""
    return {
        "upload": "上传文件",
        "split": "智能切割",
        "parse": "解析抽取",
        "verdict": "智能判定",
        "review": "人工判定",
        "kb_import": "知识库导入",
        "kb_rebuild": "知识库重建",
        "delete_file": "删除文件",
        "delete_candidate": "删除候选",
        "delete_entry": "删除知识点",
        "profile_update": "资料修改",
        "profile_upload": "上传图片",
        "login": "进入后台",
        "search": "联网检索",
    }.get(action, action)


def recent_stats(db, days: int = 7):
    """近 N 天的动作分布（后台概览用）"""
    from app.models.models import AuditLog
    since = datetime.utcnow() - timedelta(days=days)
    rows = db.query(AuditLog.action, AuditLog.status).filter(AuditLog.created_at >= since).all()
    actions: Dict[str, int] = {}
    warns = 0
    for action, status in rows:
        actions[action] = actions.get(action, 0) + 1
        if status != "ok":
            warns += 1
    return {"window_days": days, "total": len(rows), "actions": actions, "abnormal": warns}
