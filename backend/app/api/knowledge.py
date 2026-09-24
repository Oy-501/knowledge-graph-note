"""知识校验与关联推理 API"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List, Optional, Any
from app.database import get_db
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
    """为新节点推理关联连线"""
    nodes = request.nodes
    weights = request.weights or {}
    threshold = request.threshold or 0.15

    if not nodes:
        return {"links": [], "message": "无节点可推理"}

    links = infer_links_batch(nodes, user_id, weights, threshold, db)
    return {"links": links, "count": len(links)}


@router.get("/search")
def search_knowledge(keyword: str, limit: int = 20, db: Session = Depends(get_db)):
    """搜索知识库中的知识点"""
    from app.models.models import KnowledgeBase, Node

    # 搜索知识库
    kb_results = db.query(KnowledgeBase).filter(
        KnowledgeBase.entity.ilike(f"%{keyword}%")
    ).limit(limit).all()

    # 搜索已有节点
    node_results = db.query(Node).filter(
        Node.entity.ilike(f"%{keyword}%"),
        Node.status == "active"
    ).limit(limit).all()

    return {
        "knowledge_base": [
            {"id": k.id, "entity": k.entity, "domain": k.domain, "definition": k.definition}
            for k in kb_results
        ],
        "nodes": [
            {"id": n.id, "entity": n.entity, "title": n.title, "level": n.level}
            for n in node_results
        ]
    }