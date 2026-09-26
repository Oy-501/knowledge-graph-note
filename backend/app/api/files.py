"""文件上传、解析、同步与删除 API"""
import json
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File as FastAPIFile, BackgroundTasks
from pydantic import BaseModel
from typing import Optional
from sqlalchemy.orm import Session
from app.config import settings
from app.database import get_db
from app.models.models import (
    File, Node, NodeSource, Link, IsolateBlacklist, NoteNode, KnowledgeCandidate,
)
from app.services.parser import parse_and_extract
from app.services.inference import infer_links_for_new_file
from app.services.file_splitter import plan_split, describe_plan, summarize_pieces
from app.services import audit
from app.services import web_probe  # noqa: F401  （保持服务模块可用性检查）

router = APIRouter()


def upload_limits() -> dict:
    """上传统一上限（前端也读这个接口，保证前后端口径一致）"""
    return {
        "max_upload_mb": settings.MAX_UPLOAD_MB_HARD,
        "soft_split_mb": round(settings.SPLIT_TARGET_CHARS / 1024 / 1024, 1),
        "split_target_lines": settings.SPLIT_TARGET_LINES,
        "max_nodes_per_file": settings.MAX_NODES_PER_FILE,
        "max_nodes_total": settings.MAX_NODES_PER_FILE_TOTAL,
        "accept": [".md", ".markdown", ".txt", ".csv", ".tsv", ".json", ".log"],
        "advice": (
            f"超过 {settings.SPLIT_TARGET_LINES} 行或 "
            f"{round(settings.SPLIT_TARGET_CHARS / 1024 / 1024, 1)}MB 的文件会"
            f"自动按结构切割成多片逐片解析（内容不会丢），无需手动拆分；"
            f"硬上限 {settings.MAX_UPLOAD_MB_HARD}MB。"
        ),
    }


async def _read_text_limited(upload: UploadFile) -> str:
    """限额读取上传文件（硬上限内一律接收，超限交给智能切割）

    - 超过硬上限 MAX_UPLOAD_MB_HARD → 413（只读到 limit+1 字节就判定，不会被撑爆）
    - 疑似二进制（含 NUL 字节）→ 415
    """
    limit = settings.MAX_UPLOAD_MB_HARD * 1024 * 1024
    raw = await upload.read(limit + 1)
    if len(raw) > limit:
        raise HTTPException(
            status_code=413,
            detail=(f"文件超过硬上限 {settings.MAX_UPLOAD_MB_HARD}MB（当前 ≥ "
                    f"{len(raw) / 1024 / 1024:.1f}MB）。请拆分成多个文件分批上传。"),
        )
    if not raw:
        raise HTTPException(status_code=400, detail="文件内容为空。")
    if b"\x00" in raw[:8192]:
        raise HTTPException(
            status_code=415,
            detail=("检测到二进制内容（PDF / Office / 压缩包等）。系统只解析纯文本，"
                    "请先另存为 .md / .txt / .csv 再上传。"),
        )
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("gbk", errors="replace")


@router.get("/limits")
def get_upload_limits():
    """返回上传/解析上限，供前端做前置校验与提示"""
    return upload_limits()


def _purge_file_nodes(db: Session, file_id: int) -> int:
    """清除某文件产出的全部节点与关联，返回清除的节点数。

    供「删除文件」与「本地文件重新解析（sync 内容更新）」复用，
    保证图谱与知识画像中不留已删文档的残留。

    ⚠ 这里必须覆盖**所有**外键指向 `files.id` 的表。
    数据库开启了 `PRAGMA foreign_keys=ON`，漏一张表就会在删除文件时
    抛 `FOREIGN KEY constraint failed` —— 而且报错点在 `DELETE FROM files`，
    看不出是哪张子表没清（本轮就漏了知识画像与文件知识关联两张表）。
    当前引用 files 的表：nodes / knowledge_candidates /
    file_knowledge_profiles / file_knowledge_links。
    新增此类表时，**务必同时在这里补一行**，否则删文件会失败。
    """
    from app.models.models import FileKnowledgeLink, FileKnowledgeProfile

    # ---- 文件级关联表：与是否有节点无关，必须先清 ----
    db.query(KnowledgeCandidate).filter_by(file_id=file_id).delete(synchronize_session=False)
    db.query(FileKnowledgeProfile).filter_by(file_id=file_id).delete(synchronize_session=False)
    db.query(FileKnowledgeLink).filter(
        (FileKnowledgeLink.source_file_id == file_id) |
        (FileKnowledgeLink.target_file_id == file_id)
    ).delete(synchronize_session=False)

    # ---- 节点级关联表：先取 node_id 再逐张清理（bulk delete 不走 ORM cascade）----
    node_ids = [n.id for n in db.query(Node).filter_by(file_id=file_id).all()]
    if not node_ids:
        return 0
    db.query(NodeSource).filter(
        NodeSource.node_id.in_(node_ids)
    ).delete(synchronize_session=False)
    db.query(Link).filter(
        (Link.source_id.in_(node_ids)) | (Link.target_id.in_(node_ids))
    ).delete(synchronize_session=False)
    db.query(IsolateBlacklist).filter(
        (IsolateBlacklist.node_id.in_(node_ids)) |
        (IsolateBlacklist.blocked_node_id.in_(node_ids))
    ).delete(synchronize_session=False)
    db.query(NoteNode).filter(
        NoteNode.node_id.in_(node_ids)
    ).delete(synchronize_session=False)
    db.query(Node).filter(Node.id.in_(node_ids)).delete(synchronize_session=False)
    return len(node_ids)


@router.post("/upload")
async def upload_file(
    file: UploadFile = FastAPIFile(...),
    user_id: int = 1,
    db: Session = Depends(get_db),
    background_tasks: BackgroundTasks = None
):
    """上传文件并异步解析（大文件自动智能切割，不再直接拒绝）"""
    text = await _read_text_limited(file)

    # 创建文件记录
    file_record = File(
        user_id=user_id,
        name=file.filename,
        content=text,
        status="parsing"
    )
    db.add(file_record)
    db.commit()
    db.refresh(file_record)

    # 预演切割方案：前端与审计都能看到「会切成几片、按什么边界切、为什么」
    plan = plan_split(
        text,
        target_lines=settings.SPLIT_TARGET_LINES,
        target_chars=settings.SPLIT_TARGET_CHARS,
        max_pieces=settings.SPLIT_MAX_PIECES,
        overlap_lines=settings.SPLIT_OVERLAP_LINES,
    )
    audit.log_event(
        db, "upload", actor="user", user_id=user_id, target_type="file",
        target_id=file_record.id, target_name=file.filename,
        summary=(f"上传《{file.filename}》：{plan['total_lines']} 行 / {plan['total_chars']} 字符"
                 + ("，将自动切割" if plan["needed"] else "，无需切割")),
        detail={
            "size_chars": len(text),
            "total_lines": plan["total_lines"],
            "need_split": plan["needed"],
            "pieces": summarize_pieces(plan),
            "limits": upload_limits(),
            "decision_basis": (
                f"切割阈值 {settings.SPLIT_TARGET_LINES} 行 / {settings.SPLIT_TARGET_CHARS} 字符；"
                f"实际 {plan['total_lines']} 行 → " + ("需要切割" if plan["needed"] else "无需切割")
            ),
        },
        commit=False,
    )
    db.commit()

    # 异步解析
    if background_tasks:
        background_tasks.add_task(parse_and_extract, file_record.id, user_id)
    else:
        parse_and_extract(file_record.id, user_id)

    return {
        "file_id": file_record.id,
        "name": file.filename,
        "size": len(text),
        "status": "parsing",
        "split": {
            "needed": plan["needed"],
            "pieces": summarize_pieces(plan),
            "message": describe_plan(plan),
        },
        "limits": upload_limits(),
        "message": ("文件已上传，正在解析" if not plan["needed"]
                    else f"文件已上传，将切割为 {len(plan['pieces'])} 片逐片解析"),
    }


@router.delete("/{file_id}")
def delete_file(file_id: int, user_id: int = 1, db: Session = Depends(get_db)):
    """删除文件及其关联的节点和连线"""
    file_record = db.query(File).filter_by(id=file_id, user_id=user_id).first()
    if not file_record:
        return {"ok": False, "message": "文件不存在"}

    deleted_nodes = _purge_file_nodes(db, file_id)
    db.delete(file_record)
    audit.log_event(
        db, "delete_file", actor="user", user_id=user_id, target_type="file",
        target_id=file_id, target_name=file_record.name,
        summary=f"删除文件《{file_record.name}》，连带清除 {deleted_nodes} 个知识点与相关连线、候选",
        detail={"deleted_nodes": deleted_nodes,
                "cascaded": ["nodes", "node_sources", "links", "isolate_blacklist",
                             "note_nodes", "knowledge_candidates"]},
        commit=False,
    )
    db.commit()

    return {
        "ok": True,
        "deleted_nodes": deleted_nodes,
        "message": f"文件 '{file_record.name}' 及其 {deleted_nodes} 个节点已删除"
    }


class FileSyncRequest(BaseModel):
    """本地文件夹笔记同步请求（模块1：本地为源 + 双写）"""
    user_id: int = 1
    source_path: str = ""          # 'ws:{workspaceId}:{relPath}' 幂等键
    name: str = ""
    content: str = ""


@router.post("/sync")
def sync_file(req: FileSyncRequest, db: Session = Depends(get_db)):
    """按 source_path 幂等登记/更新文件并（重新）解析。

    - 本地笔记首次同步 → 建 File 并解析出知识节点；
    - 本地笔记内容更新 → 清掉旧节点/连线后按新内容重新解析（全量 rebuild 该文件）。
    """
    if not req.source_path:
        return {"ok": False, "message": "缺少 source_path"}

    # 本地工作区同步同样走上限保护：超大笔记拒绝入库，避免拖垮服务
    max_chars = settings.MAX_UPLOAD_MB_HARD * 1024 * 1024
    if len(req.content or "") > max_chars:
        return {
            "ok": False,
            "message": (f"笔记内容超过 {settings.MAX_UPLOAD_MB_HARD}MB 上限，已跳过同步。")
        }

    file_record = (
        db.query(File)
        .filter_by(user_id=req.user_id, source_path=req.source_path)
        .first()
    )
    created = file_record is None

    if created:
        file_record = File(
            user_id=req.user_id,
            name=req.name,
            content=req.content,
            source_path=req.source_path,
            status="parsing"
        )
        db.add(file_record)
        db.commit()
        db.refresh(file_record)
    else:
        # 内容已变化的更新：先清旧节点，避免新旧两套并存
        file_record.name = req.name
        file_record.content = req.content
        file_record.status = "parsing"
        try:
            removed = _purge_file_nodes(db, file_record.id)
            db.commit()
        except Exception as exc:
            db.rollback()
            return {"ok": False, "message": f"旧节点清理失败：{exc}", "file_id": file_record.id}

    # 同步解析（笔记规模小，避免 background 双 session 竞态导致图谱闪烁）
    # parse_and_extract 内部已完成向量化与自动推理
    try:
        parse_and_extract(file_record.id, req.user_id)
    except Exception as exc:
        file_record.status = "error"
        db.commit()
        return {"ok": False, "message": f"解析失败：{exc}", "file_id": file_record.id}

    db.refresh(file_record)
    return {
        "ok": True,
        "file_id": file_record.id,
        "created": created,
        "name": file_record.name,
        "status": file_record.status,
        "node_count": file_record.node_count
    }


class FileRenameRequest(BaseModel):
    user_id: int = 1
    name: Optional[str] = None
    source_path: Optional[str] = None


@router.patch("/{file_id}")
def update_file_meta(
    file_id: int, req: FileRenameRequest, db: Session = Depends(get_db)
):
    """更新文件元数据（本地重命名后同步 name / source_path）"""
    file_record = (
        db.query(File).filter_by(id=file_id, user_id=req.user_id).first()
    )
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
    """获取用户的所有文件"""
    files = db.query(File).filter_by(user_id=user_id).order_by(File.uploaded_at.desc()).all()
    return {
        "files": [
            {
                "id": f.id,
                "name": f.name,
                "status": f.status,
                "node_count": f.node_count,
                "parse_note": f.parse_note,
                "size": len(f.content or ""),
                "uploaded_at": f.uploaded_at.isoformat() if f.uploaded_at else None
            }
            for f in files
        ]
    }


@router.get("/{file_id}/nodes")
def get_file_nodes(file_id: int, user_id: int = 1, db: Session = Depends(get_db)):
    """获取文件的所有节点"""
    nodes = db.query(Node).filter_by(file_id=file_id, user_id=user_id).all()
    return {
        "nodes": [
            {
                "id": n.id,
                "entity": n.entity,
                "title": n.title,
                "type": n.type,
                "description": n.description,
                "keywords": n.keywords or [],
                "entities": n.entities or [],
                "level": n.level,
                "domain": n.domain,
                "status": n.status
            }
            for n in nodes
        ]
    }