"""笔记 CRUD API"""
import time
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, List, Any
from datetime import datetime
from app.database import get_db
from app.models.models import Note, NoteNode
from app.services.validator import validate_content, summarize, split_sentence_ranges

router = APIRouter()


class NoteSaveRequest(BaseModel):
    id: Optional[int] = None
    user_id: int = 1
    title: str = "未命名笔记"
    content: str = ""
    tags: Optional[List[str]] = None
    linked_files: Optional[List[Any]] = None
    linked_nodes: Optional[List[Any]] = None
    archived: Optional[bool] = None  # None=未提供，不覆盖已有归档状态
    accuracy_score: Optional[float] = None
    # 模块2 · v2 校验报告（前端实时校验结果落库；缺省时后端自动补一次校验）
    validation_report: Optional[Any] = None
    validation_status: Optional[str] = None
    verified: Optional[bool] = None


def _derive_from_report(report: Any) -> dict:
    """从 v2 校验报告中推导 validation_status / verified / accuracy（0-100）。

    兼容两种报告形态：
      - 前端 preSaveValidation 结果：{ errors[], warnings[], canForceSave, summary:{accuracy} }
      - 后端 /api/notes/{id}/validate 结果：{ issues[], errors[], warnings[],
        can_force_save, summary:{accuracy} }
    """
    status, verified, accuracy = 'pending', None, None
    if not isinstance(report, dict):
        return {'validation_status': status, 'verified': verified, 'accuracy_score': accuracy}

    summary = report.get('summary') or {}
    raw_acc = summary.get('accuracy')
    if raw_acc is None:
        raw_acc = report.get('accuracy_score')
    if isinstance(raw_acc, (int, float)):
        accuracy = round(raw_acc * 100, 1) if raw_acc <= 1 else float(raw_acc)

    def _has_sev(target):
        for key in ('errors', 'issues'):
            arr = report.get(key)
            if isinstance(arr, list) and any(
                isinstance(e, dict) and e.get('severity') == target for e in arr
            ):
                return True
        return False

    has_critical = _has_sev('critical')
    if report.get('canForceSave', report.get('can_force_save')) is False:
        has_critical = True
    has_warning = _has_sev('major') or _has_sev('minor') or _has_sev('info')
    if not (has_critical or has_warning):
        # 空报告视为通过（summary.errors==0 且无 issue）
        if summary.get('errors'):
            has_critical = True
        else:
            warnings = report.get('warnings')
            has_warning = isinstance(warnings, list) and len(warnings) > 0

    if has_critical:
        status = 'error'
    elif has_warning:
        status = 'warning'
    else:
        status = 'passed'
    verified = status == 'passed' and (accuracy is None or accuracy >= 80)
    return {'validation_status': status, 'verified': verified, 'accuracy_score': accuracy}


def _apply_validation(note: Note, request: 'NoteSaveRequest') -> None:
    """保存时写入校验报告；未显式传状态字段则从报告推导。"""
    if request.validation_report is not None:
        note.validation_report = request.validation_report
        derived = _derive_from_report(request.validation_report)
        note.validation_status = request.validation_status if request.validation_status is not None else derived['validation_status']
        note.verified = request.verified if request.verified is not None else derived['verified']
        if request.accuracy_score is None:
            note.accuracy_score = derived['accuracy_score']
    else:
        if request.validation_status is not None:
            note.validation_status = request.validation_status
        if request.verified is not None:
            note.verified = request.verified
        if request.accuracy_score is not None:
            note.accuracy_score = request.accuracy_score


@router.post("/save")
def save_note(request: NoteSaveRequest, db: Session = Depends(get_db)):
    """保存或更新笔记"""
    now = datetime.utcnow()

    if request.id:
        note = db.query(Note).filter_by(id=request.id, user_id=request.user_id).first()
        if not note:
            return {"ok": False, "message": "笔记不存在"}
        note.title = request.title
        note.content = request.content
        note.tags = request.tags or []
        note.linked_files = request.linked_files or []
        note.linked_nodes = request.linked_nodes or []
        if request.archived is not None:
            note.archived = request.archived
        _apply_validation(note, request)
        note.version = (note.version or 1) + 1
        note.updated_at = now
    else:
        note = Note(
            user_id=request.user_id,
            title=request.title,
            content=request.content,
            tags=request.tags or [],
            linked_files=request.linked_files or [],
            linked_nodes=request.linked_nodes or [],
            created_at=now,
            updated_at=now
        )
        if request.archived is not None:
            note.archived = request.archived
        _apply_validation(note, request)
        db.add(note)

    db.commit()
    db.refresh(note)

    return {
        "ok": True,
        "note": {
            "id": note.id,
            "title": note.title,
            "content": note.content,
            "tags": note.tags,
            "linked_files": note.linked_files,
            "linked_nodes": note.linked_nodes,
            "archived": note.archived,
            "accuracy_score": note.accuracy_score,
            "verified": note.verified,
            "validation_status": note.validation_status,
            "validation_report": note.validation_report,
            "created_at": note.created_at.isoformat() if note.created_at else None,
            "updated_at": note.updated_at.isoformat() if note.updated_at else None
        }
    }


@router.post("/{note_id}/validate")
def validate_note(note_id: int, db: Session = Depends(get_db)):
    """对既有笔记运行后端 v2 校验并将报告落库（同时同步关联知识节点的校验状态）。"""
    note = db.query(Note).filter_by(id=note_id).first()
    if not note:
        return {"ok": False, "message": "笔记不存在"}

    issues = validate_content(note.content or '', db)
    sentence_count = len(split_sentence_ranges(note.content or ''))
    summary = summarize(issues, sentence_count=sentence_count)
    errors = [i for i in issues if i['severity'] in ('critical', 'major')]
    warnings = [i for i in issues if i['severity'] in ('minor', 'info')]
    report = {
        "issues": issues,
        "errors": errors,
        "warnings": warnings,
        "passed": len(errors) == 0,
        "can_force_save": not any(i['severity'] == 'critical' for i in issues),
        "summary": {**summary, "checkedAt": int(time.time() * 1000)},
    }

    derived = _derive_from_report(report)
    note.validation_report = report
    note.validation_status = derived['validation_status']
    note.accuracy_score = derived['accuracy_score']
    note.verified = derived['verified']
    note.updated_at = datetime.utcnow()

    # 同步关联知识节点的校验状态（无命中→passed，仅提示→warning，有阻断→error）
    linked_ids = [int(n) for n in (note.linked_nodes or []) if str(n).isdigit()]
    if linked_ids:
        from app.models.models import Node
        nodes = db.query(Node).filter(Node.id.in_(linked_ids)).all()
        for node in nodes:
            title = (node.title or '').lower()
            entity = (node.entity or '').lower()
            level = 'passed'
            for issue in issues:
                ent = (issue.get('entity') or '').lower()
                if not ent:
                    continue
                if ent in title or ent in entity or title in ent:
                    if issue['severity'] == 'critical':
                        level = 'error'
                        break
                    level = 'warning'
            node.validate_status = level
            node.validated = level == 'passed'

    db.commit()
    return {"ok": True, "report": report}


@router.delete("/{note_id}")
def delete_note(note_id: int, user_id: int = 1, db: Session = Depends(get_db)):
    """删除笔记"""
    note = db.query(Note).filter_by(id=note_id, user_id=user_id).first()
    if not note:
        return {"ok": False, "message": "笔记不存在"}

    # 先清理 note_nodes 关联行，避免删除笔记后残留孤儿关联
    db.query(NoteNode).filter(NoteNode.note_id == note_id).delete()
    db.delete(note)
    db.commit()
    return {"ok": True, "message": f"笔记 '{note.title}' 已删除"}


@router.get("")
def list_notes(user_id: int = 1, archived: Optional[bool] = None, db: Session = Depends(get_db)):
    """获取笔记列表"""
    query = db.query(Note).filter_by(user_id=user_id)
    if archived is not None:
        query = query.filter_by(archived=archived)

    notes = query.order_by(Note.updated_at.desc()).all()
    return {
        "notes": [
            {
                "id": n.id,
                "title": n.title,
                "content": n.content[:200] if n.content else "",
                "tags": n.tags or [],
                "linked_files": n.linked_files or [],
                "linked_nodes": n.linked_nodes or [],
                "archived": n.archived,
                "accuracy_score": n.accuracy_score,
                "verified": n.verified,
                "validation_status": n.validation_status,
                "validation_report": n.validation_report,
                "created_at": n.created_at.isoformat() if n.created_at else None,
                "updated_at": n.updated_at.isoformat() if n.updated_at else None
            }
            for n in notes
        ]
    }


@router.get("/{note_id}")
def get_note(note_id: int, user_id: int = 1, db: Session = Depends(get_db)):
    """获取单个笔记详情"""
    note = db.query(Note).filter_by(id=note_id, user_id=user_id).first()
    if not note:
        return {"ok": False, "message": "笔记不存在"}

    return {
        "ok": True,
        "note": {
            "id": note.id,
            "title": note.title,
            "content": note.content,
            "tags": note.tags or [],
            "linked_files": note.linked_files or [],
            "linked_nodes": note.linked_nodes or [],
            "archived": note.archived,
            "accuracy_score": note.accuracy_score,
            "verified": note.verified,
            "validation_status": note.validation_status,
            "validation_report": note.validation_report,
            "created_at": note.created_at.isoformat() if note.created_at else None,
            "updated_at": note.updated_at.isoformat() if note.updated_at else None
        }
    }