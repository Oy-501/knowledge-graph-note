"""关联推理服务：四维加权融合打分 + 关系分类"""
import json
from typing import List, Dict, Optional
from loguru import logger
from app.models.models import Node, Link, NodeSource, KnowledgeBase
from app.services.vector_engine import (
    cosine_similarity, jaccard_similarity, encode, embed_to_db
)


def infer_links_for_new_file(file_id: int, user_id: int, db):
    new_nodes = db.query(Node).filter_by(file_id=file_id, user_id=user_id).all()
    if not new_nodes:
        return
    existing_nodes = db.query(Node).filter(
        Node.user_id == user_id,
        Node.file_id != file_id,
        Node.status == "active"
    ).all()
    new_nodes_dict = [_node_to_dict(n) for n in new_nodes]
    existing_nodes_dict = [_node_to_dict(n) for n in existing_nodes]
    links = infer_links_batch(new_nodes_dict, user_id, {}, 0.15, db, existing_nodes=existing_nodes_dict)
    count = 0
    for link_data in links:
        source_id = link_data["source"]
        target_id = link_data["target"]
        if source_id == target_id:
            continue
        existing = db.query(Link).filter(
            (Link.source_id == source_id) & (Link.target_id == target_id) |
            (Link.source_id == target_id) & (Link.target_id == source_id)
        ).first()
        if existing:
            continue
        link = Link(
            source_id=source_id, target_id=target_id,
            relation_type=link_data.get("relation_type", "related"),
            relation_label=link_data.get("relation_label", "相关"),
            score=link_data.get("score", 0.3),
            final_weight=link_data.get("final_weight", link_data.get("score", 0.3)),
            evidence=link_data.get("evidence", ""),
            source_text=link_data.get("source_text", ""),
            source_file=link_data.get("source_file", ""),
            auto_generated=True,
            time_bridge=True
        )
        db.add(link)
        count += 1
    db.commit()
    logger.info(f"Inferred {count} links for file {file_id}")


def infer_links_batch(new_nodes: List[Dict], user_id: int, weights: Dict, threshold: float, db, existing_nodes: Optional[List[Dict]] = None) -> List[Dict]:
    if existing_nodes is None:
        existing = db.query(Node).filter(Node.user_id == user_id, Node.status == "active").all()
        existing_nodes = [_node_to_dict(n) for n in existing]
    alpha = weights.get("alpha", 0.15)
    beta = weights.get("beta", 0.25)
    gamma = weights.get("gamma", 0.50)
    delta = weights.get("delta", 0.10)
    th = threshold or 0.15
    links = []
    for new_node in new_nodes:
        for old_node in existing_nodes:
            if new_node.get("id") == old_node.get("id"):
                continue
            if not can_connect(new_node, old_node):
                continue
            score, detail = calculate_score(new_node, old_node, alpha, beta, gamma, delta, db)
            if score >= th:
                rel_type = classify_relation(new_node, old_node, score, detail, db)
                evidence = get_evidence(new_node, old_node, detail)
                links.append({
                    "source": new_node["id"], "target": old_node["id"],
                    "relation_type": rel_type["type"], "relation_label": rel_type["label"],
                    "score": round(score, 4), "final_weight": round(score, 4),
                    "evidence": evidence, "source_text": detail.get("source_text", ""),
                    "source_file": detail.get("source_file", ""),
                    "auto_generated": True, "time_bridge": True
                })
    return links


def calculate_score(node_a: Dict, node_b: Dict, alpha: float, beta: float, gamma: float, delta: float, db) -> tuple:
    detail = {}
    if (node_a.get("id") != node_b.get("id")
            and node_a.get("entity")
            and node_a.get("entity") == node_b.get("entity")):
        detail["source_text"] = f"同名实体「{node_a.get('entity')}」跨文件重复出现，等待同名合并"
        return 0.0, detail
    level_a = node_a.get("level", 3)
    level_b = node_b.get("level", 3)
    if abs(level_a - level_b) >= 3:
        has_bridge = check_corpus_bridge(node_a, node_b, db)
        if not has_bridge:
            return 0.0, detail
    kw_a = node_a.get("keywords", [])
    kw_b = node_b.get("keywords", [])
    sim_text = jaccard_similarity(kw_a, kw_b)
    detail["sim_text"] = sim_text
    text_a = (node_a.get("description") or "") + " " + " ".join(node_a.get("entities", []))
    text_b = (node_b.get("description") or "") + " " + " ".join(node_b.get("entities", []))
    sim_vector = 0.0
    try:
        vec_a = json.loads(node_a.get("embedding", "[]")) if isinstance(node_a.get("embedding"), str) else node_a.get("embedding", [])
        vec_b = json.loads(node_b.get("embedding", "[]")) if isinstance(node_b.get("embedding"), str) else node_b.get("embedding", [])
        if vec_a and vec_b:
            sim_vector = cosine_similarity(vec_a, vec_b)
    except (json.JSONDecodeError, TypeError):
        pass
    detail["sim_vector"] = sim_vector
    sim_corpus = check_corpus_bridge_score(node_a, node_b, db)
    detail["sim_corpus"] = sim_corpus
    sim_topology = 0.0
    detail["sim_topology"] = sim_topology
    score = alpha * sim_text + beta * sim_vector + gamma * sim_corpus + delta * sim_topology
    return min(1.0, score), detail


def can_connect(node_a: Dict, node_b: Dict) -> bool:
    if node_a.get("id") == node_b.get("id"):
        return False
    if node_a.get("file_id") and node_b.get("file_id") and node_a["file_id"] == node_b["file_id"]:
        return True
    if (node_a.get("group_id") and node_b.get("group_id") and
        node_a["group_id"] == node_b["group_id"] and node_a["group_id"] != "default"):
        return True
    t_a = node_a.get("upload_time", 0)
    t_b = node_b.get("upload_time", 0)
    if t_a > 0 and t_b > 0 and abs(t_a - t_b) < 7 * 24 * 3600:
        return True
    return False


def check_corpus_bridge(node_a: Dict, node_b: Dict, db) -> bool:
    score = check_corpus_bridge_score(node_a, node_b, db)
    return score > 0


def check_corpus_bridge_score(node_a: Dict, node_b: Dict, db) -> float:
    try:
        entities_a = set(node_a.get("entities", []) + node_a.get("keywords", []))
        entities_b = set(node_b.get("entities", []) + node_b.get("keywords", []))
        if not entities_a or not entities_b:
            return 0.0
        kb_entries = db.query(KnowledgeBase).filter(
            KnowledgeBase.entity.in_(list(entities_a | entities_b))
        ).all()
        if not kb_entries:
            return 0.0
        bridge_count = 0
        for kb in kb_entries:
            related = set(kb.related_terms or [])
            related_aliases = set()
            for a in (kb.aliases or []):
                related_aliases.add(a)
            if (entities_a & related) or (entities_a & related_aliases):
                bridge_count += 1
            if (entities_b & related) or (entities_b & related_aliases):
                bridge_count += 1
        if bridge_count > 0:
            return min(0.8, bridge_count * 0.2)
    except Exception as e:
        logger.warning(f"Corpus bridge check failed: {e}")
    return 0.0


def classify_relation(node_a: Dict, node_b: Dict, score: float, detail: Dict, db) -> Dict:
    level_a = node_a.get("level", 3)
    level_b = node_b.get("level", 3)
    diff = level_a - level_b
    if diff == 1:
        return {"type": "prerequisite", "label": "前置知识"}
    elif diff == -1:
        return {"type": "implementation", "label": "实现关系"}
    elif diff == 0:
        if detail.get("sim_vector", 0) > 0.8:
            return {"type": "extension", "label": "扩展延伸"}
        elif detail.get("sim_corpus", 0) > 0.3:
            return {"type": "theory", "label": "理论关联"}
        else:
            return {"type": "related", "label": "相关"}
    else:
        return {"type": "related", "label": "相关"}


def get_evidence(node_a: Dict, node_b: Dict, detail: Dict) -> str:
    parts = []
    if detail.get("sim_text", 0) > 0.3:
        parts.append(f"关键词重合度 {detail['sim_text']:.2f}")
    if detail.get("sim_vector", 0) > 0.6:
        parts.append(f"语义相似度 {detail['sim_vector']:.2f}")
    if detail.get("sim_corpus", 0) > 0:
        parts.append(f"知识库桥接")
    return "; ".join(parts) if parts else "弱关联"


def _node_to_dict(node: Node) -> Dict:
    return {
        "id": node.id, "entity": node.entity, "title": node.title,
        "description": node.description or "", "keywords": node.keywords or [],
        "entities": node.entities or [], "level": node.level or 3,
        "domain": node.domain or "", "file_id": node.file_id,
        "group_id": node.group_id or "default", "upload_time": node.upload_time or 0,
        "embedding": node.embedding, "isolate_blacklist": node.isolate_blacklist or []
    }
