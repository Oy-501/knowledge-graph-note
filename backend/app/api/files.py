"""文件上传、解析、同步与删除 API"""
import json
from fastapi import APIRouter, Depends, UploadFile, File as FastAPIFile, BackgroundTasks
from pydantic import BaseModel
from typing import Optional
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.models import File, Node, NodeSource, Link, IsolateBlacklist, NoteNode
from app.services.parser import parse_and_extract
from app.services.inference import infer_links_for_new_file

router = APIRouter()


def _purge_file_nodes(db: Session, file_id: int) -> int:
    node_ids = [n.id for n in db.query(Node).filter_by(file_id=file_id).all()]
    if not node_ids:
        return 0
    db.query(NodeSource).filter(NodeSource.node_id.in_(node_ids)).delete(synchronize_session=False)
    db.query(Link).filter(
        (Link.source_id.in_(node_ids)) | (Link.target_id.in_(node_ids))
    ).delete(synchronize_session=False)
    db.query(IsolateBlacklist).filter(
        (IsolateBlacklist.node_id.in_(node_ids)) |
        (IsolateBlacklist.blocked_node_id.in_(node_ids))
    ).delete(synchronize_session=False)
    db.query(NoteNode).filter(NoteNode.node_id.in_(node_ids)).delete(synchronize_session=False)
    db.query(Node).filter(Node.id.in_(node_ids)).delete(synchronize_session=False)
    return len(node_ids)


@router.post("/upload")
async def upload_file(file: UploadFile = FastAPIFile(...), user_id: int = 1, db: Session = Depends(get_db), background_tasks: BackgroundTasks = None):
    content = await file.read()
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        text = content.decode("gbk", errors="replace")
    file_record = File(user_id=user_id, name=file.filename, content=text, status="parsing")
    db.add(file_record)
    db.commit()
    db.refresh(file_record)
    if background_tasks:
        background_tasks.add_task(parse_and_extract, file_record.id, user_id)
    else:
        parse_and_extract(file_record.id, user_id)
    return {"file_id": file_record.id, "name": file.filename, "status": "parsing", "message": "文件已上传，正在解析"}


@router.delete("/{file_id}")
def delete_file(file_id: int, user_id: int = 1, db: Session = Depends(get_db)):
    file_record = db.query(File).filter_by(id=file_id, user_id=user_id).first()
    if not file_record:
        return {"ok": False, "message": "文件不存在"}
    deleted_nodes = _purge_file_nodes(db, file_id)
    db.delete(file_record)
    db.commit()
    return {"ok": True, "deleted_nodes": deleted_nodes,
            "message": f"文件 '{file_record.name}' 及其 {deleted_nodes} 个节点已删除"}


class FileSyncRequest(BaseModel):
    user_id: int = 1
    source_path: str = ""
    name: str = ""
    content: str = ""


@router.post("/sync")
def sync_file(req: FileSyncRequest, db: Session = Depends(get_db)):
    if not req.source_path:
        return {"ok": False, "message": "缺少 source_path"}
    file_record = db.query(File).filter_by(user_id=req.user_id, source_path=req.source_path).first()
    created = file_record is None
    if created:
        file_record = File(user_id=req.user_id, name=req.name, content=req.content,
                           source_path=req.source_path, status="parsing")
        db.add(file_record)
        db.commit()
        db.refresh(file_record)
    else:
        file_record.name = req.name
        file_record.content = req.content
        file_record.status = "parsing"
        try:
            removed = _purge_file_nodes(db, file_record.id)
            db.commit()
        except Exception as exc:
            db.rollback()
            return {"ok": False, "message": f"旧节点清理失败：{exc}", "file_id": file_record.id}
    try:
        parse_and_extract(file_record.id, req.user_id)
    except Exception as exc:
        file_record.status = "error"
        db.commit()
        return {"ok": False, "message": f"解析失败：{exc}", "file_id": file_record.id}
    db.refresh(file_record)
    return {"ok": True, "file_id": file_record.id, "created": created,
            "name": file_record.name, "status": file_record.status,
            "node_count": file_record.node_count}


class FileRenameRequest(BaseModel):
    user_id: int = 1
    name: Optional[str] = None
    source_path: Optional[str] = None


@router.patch("/{file_id}")
def update_file_meta(file_id: int, req: FileRenameRequest, db: Session = Depends(get_db)):
    file_record = db.query(File).filter_by(id=file_id, user_id=req.user_id).first()
    if not file_record:
        return {"ok": False, "message": "文件不存在"}
    if req.name is not None:
        file_record.name = req.name
    if req.source_path is not None:
        file_record.source_path = req.source_path
    db.commit()
    return {"ok": True, "file_id": file_record.id, "name": file_record.name}


@router.get("")
def list_files(user_id: int = 1, db: Session = Depends(get_db)):
    files = db.query(File).filter_by(user_id=user_id).order_by(File.uploaded_at.desc()).all()
    return {"files": [{"id": f.id, "name": f.name, "status": f.status,
                        "node_count": f.node_count,
                        "uploaded_at": f.uploaded_at.isoformat() if f.uploaded_at else None}
                       for f in files]}


@router.get("/{file_id}/nodes")
def get_file_nodes(file_id: int, user_id: int = 1, db: Session = Depends(get_db)):
    nodes = db.query(Node).filter_by(file_id=file_id, user_id=user_id).all()
    return {"nodes": [{"id": n.id, "entity": n.entity, "title": n.title, "type": n.type,
                        "description": n.description, "keywords": n.keywords or [],
                        "entities": n.entities or [], "level": n.level, "domain": n.domain,
                        "status": n.status} for n in nodes]}
