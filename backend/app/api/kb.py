"""知识库 API：条目管理、文档理解导入、知识锚定匹配、本体图与知识关联

知识库是本系统的「知识权威源」——图谱建立在它之上，文件之间的关联由它决定。
"""
from collections import Counter, defaultdict
from typing import List, Optional

from fastapi import APIRouter, Depends, File as FastAPIFile, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.models import (
    KnowledgeBase, KbRelation, KbImport, File, FileKnowledgeProfile, FileKnowledgeLink, Node, Link,
)
from app.services.kb_index import KbIndex, build_relations_from_entries, load_index
from app.services.kb_import import understand_kb_document
from app.services import kb_link

router = APIRouter()


@router.get("/stats")
def kb_stats(user_id: int = 1, db: Session = Depends(get_db)):
    index = load_index(db)
    stats = index.stats()
    source_counter: Counter = Counter()
    canonical = set(index.entries.keys())
    seen_entities = set()
    for e in db.query(KnowledgeBase).all():
        if e.entity in canonical and e.entity not in seen_entities:
            seen_entities.add(e.entity)
            source_counter[e.source or "unknown"] += 1
    for r in db.query(KbRelation).all():
        source_counter["relation:" + (r.origin or "derived")] += 1
    profiles = db.query(FileKnowledgeProfile).all()
    file_total = db.query(File).filter_by(user_id=user_id).count()
    covered = len([p for p in profiles if (p.concept_count or 0) > 0])
    return {
        **stats, "entries": stats["entities"], "sources": dict(source_counter),
        "imports": db.query(KbImport).count(), "files": file_total,
        "files_covered": covered,
        "coverage_rate": round(covered / file_total, 4) if file_total else 0.0,
        "file_links": db.query(FileKnowledgeLink).count(),
        "kb_node_links": db.query(Link).filter(Link.source_file == kb_link.KB_SOURCE_TAG).count(),
        "avg_concepts_per_file": round(
            sum(p.concept_count or 0 for p in profiles) / len(profiles), 2
        ) if profiles else 0.0,
    }


@router.get("/entries")
def list_entries(keyword: str = "", domain: str = "", level: int = 0, limit: int = 50, offset: int = 0, db: Session = Depends(get_db)):
    query = db.query(KnowledgeBase)
    if keyword:
        like = f"%{keyword}%"
        query = query.filter(KnowledgeBase.entity.ilike(like))
    if domain:
        query = query.filter(KnowledgeBase.domain == domain)
    if level:
        query = query.filter(KnowledgeBase.level == level)
    total = query.count()
    rows = query.order_by(KnowledgeBase.id.desc()).offset(offset).limit(min(limit, 200)).all()
    rel_counter: Counter = Counter()
    for r in db.query(KbRelation).all():
        rel_counter[r.source_entity] += 1
    return {
        "total": total,
        "entries": [{
            "id": e.id, "entity": e.entity, "aliases": e.aliases or [],
            "domain": e.domain, "level": e.level,
            "definition": (e.definition or "")[:400],
            "source": e.source, "credibility": e.credibility,
            "related_terms": e.related_terms or [], "relation_count": rel_counter.get(e.entity, 0),
            "created_at": e.created_at.isoformat() if e.created_at else None,
        } for e in rows],
    }


class EntryPayload(BaseModel):
    entity: str
    aliases: List[str] = []
    domain: str = "general"
    level: int = 3
    definition: str = ""
    related_terms: List[str] = []
    credibility: int = 6


@router.post("/entries")
def create_entry(payload: EntryPayload, db: Session = Depends(get_db)):
    exists = db.query(KnowledgeBase).filter(KnowledgeBase.entity == payload.entity).first()
    if exists:
        return {"ok": False, "message": f"知识点「{payload.entity}」已存在", "id": exists.id}
    row = KnowledgeBase(
        entity=payload.entity, aliases=payload.aliases, domain=payload.domain,
        level=payload.level, definition=payload.definition, source="manual",
        credibility=payload.credibility, bridge_sentences=[], opposite_terms=[],
        related_terms=payload.related_terms,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    build_relations_from_entries(db)
    return {"ok": True, "id": row.id, "message": f"已新增知识点「{row.entity}」"}


@router.put("/entries/{entry_id}")
def update_entry(entry_id: int, payload: EntryPayload, db: Session = Depends(get_db)):
    row = db.query(KnowledgeBase).filter_by(id=entry_id).first()
    if not row:
        return {"ok": False, "message": "条目不存在"}
    row.entity = payload.entity
    row.aliases = payload.aliases
    row.domain = payload.domain
    row.level = payload.level
    row.definition = payload.definition
    row.related_terms = payload.related_terms
    row.credibility = payload.credibility
    db.commit()
    build_relations_from_entries(db)
    return {"ok": True, "message": f"已更新知识点「{row.entity}」"}


@router.delete("/entries/{entry_id}")
def delete_entry(entry_id: int, db: Session = Depends(get_db)):
    row = db.query(KnowledgeBase).filter_by(id=entry_id).first()
    if not row:
        return {"ok": False, "message": "条目不存在"}
    entity = row.entity
    db.query(KbRelation).filter(
        (KbRelation.source_entity == entity) | (KbRelation.target_entity == entity)
    ).delete(synchronize_session=False)
    db.delete(row)
    db.commit()
    return {"ok": True, "message": f"已删除知识点「{entity}」"}


@router.get("/relations")
def list_relations(entity: str = "", limit: int = 200, db: Session = Depends(get_db)):
    query = db.query(KbRelation)
    if entity:
        query = query.filter(
            (KbRelation.source_entity == entity) | (KbRelation.target_entity == entity)
        )
    rows = query.order_by(KbRelation.weight.desc()).limit(min(limit, 500)).all()
    return {"total": len(rows), "relations": [{
        "id": r.id, "source": r.source_entity, "target": r.target_entity,
        "relation_type": r.relation_type, "relation_label": r.relation_label,
        "weight": r.weight, "evidence": r.evidence, "origin": r.origin,
    } for r in rows]}


class RelationPayload(BaseModel):
    source_entity: str
    target_entity: str
    relation_type: str = "related"
    relation_label: str = "相关"
    weight: float = 0.6
    evidence: str = ""


@router.post("/relations")
def create_relation(payload: RelationPayload, db: Session = Depends(get_db)):
    dup = db.query(KbRelation).filter_by(
        source_entity=payload.source_entity, target_entity=payload.target_entity,
        relation_type=payload.relation_type,
    ).first()
    if dup:
        return {"ok": False, "message": "该关系已存在", "id": dup.id}
    row = KbRelation(**payload.model_dump(), origin="manual")
    db.add(row)
    db.commit()
    db.refresh(row)
    return {"ok": True, "id": row.id, "message": "关系已新增"}


@router.delete("/relations/{rel_id}")
def delete_relation(rel_id: int, db: Session = Depends(get_db)):
    row = db.query(KbRelation).filter_by(id=rel_id).first()
    if not row:
        return {"ok": False, "message": "关系不存在"}
    db.delete(row)
    db.commit()
    return {"ok": True, "message": "关系已删除"}


@router.get("/neighbors")
def kb_neighbors(entity: str, limit: int = 20, db: Session = Depends(get_db)):
    index = load_index(db)
    return {"entity": entity, "neighbors": index.neighbors(entity, limit=limit)}


@router.post("/upload")
async def upload_kb(file: UploadFile = FastAPIFile(...), user_id: int = 1, dry_run: bool = False, overwrite: bool = False, db: Session = Depends(get_db)):
    raw = await file.read()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        text = raw.decode("gbk", errors="replace")
    report = understand_kb_document(
        db, name=file.filename or "uploaded_kb", content=text,
        user_id=user_id, dry_run=dry_run, overwrite_definitions=overwrite,
    )
    return {"ok": True, "name": file.filename, "dry_run": dry_run, "report": report}


class PreviewPayload(BaseModel):
    text: str
    name: str = "未命名知识库"
    dry_run: bool = True
    overwrite: bool = False


@router.post("/preview")
def preview_kb(payload: PreviewPayload, user_id: int = 1, db: Session = Depends(get_db)):
    report = understand_kb_document(
        db, name=payload.name, content=payload.text, user_id=user_id,
        dry_run=payload.dry_run, overwrite_definitions=payload.overwrite,
    )
    return {"ok": True, "report": report}


@router.get("/imports")
def list_imports(limit: int = 20, db: Session = Depends(get_db)):
    rows = db.query(KbImport).order_by(KbImport.id.desc()).limit(min(limit, 100)).all()
    return {"imports": [{
        "id": r.id, "name": r.name, "format": r.format, "status": r.status,
        "entry_total": r.entry_total, "new_count": r.new_count, "merged_count": r.merged_count,
        "conflict_count": r.conflict_count, "relation_count": r.relation_count,
        "rejected_count": r.rejected_count,
        "summary": (r.report or {}).get("summary", ""),
        "created_at": r.created_at.isoformat() if r.created_at else None,
    } for r in rows]}


@router.get("/imports/{import_id}")
def get_import(import_id: int, db: Session = Depends(get_db)):
    row = db.query(KbImport).filter_by(id=import_id).first()
    if not row:
        return {"ok": False, "message": "记录不存在"}
    return {"ok": True, "import": {
        "id": row.id, "name": row.name, "format": row.format,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "report": row.report,
    }}


class MatchPayload(BaseModel):
    text: str
    limit: int = 30


@router.post("/match")
def kb_match(payload: MatchPayload, db: Session = Depends(get_db)):
    index = load_index(db)
    hits = index.scan(payload.text)
    counter = Counter(h["entity"] for h in hits)
    concepts = []
    for entity, count in counter.most_common(payload.limit):
        entry = index.entries.get(entity, {})
        sample = next(h for h in hits if h["entity"] == entity)
        concepts.append({
            "entity": entity, "count": count,
            "via_alias": any(h["via_alias"] for h in hits if h["entity"] == entity),
            "matched_text": sample["matched"],
            "level": entry.get("level"), "domain": entry.get("domain"),
            "definition": (entry.get("definition") or "")[:200],
            "start": sample["start"], "end": sample["end"],
        })
    covered = sum(h["end"] - h["start"] for h in hits)
    body = len("".join(payload.text.split())) or 1
    return {
        "matched": len(counter), "hits": len(hits),
        "coverage": round(min(1.0, covered / body), 4),
        "concepts": concepts,
        "uncovered": [] if hits else ["该文本未命中任何知识库知识点 —— 按知识边界规则，它不会参与关联"],
    }


@router.get("/graph")
def kb_graph(domain: str = "", keyword: str = "", limit: int = 150, db: Session = Depends(get_db)):
    query = db.query(KnowledgeBase)
    if domain:
        query = query.filter(KnowledgeBase.domain == domain)
    if keyword:
        query = query.filter(KnowledgeBase.entity.ilike(f"%{keyword}%"))
    rows = query.order_by(KnowledgeBase.level.asc()).limit(min(limit, 400)).all()
    names = {e.entity for e in rows}
    rels = db.query(KbRelation).all()
    links = [{
        "source": r.source_entity, "target": r.target_entity,
        "relation_type": r.relation_type, "relation_label": r.relation_label,
        "weight": r.weight, "evidence": r.evidence, "origin": r.origin,
    } for r in rels if r.source_entity in names and r.target_entity in names]
    linked = {l["source"] for l in links} | {l["target"] for l in links}
    return {
        "nodes": [{
            "id": e.entity, "entity": e.entity, "domain": e.domain, "level": e.level or 3,
            "definition": (e.definition or "")[:200], "aliases": e.aliases or [],
            "source": e.source, "degree": 0,
            "isolated": e.entity not in linked,
            "credibility": e.credibility or 5,
        } for e in rows],
        "links": links,
        "truncated": len(names) >= limit,
        "total_entries": db.query(KnowledgeBase).count(),
    }


@router.get("/files")
def kb_files(threshold: float = 0.0, user_id: int = 1, db: Session = Depends(get_db)):
    files = {f.id: f for f in db.query(File).filter_by(user_id=user_id).all()}
    profiles = {p.file_id: p for p in db.query(FileKnowledgeProfile).all()}
    links = db.query(FileKnowledgeLink).filter_by(user_id=user_id).all()
    def _top_concepts(p: FileKnowledgeProfile):
        return [{"entity": c.get("entity"), "weight": c.get("weight"), "count": c.get("count")}
                for c in (p.concepts or [])[:12]]
    return {
        "files": [{
            "file_id": fid, "name": files[fid].name, "node_count": files[fid].node_count,
            "anchor_count": profiles[fid].anchor_count if fid in profiles else 0,
            "concept_count": profiles[fid].concept_count if fid in profiles else 0,
            "coverage": profiles[fid].coverage if fid in profiles else 0.0,
            "domains": profiles[fid].domains if fid in profiles else {},
            "levels": profiles[fid].levels if fid in profiles else {},
            "top_concepts": _top_concepts(profiles[fid]) if fid in profiles else [],
        } for fid in files],
        "links": [{
            "id": l.id, "source_file_id": l.source_file_id, "target_file_id": l.target_file_id,
            "source_name": files.get(l.source_file_id).name if files.get(l.source_file_id) else "",
            "target_name": files.get(l.target_file_id).name if files.get(l.target_file_id) else "",
            "kb_similarity": l.kb_similarity, "direct_score": l.direct_score,
            "bridge_score": l.bridge_score, "domain_score": l.domain_score,
            "shared_concepts": l.shared_concepts or [], "bridges": l.bridges or [],
            "method": l.method,
        } for l in links if l.kb_similarity >= threshold],
        "threshold": threshold,
    }


@router.get("/file/{file_id}")
def kb_file_detail(file_id: int, db: Session = Depends(get_db)):
    index = load_index(db)
    file_row = db.query(File).filter_by(id=file_id).first()
    if not file_row:
        return {"ok": False, "message": "文件不存在"}
    prof_row = db.query(FileKnowledgeProfile).filter_by(file_id=file_id).first()
    if not prof_row:
        fresh = index.build_profile(file_row.content or "")
        concepts, anchor_count = fresh["concepts"], fresh["anchor_count"]
        coverage, concept_count = fresh["coverage"], fresh["concept_count"]
    else:
        concepts = prof_row.concepts or []
        anchor_count, coverage = prof_row.anchor_count or 0, prof_row.coverage or 0.0
        concept_count = prof_row.concept_count or 0
    related_rows = db.query(FileKnowledgeLink).filter(
        (FileKnowledgeLink.source_file_id == file_id) |
        (FileKnowledgeLink.target_file_id == file_id)
    ).order_by(FileKnowledgeLink.kb_similarity.desc()).limit(10).all()
    peer_files = {f.id: f.name for f in db.query(File).all()}
    return {
        "ok": True,
        "file": {"file_id": file_id, "name": file_row.name, "node_count": file_row.node_count},
        "profile": {
            "anchor_count": anchor_count, "concept_count": concept_count, "coverage": coverage,
            "domains": prof_row.domains if prof_row else {},
            "levels": prof_row.levels if prof_row else {},
        },
        "concepts": [{
            **c, "neighbors": index.neighbors(c.get("entity"), limit=6),
        } for c in concepts[:30]],
        "related_files": [{
            "file_id": other_id, "name": peer_files.get(other_id, ""),
            "kb_similarity": l.kb_similarity, "shared_concepts": l.shared_concepts or [],
            "bridges": (l.bridges or [])[:8],
            "direct_score": l.direct_score, "bridge_score": l.bridge_score,
            "domain_score": l.domain_score,
        } for l, other_id in [
            (l, l.target_file_id if l.source_file_id == file_id else l.source_file_id)
            for l in related_rows
        ]],
    }


class RebuildPayload(BaseModel):
    user_id: int = 1
    threshold: float = 0.15
    node_threshold: float = 0.15
    rebuild_relations: bool = True


@router.post("/rebuild")
def kb_rebuild(payload: RebuildPayload, db: Session = Depends(get_db)):
    result = {}
    if payload.rebuild_relations:
        result["relations"] = build_relations_from_entries(db)
    result.update(kb_link.kb_rebuild_all(
        db, user_id=payload.user_id,
        threshold=payload.threshold, node_threshold=payload.node_threshold,
    ))
    return {"ok": True, "result": result, "message": "知识库关联重建完成"}
