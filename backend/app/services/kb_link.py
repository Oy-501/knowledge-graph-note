"""基于知识库的关联引擎

与「文本语义相似」本质不同的三条规则：

  1. 先锚定，后关联：文档节点先锚定到知识库知识点，没被知识库覆盖的内容不参与关联。
  2. 关联靠知识，不靠字面：两个知识点关联，要么命中同一个知识库条目（同一知识点），
     要么在知识库关系图上存在通路（1 跳/2 跳桥接），字面像但知识库不认的一律不连。
  3. 文件相似度 = 知识画像的向量化比较：由知识库概念空间给出，并附带可下钻的证据
     （共享了哪些知识点、经由哪些关系桥接、领域层级是否一致）。

产物：
  - file_knowledge_profiles  文件知识画像
  - file_knowledge_links     文件-文件知识关联（带证据）
  - links（semantic_bridge=True, source_file='知识库'）  节点级知识锚定关联
"""
from collections import Counter, defaultdict
from typing import Dict, List, Optional

from loguru import logger

from app.config import settings

KB_SOURCE_TAG = "知识库"

# 大图谱保护：文件两两比较与节点级锚定连线都要限量，否则文件/节点一多就会卡死
MAX_FILES_FOR_LINKING = 150
MAX_FILE_LINK_SECONDS = 15.0

# 知识库关系类型 → 图谱关系类型（复用前端 8+1 类关系配色）
_RELATION_MAP = {
    "equivalent": ("equivalent", "等价知识点"),
    "包含": ("theory", "包含于理论"),
    "属于": ("theory", "属于理论"),
    "prerequisite": ("prerequisite", "前置知识"),
    "前置": ("prerequisite", "前置知识"),
    "定义": ("theory", "定义来源"),
    "对比": ("comparison", "对比关系"),
    "举例": ("application", "应用实例"),
    "implementation": ("implementation", "实现关系"),
    "bridge": ("bridged", "知识库桥接"),
    "derived": ("bridged", "知识库桥接"),
    "related": ("related", "相关知识"),
}


def _map_relation(kb_type: str):
    return _RELATION_MAP.get(kb_type or "related", ("related", "相关知识"))


def _node_text(node) -> str:
    return " ".join(filter(None, [
        node.title or "", node.entity or "",
        node.description or "", node.content or "",
        " ".join(node.keywords or []),
    ]))


def _anchors_of(node, index) -> Dict[str, int]:
    """节点文本 → {知识库知识点: 命中次数}"""
    return dict(Counter(h["entity"] for h in index.scan(_node_text(node))))


# ---------------------------------------------------------------- 锚定


def apply_kb_anchoring(db, file_id: int, user_id: int = 1, index=None, persist: bool = True) -> Dict:
    """把文件的节点锚定到知识库知识点：补 entities、以知识库为准校正领域/层级、写来源证据。"""
    from app.models.models import Node, NodeSource
    from app.services.kb_index import load_index
    from app.services.parser import get_level_label

    index = index or load_index(db)
    nodes = db.query(Node).filter_by(file_id=file_id, user_id=user_id).all()
    anchored_nodes, anchor_hits = 0, 0

    for node in nodes:
        anchors = _anchors_of(node, index)
        if not anchors:
            continue
        anchor_hits += sum(anchors.values())
        anchored_nodes += 1

        kb_entities = [e for e, _ in sorted(anchors.items(), key=lambda kv: -kv[1])][:8]
        old = [e for e in (node.entities or []) if e not in kb_entities]
        node.entities = (kb_entities + old)[:15]

        top_entity = kb_entities[0]
        entry = index.entries.get(top_entity, {})
        if anchors[top_entity] >= 2:
            kb_level = entry.get("level") or node.level
            node.level = kb_level
            node.level_label = get_level_label(kb_level)
            kb_domain = entry.get("domain") or ""
            if kb_domain and kb_domain != "general":
                node.domain = kb_domain

        if persist:
            exists = db.query(NodeSource).filter_by(node_id=node.id, source_type="kb").first()
            if not exists:
                parts = []
                for ent in kb_entities[:5]:
                    d = (index.entries.get(ent, {}).get("definition") or "")[:80]
                    parts.append(f"{ent}：{d}" if d else ent)
                db.add(NodeSource(
                    node_id=node.id, source_type="kb", source_id=file_id,
                    paragraph="知识库锚定｜" + "；".join(parts),
                    confidence=round(min(1.0, anchors[kb_entities[0]] / 3.0), 2),
                ))

    if persist:
        db.commit()
    logger.info(f"文件 {file_id} 知识库锚定：{anchored_nodes} 个节点、{anchor_hits} 次命中")
    return {"file_id": file_id, "anchored_nodes": anchored_nodes, "anchor_hits": anchor_hits,
            "total_nodes": len(nodes)}


# ---------------------------------------------------------------- 画像


def profile_file(db, file_id: int, user_id: int = 1, index=None, persist: bool = True) -> Dict:
    """构建/更新单个文件的知识画像"""
    from app.models.models import File, FileKnowledgeProfile
    from app.services.kb_index import load_index

    index = index or load_index(db)
    file_row = db.query(File).filter_by(id=file_id).first()
    if not file_row:
        return {}
    prof = index.build_profile(file_row.content or "")

    if persist:
        row = db.query(FileKnowledgeProfile).filter_by(file_id=file_id).first()
        if not row:
            row = FileKnowledgeProfile(file_id=file_id, user_id=user_id)
            db.add(row)
        row.user_id = user_id
        row.concepts = prof["concepts"]
        row.domains = prof["domains"]
        row.levels = prof["levels"]
        row.anchor_count = prof["anchor_count"]
        row.concept_count = prof["concept_count"]
        row.coverage = prof["coverage"]
        from datetime import datetime
        row.updated_at = datetime.utcnow()
        db.commit()

    return {"file_id": file_id, "name": file_row.name, **prof}


def build_profiles(db, user_id: int = 1, index=None) -> Dict:
    """为全部文件重建知识画像"""
    from app.models.models import File
    from app.services.kb_index import load_index

    index = index or load_index(db)
    files = db.query(File).filter_by(user_id=user_id).all()
    covered = 0
    for f in files:
        info = profile_file(db, f.id, user_id, index=index, persist=True)
        if info.get("concept_count"):
            covered += 1
    return {"files": len(files), "covered": covered}


# ---------------------------------------------------------------- 文件-文件知识关联


def link_files(db, user_id: int = 1, threshold: float = 0.15, index=None) -> Dict:
    """按知识画像计算文件-文件知识关联（不是语义相似度）

    性能保护：文件两两比较是 O(n²)，文件很多时限制参与比较的文件数并设时间预算。
    """
    import time
    from app.models.models import File, FileKnowledgeProfile, FileKnowledgeLink
    from app.services.kb_index import load_index

    index = index or load_index(db)
    files = {f.id: f for f in db.query(File).filter_by(user_id=user_id).all()}
    profiles = {p.file_id: {"concepts": p.concepts or [], "domains": p.domains or {},
                            "levels": p.levels or {}} for p in db.query(FileKnowledgeProfile).all()}

    db.query(FileKnowledgeLink).filter_by(user_id=user_id).delete(synchronize_session=False)
    db.commit()

    ids = sorted(f for f in files if profiles.get(f))
    total_ids = len(ids)
    skipped = 0
    if total_ids > MAX_FILES_FOR_LINKING:
        # 只比较知识点最多的那批文件（画像为空/极小的文件本来就连不出东西）
        ids.sort(key=lambda fid: -len(profiles[fid]["concepts"]))
        ids = ids[:MAX_FILES_FOR_LINKING]
        skipped = total_ids - len(ids)
        logger.warning(f"文件数 {total_ids} 超过比较上限 {MAX_FILES_FOR_LINKING}，"
                       f"仅比较知识点最多的 {len(ids)} 个文件")

    created, scored, truncated = 0, 0, False
    deadline = time.monotonic() + MAX_FILE_LINK_SECONDS
    for i, fid_a in enumerate(ids):
        for fid_b in ids[i + 1:]:
            scored += 1
            if scored % 200 == 0 and time.monotonic() > deadline:
                truncated = True
                break
            sim = index.similarity(profiles[fid_a], profiles[fid_b])
            if sim["kb_similarity"] < threshold:
                continue
            db.add(FileKnowledgeLink(
                user_id=user_id, source_file_id=fid_a, target_file_id=fid_b,
                kb_similarity=sim["kb_similarity"], direct_score=sim["direct_score"],
                bridge_score=sim["bridge_score"], domain_score=sim["domain_score"],
                shared_concepts=sim["shared_concepts"], bridges=sim["bridges"],
                method="kb_space",
            ))
            created += 1
        if truncated:
            break
    db.commit()
    logger.info(f"文件知识关联：比较 {scored} 对，落库 {created} 条（阈值 {threshold}）"
                f"{'，触发时间预算提前结束' if truncated else ''}")
    return {"pairs_scored": scored, "links": created, "threshold": threshold,
            "skipped_files": skipped, "truncated": truncated}


def link_files_for(db, file_id: int, user_id: int = 1, threshold: float = 0.15, index=None) -> Dict:
    """增量：只更新与该文件相关的知识关联"""
    from app.models.models import File, FileKnowledgeProfile, FileKnowledgeLink
    from app.services.kb_index import load_index

    index = index or load_index(db)
    profiles = {p.file_id: {"concepts": p.concepts or [], "domains": p.domains or {},
                            "levels": p.levels or {}} for p in db.query(FileKnowledgeProfile).all()}
    if not profiles.get(file_id):
        return {"pairs_scored": 0, "links": 0}

    others = [fid for fid in profiles if fid != file_id]
    db.query(FileKnowledgeLink).filter(
        FileKnowledgeLink.user_id == user_id,
        (FileKnowledgeLink.source_file_id == file_id) | (FileKnowledgeLink.target_file_id == file_id),
    ).delete(synchronize_session=False)
    db.commit()

    created = 0
    for fid in others:
        sim = index.similarity(profiles[file_id], profiles[fid])
        if sim["kb_similarity"] < threshold:
            continue
        a, b = sorted((file_id, fid))
        db.add(FileKnowledgeLink(
            user_id=user_id, source_file_id=a, target_file_id=b,
            kb_similarity=sim["kb_similarity"], direct_score=sim["direct_score"],
            bridge_score=sim["bridge_score"], domain_score=sim["domain_score"],
            shared_concepts=sim["shared_concepts"], bridges=sim["bridges"],
            method="kb_space",
        ))
        created += 1
    db.commit()
    return {"pairs_scored": len(others), "links": created}


# ---------------------------------------------------------------- 节点级知识关联


def link_nodes_by_kb(
    db, user_id: int = 1, threshold: float = 0.15,
    index=None, only_file_id: Optional[int] = None, max_nodes_per_concept: int = 6,
) -> Dict:
    """节点级关联：只有被知识库锚定的知识点之间才连线。

    - 同一知识点（同一 KB 条目）→ 等价知识点
    - 知识库关系边两端        → 按 KB 关系类型映射（前置/理论/对比/桥接…）
    """
    from app.models.models import Node, Link, File
    from app.services.kb_index import load_index

    index = index or load_index(db)
    nodes = db.query(Node).filter_by(user_id=user_id, status="active").all()
    if not nodes:
        return {"same_concept": 0, "bridged": 0, "total": 0}

    # 节点规模保护：几万节点两两成对会直接把内存与数据库拖死
    capped = False
    if len(nodes) > settings.MAX_NODES_FOR_KB_LINK:
        nodes = sorted(nodes, key=lambda n: -len(n.entities or []))[:settings.MAX_NODES_FOR_KB_LINK]
        capped = True
        logger.warning(f"节点数超过 {settings.MAX_NODES_FOR_KB_LINK}，"
                       f"仅对锚定知识点最多的前 {settings.MAX_NODES_FOR_KB_LINK} 个节点做知识锚定连线")

    anchors: Dict[int, Dict[str, int]] = {}
    for n in nodes:
        a = _anchors_of(n, index)
        if a:
            anchors[n.id] = a
    if not anchors:
        return {"same_concept": 0, "bridged": 0, "total": 0}

    nodes_by_id = {n.id: n for n in nodes}
    # 概念 → 该概念下的代表节点（每个文件只留命中最强的一个，避免同文件内堆叠）
    concept_nodes: Dict[str, List[tuple]] = defaultdict(list)
    for nid, a in anchors.items():
        for ent, cnt in a.items():
            concept_nodes[ent].append((nid, cnt))

    existing_pairs = set()
    for l in db.query(Link).filter(
        (Link.source_id.in_(list(nodes_by_id))) | (Link.target_id.in_(list(nodes_by_id)))
    ).all():
        existing_pairs.add(frozenset((l.source_id, l.target_id)))

    new_links: List[Dict] = []

    def _pick(entries: List[tuple]) -> List[tuple]:
        """每文件取命中最强者，按命中次数降序"""
        best: Dict[int, tuple] = {}
        for nid, cnt in entries:
            fid = nodes_by_id[nid].file_id
            if fid not in best or best[fid][1] < cnt:
                best[fid] = (nid, cnt)
        return sorted(best.values(), key=lambda x: -x[1])[:max_nodes_per_concept]

    def _add(a_id, b_id, kb_type, score, evidence, source_text):
        if a_id == b_id:
            return
        pair = frozenset((a_id, b_id))
        if pair in existing_pairs:
            return
        if only_file_id is not None and nodes_by_id[a_id].file_id != only_file_id and nodes_by_id[b_id].file_id != only_file_id:
            return
        existing_pairs.add(pair)
        rel_type, rel_label = _map_relation(kb_type)
        new_links.append({
            "source_id": a_id, "target_id": b_id, "relation_type": rel_type,
            "relation_label": rel_label, "score": round(score, 4),
            "evidence": evidence, "source_text": source_text,
        })

    # 1) 同一知识点 → 等价知识点
    same_concept = 0
    for ent, entries in concept_nodes.items():
        picked = _pick(entries)
        if len(picked) < 2:
            continue
        entry = index.entries.get(ent, {})
        definition = (entry.get("definition") or "")[:200]
        for i in range(len(picked)):
            for j in range(i + 1, len(picked)):
                (nid_a, ca), (nid_b, cb) = picked[i], picked[j]
                score = min(0.9, 0.5 + 0.1 * min(4, ca + cb))
                if score < threshold:
                    continue
                before = len(new_links)
                _add(nid_a, nid_b, "equivalent", score,
                     f"两个知识点均锚定知识库条目「{ent}」",
                     f"知识库定义：{definition}" if definition else ent)
                if len(new_links) > before:
                    same_concept += 1

    # 2) 知识库关系边 → 跨知识点关联
    bridged = 0
    for (ent_a, ent_b), detail in list(index.rel_detail.items()):
        if ent_a not in concept_nodes or ent_b not in concept_nodes:
            continue
        picked_a, picked_b = _pick(concept_nodes[ent_a]), _pick(concept_nodes[ent_b])
        rw = float(detail.get("weight") or 0.5)
        evidence = detail.get("evidence") or f"知识库关系：{ent_a} —{detail.get('relation_type')}— {ent_b}"
        pairs = 0
        for nid_a, ca in picked_a:
            for nid_b, cb in picked_b:
                if pairs >= 20:
                    break
                score = min(1.0, 0.35 * rw + 0.12 * min(4, ca + cb))
                if score < threshold:
                    continue
                before = len(new_links)
                _add(nid_a, nid_b, detail.get("relation_type", "related"), score,
                     f"知识库桥接：{ent_a} —{detail.get('relation_type', 'related')}→ {ent_b}",
                     evidence[:300])
                if len(new_links) > before:
                    bridged += 1
                    pairs += 1
        if len(new_links) > 4000:  # 防御性上限，避免极端语料炸图
            break

    for item in new_links[:4000]:
        db.add(Link(
            source_id=item["source_id"], target_id=item["target_id"],
            relation_type=item["relation_type"], relation_label=item["relation_label"],
            score=item["score"], final_weight=item["score"],
            evidence=item["evidence"], source_text=item["source_text"],
            source_file=KB_SOURCE_TAG, auto_generated=True,
            semantic_bridge=True, time_bridge=False,
        ))
    db.commit()
    logger.info(f"知识锚定关联：同一知识点 {same_concept} 条、知识库桥接 {bridged} 条")
    return {"same_concept": same_concept, "bridged": bridged, "total": len(new_links[:4000]),
            "capped": capped}


def purge_kb_links(db, user_id: int = 1) -> int:
    """清除由知识库生成的节点连线（source_file == '知识库'）"""
    from app.models.models import Link, Node

    node_ids = [n.id for n in db.query(Node).filter_by(user_id=user_id).all()]
    if not node_ids:
        return 0
    count = db.query(Link).filter(
        Link.source_file == KB_SOURCE_TAG,
        (Link.source_id.in_(node_ids)) | (Link.target_id.in_(node_ids)),
    ).delete(synchronize_session=False)
    db.commit()
    return count


# ---------------------------------------------------------------- 全量/增量编排


def kb_rebuild_all(db, user_id: int = 1, threshold: float = 0.15, node_threshold: float = 0.15) -> Dict:
    """重建：锚定 → 画像 → 文件关联 → 节点关联（幂等）"""
    from app.models.models import File
    from app.services.kb_index import load_index

    index = load_index(db)
    files = db.query(File).filter_by(user_id=user_id).all()
    anchor_stats = [apply_kb_anchoring(db, f.id, user_id, index=index, persist=True) for f in files]
    profile_stats = build_profiles(db, user_id, index=index)
    removed = purge_kb_links(db, user_id)
    file_links = link_files(db, user_id, threshold=threshold, index=index)
    node_links = link_nodes_by_kb(db, user_id, threshold=node_threshold, index=index)

    return {
        "files": len(files),
        "anchored_nodes": sum(s["anchored_nodes"] for s in anchor_stats),
        "anchor_hits": sum(s["anchor_hits"] for s in anchor_stats),
        "profiles": profile_stats,
        "file_links": file_links,
        "node_links": node_links,
        "purged_stale_links": removed,
        "kb": index.stats(),
    }


def kb_incremental_for_file(db, file_id: int, user_id: int = 1, index=None,
                            threshold: float = 0.15, node_threshold: float = 0.15) -> Dict:
    """新文件上传后的增量：锚定该文件 → 画像 → 更新它与既有文件的知识关联"""
    from app.services.kb_index import load_index

    index = index or load_index(db)
    anchor = apply_kb_anchoring(db, file_id, user_id, index=index, persist=True)
    prof = profile_file(db, file_id, user_id, index=index, persist=True)
    # 该文件已有节点连线先清掉，避免重复（仅清除 KB 生成且涉及本文件节点的连线）
    from app.models.models import Link, Node
    node_ids = [n.id for n in db.query(Node).filter_by(file_id=file_id).all()]
    if node_ids:
        db.query(Link).filter(
            Link.source_file == KB_SOURCE_TAG,
            (Link.source_id.in_(node_ids)) | (Link.target_id.in_(node_ids)),
        ).delete(synchronize_session=False)
        db.commit()
    node_links = link_nodes_by_kb(db, user_id, threshold=node_threshold, index=index, only_file_id=file_id)
    file_links = link_files_for(db, file_id, user_id, threshold=threshold, index=index)
    return {"anchor": anchor, "profile": {k: prof.get(k) for k in
            ("concept_count", "anchor_count", "coverage") if k in prof},
            "node_links": node_links, "file_links": file_links}
