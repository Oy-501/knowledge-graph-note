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
from app.services import learn_anything
from loguru import logger

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


@router.get("/sources")
def concept_sources(entity: str, domain: str = "", limit: int = 8):
    """知识点的联网来源与视频讲解。

    与判定时的联网分开：判定只用一次检索保证速度，
    这里按需展开，合并多个搜索源，并附带视频站点的讲解链接。
    """
    from app.services import web_probe

    entity = (entity or "").strip()
    if not entity:
        raise AppError("缺少知识点名称", status_code=422, code="entity_required",
                       hint="传入 entity 参数，例如 entity=B+ 树")

    limit, _ = clamp_paging(limit, 0, max_limit=20, default_limit=8)
    suffix = ""
    if domain and domain not in ("general", "通用"):
        suffix = f" {domain}"

    web = web_probe.search_multi(f'"{entity}"{suffix}', limit=limit, expect=entity)
    sources = [
        {**r, "tier": web_probe.source_tier(r.get("url") or "")}
        for r in (web.get("results") or [])
    ]
    videos = web_probe.search_videos(entity, limit=3)
    return {
        "ok": True,
        "entity": entity,
        "online": web.get("online", False),
        "sources": sources,
        "videos": videos,
        "video_search": web_probe.video_search_links(entity),
        "references": web_probe.reference_links(entity),
        "reading": learn_anything.reading_for(entity, domain),
        "message": "" if web.get("online") else web.get("error", ""),
    }


@router.get("/node/{node_id}/sources")
def node_sources(node_id: int, db: Session = Depends(get_db)):
    """知识点详情页的来源、判定依据与视频讲解。

    详情页不经过候选列表，只能按 node_id 反查它对应的候选；
    没有候选（历史节点）时退回用节点标题检索。
    """
    from app.models.models import KnowledgeCandidate
    from app.services import web_probe

    node = db.query(Node).filter_by(id=node_id).first()
    if node is None:
        raise AppError("知识点不存在", status_code=404, code="node_not_found",
                       hint="它可能已被删除，或者链接指向了旧的节点 id。")

    cand = (db.query(KnowledgeCandidate)
            .filter_by(node_id=node_id)
            .order_by(KnowledgeCandidate.verdict_score.desc())
            .first())
    entity = ((cand.entity if cand else "") or node.title or "").strip()

    result = {
        "ok": True,
        "entity": entity,
        "decision": cand.verdict_decision if cand else "",
        "score": cand.verdict_score if cand else None,
        "reason": cand.verdict_reason if cand else "",
        "sources": web_probe.evidence_sources(
            entity, cand.verdict_evidence if cand else []),
        "videos": [],
        "references": web_probe.reference_links(entity),
        "video_search": web_probe.video_search_links(entity),
        "reading": learn_anything.reading_for(entity, getattr(node, "domain", "") or ""),
        "online": False,
    }
    if not entity:
        return result

    try:
        result["videos"] = web_probe.search_videos(entity, limit=3)
    except Exception as exc:  # 联网失败只降级，不影响详情展示
        logger.debug(f"视频检索失败 node={node_id}: {exc}")
    try:
        web = web_probe.search_multi(f'"{entity}"', limit=6, expect=entity)
        result["online"] = bool(web.get("online"))
        # 判定证据里没有来源时，用一次实时检索补上
        if not result["sources"] and web.get("results"):
            result["sources"] = [
                {"title": (r.get("title") or "")[:100],
                 "url": r.get("url") or "",
                 "provider": r.get("provider") or "",
                 "tier": web_probe.source_tier(r.get("url") or "")}
                for r in web["results"][:5] if r.get("url")
            ]
    except Exception as exc:
        logger.debug(f"来源检索失败 node={node_id}: {exc}")
    return result