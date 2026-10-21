"""知识校验与关联推理 API"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List, Optional, Any
from app.database import get_db
from app.models.models import Node
from app.services.errors import AppError, clamp_paging, escape_like
from app.services.search import (node_references, search_knowledge_base,
                                 search_nodes, search_notes)
from app.services.validator import validate_content, summarize, split_sentence_ranges
from app.services.inference import infer_links_batch

router = APIRouter()


class ValidateRequest(BaseModel):
    content: str
    existing_nodes: Optional[List[dict]] = None


class InferNode(BaseModel):
    id: Any
    title: str = ""
    entity: str = ""
    description: str = ""
    keywords: List[str] = []
    entities: List[str] = []
    level: int = 3
    domain: str = ""
    file_id: Any = None
    group_id: str = "default"


class InferRequest(BaseModel):
    nodes: List[dict]
    weights: Optional[dict] = None
    threshold: Optional[float] = None


class SearchRequest(BaseModel):
    keyword: str
    limit: int = 20


@router.post("/validate")
def validate_knowledge(request: ValidateRequest, user_id: int = 1, db: Session = Depends(get_db)):
    """校验笔记内容的知识准确性（v2：7 类 × 4 级，返回带全文偏移的 issues）"""
    if not request.content or not request.content.strip():
        return {
            "passed": True,
            "can_force_save": True,
            "issues": [], "results": [], "errors": [], "warnings": [],
            "summary": {
                "total": 0, "passed": 0, "errors": 0, "warnings": 0,
                "critical": 0, "major": 0, "minor": 0, "info": 0,
                "accuracy": 100
            },
            "accuracy_score": 1.0
        }

    issues = validate_content(request.content, db)
    errors = [i for i in issues if i['severity'] in ('critical', 'major')]
    warnings = [i for i in issues if i['severity'] in ('minor', 'info')]
    sentence_count = len(split_sentence_ranges(request.content))
    summary = summarize(issues, sentence_count=sentence_count)
    accuracy = summary['accuracy'] / 100.0

    return {
        "passed": len(errors) == 0,
        "can_force_save": not any(i['severity'] == 'critical' for i in issues),
        "issues": issues,
        "results": issues,  # 兼容旧字段名
        "errors": errors,
        "warnings": warnings,
        "summary": summary,
        "accuracy_score": round(accuracy, 3)
    }


@router.post("/infer")
def infer_links(request: InferRequest, user_id: int = 1, db: Session = Depends(get_db)):
    """为新节点推理关联连线（带节点数上限，避免超大请求拖死服务）"""
    from app.config import settings

    nodes = request.nodes
    weights = request.weights or {}
    threshold = request.threshold or 0.15

    if not nodes:
        return {"links": [], "message": "无节点可推理"}

    truncated = False
    if len(nodes) > settings.MAX_NODES_PER_FILE:
        nodes = nodes[:settings.MAX_NODES_PER_FILE]
        truncated = True

    links = infer_links_batch(nodes, user_id, weights, threshold, db)
    return {
        "links": links,
        "count": len(links),
        "truncated": truncated,
        "message": (f"节点数超过上限 {settings.MAX_NODES_PER_FILE}，已截断后推理"
                    if truncated else ""),
    }


@router.get("/search")
def search_knowledge(keyword: str = "", limit: int = 10, user_id: int = 1,
                     db: Session = Depends(get_db)):
    """跨「知识库 / 图谱节点 / 笔记」检索。

    旧版只在 entity 上做 ILIKE：别名、定义、节点标题、笔记正文都不参与，
    于是「搜一个同义词就什么都搜不到」。
    现在三段都参与，并标注命中来源（实体 / 别名 / 定义）。
    返回键 `knowledge_base` / `nodes` 保持原样，新增 `notes` 与 `total`。
    """
    key = (keyword or "").strip()
    limit, _ = clamp_paging(limit, 0, max_limit=50, default_limit=10)
    if not key:
        # 空关键词不能走 ILIKE '%%' —— 那等于把整库倒出来
        return {"keyword": "", "knowledge_base": [], "nodes": [], "notes": [], "total": 0}

    kb_rows = search_knowledge_base(db, key, limit)
    node_rows = search_nodes(db, key, limit)
    note_rows, note_total = search_notes(db, key, user_id=user_id, limit=limit, offset=0)
    return {
        "keyword": key,
        "knowledge_base": kb_rows,
        "nodes": node_rows,
        "notes": note_rows,
        "total": len(kb_rows) + len(node_rows) + note_total,
    }


@router.get("/node/{node_id}/notes")
def node_notes(node_id: int, user_id: int = 1, limit: int = 30,
               db: Session = Depends(get_db)):
    """反向链接：哪些笔记写过这个知识点。

    分 `linked`（显式关联）与 `mentioned`（正文提到但没连），
    后者是补齐关联最快的地方。
    """
    node = db.query(Node).filter_by(id=node_id).first()
    if node is None:
        raise AppError("知识点不存在", status_code=404, code="node_not_found",
                       hint="它可能已被删除，或者链接指向了旧的节点 id。")
    limit, _ = clamp_paging(limit, 0, max_limit=100, default_limit=30)
    return {"ok": True, **node_references(db, node, user_id=user_id, limit=limit)}