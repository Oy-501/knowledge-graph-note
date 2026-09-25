"""关联推理服务：四维加权融合打分 + 关系分类

大文件/大图谱下的性能保护（"上传大文件网站崩溃"的根因就在这一层）：
  1. 知识库桥接读内存索引：原来每对比一次就要查一次库（几千节点 = 几十万次 SQL）；
  2. 候选集剪枝：既有节点很多时，只与「关键词/知识点有交集」的节点比较，而不是全量 N×M；
  3. 配对数预算 + 时间预算：到顶提前收工并记日志，保证接口始终可响应。
"""
import json
import time
from collections import defaultdict
from typing import List, Dict, Optional
from loguru import logger
from app.models.models import Node, Link, NodeSource, KnowledgeBase
from app.config import settings
from app.services.vector_engine import (
    cosine_similarity, jaccard_similarity, encode, embed_to_db
)


def infer_links_for_new_file(file_id: int, user_id: int, db):
    """为新上传文件的所有节点推理关联"""
    new_nodes = db.query(Node).filter_by(file_id=file_id, user_id=user_id).all()
    if not new_nodes:
        return

    # 获取所有旧节点
    existing_nodes = db.query(Node).filter(
        Node.user_id == user_id,
        Node.file_id != file_id,
        Node.status == "active"
    ).all()

    # 转换为字典列表
    new_nodes_dict = [_node_to_dict(n) for n in new_nodes]
    existing_nodes_dict = [_node_to_dict(n) for n in existing_nodes]

    # 推理
    links = infer_links_batch(
        new_nodes_dict,
        user_id,
        {},
        0.15,
        db,
        existing_nodes=existing_nodes_dict
    )

    # 存入数据库
    count = 0
    for link_data in links:
        source_id = link_data["source"]
        target_id = link_data["target"]
        if source_id == target_id:
            continue

        # 检查是否已存在
        existing = db.query(Link).filter(
            (Link.source_id == source_id) & (Link.target_id == target_id) |
            (Link.source_id == target_id) & (Link.target_id == source_id)
        ).first()
        if existing:
            continue

        link = Link(
            source_id=source_id,
            target_id=target_id,
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


def infer_links_batch(
    new_nodes: List[Dict],
    user_id: int,
    weights: Dict,
    threshold: float,
    db,
    existing_nodes: Optional[List[Dict]] = None
) -> List[Dict]:
    """批量推理新节点与已有节点的关联（带候选剪枝与预算保护）"""
    if existing_nodes is None:
        existing = db.query(Node).filter(
            Node.user_id == user_id,
            Node.status == "active"
        ).all()
        existing_nodes = [_node_to_dict(n) for n in existing]

    alpha = weights.get("alpha", 0.15)
    beta = weights.get("beta", 0.25)
    gamma = weights.get("gamma", 0.50)
    delta = weights.get("delta", 0.10)
    th = threshold or 0.15

    # 知识库索引只加载一次（原实现是每对节点查一次数据库）
    kb = _load_kb_index(db)
    by_id = {n["id"]: n for n in existing_nodes}
    inverted = _build_inverted_index(existing_nodes, kb)
    use_full_scan = len(existing_nodes) <= settings.MAX_LINK_CANDIDATES

    links: List[Dict] = []
    pairs = 0
    deadline = time.monotonic() + settings.LINK_TIME_BUDGET_S
    truncated = False
    output_capped = False

    for new_node in new_nodes:
        candidates = _pick_candidates(new_node, existing_nodes, by_id, inverted, kb, use_full_scan)
        node_links: List[Dict] = []
        for old_node in candidates:
            if new_node.get("id") == old_node.get("id"):
                continue

            # 预算保护：大图谱下宁可少连几条，也不能让服务卡死
            pairs += 1
            if pairs > settings.LINK_PAIR_BUDGET:
                truncated = True
                break
            if pairs % 500 == 0 and time.monotonic() > deadline:
                truncated = True
                break

            # 上下文窗口检查
            if not can_connect(new_node, old_node):
                continue

            # 四维打分
            score, detail = calculate_score(new_node, old_node, alpha, beta, gamma, delta,
                                            db, kb=kb)

            if score >= th:
                rel_type = classify_relation(new_node, old_node, score, detail, db)
                evidence = get_evidence(new_node, old_node, detail)

                node_links.append({
                    "source": new_node["id"],
                    "target": old_node["id"],
                    "relation_type": rel_type["type"],
                    "relation_label": rel_type["label"],
                    "score": round(score, 4),
                    "final_weight": round(score, 4),
                    "evidence": evidence,
                    "source_text": detail.get("source_text", ""),
                    "source_file": detail.get("source_file", ""),
                    "auto_generated": True,
                    "time_bridge": True
                })

        # 每个节点只保留最强的 N 条（一个节点连 800 个既无意义也会写出海量连线）
        node_links.sort(key=lambda x: -x["score"])
        if len(node_links) > settings.MAX_LINKS_PER_NODE:
            node_links = node_links[:settings.MAX_LINKS_PER_NODE]
        links.extend(node_links)

        if len(links) >= settings.LINK_OUTPUT_LIMIT:
            output_capped = True
            break
        if truncated:
            break

    if truncated or output_capped:
        logger.warning(
            f"关联推理触发保护（比较 {pairs} 对，上限 {settings.LINK_PAIR_BUDGET} 对 / "
            f"{settings.LINK_TIME_BUDGET_S}s；产出 {len(links)} 条，上限 "
            f"{settings.LINK_OUTPUT_LIMIT} 条）：已提前结束。建议拆分文件、按分组管理，"
            f"或调低单文件规模。"
        )
    return links


# ---------------------------------------------------------------- 候选集与知识库缓存


def _load_kb_index(db):
    """加载知识库内存索引；失败时返回 None（退化为原来的库内查询）"""
    try:
        from app.services.kb_index import load_index
        return load_index(db)
    except Exception as exc:  # 知识库不可用不应阻断关联推理
        logger.warning(f"加载知识库索引失败，退回库内查询：{exc}")
        return None


def _tokens_of(node: Dict) -> set:
    """节点的比较用特征：实体 + 关键词 + 知识锚定实体（归一化小写）"""
    raw = [node.get("entity") or ""] + list(node.get("keywords") or []) + list(node.get("entities") or [])
    return {t.strip().lower() for t in raw if t and t.strip()}


def _build_inverted_index(existing_nodes: List[Dict], kb) -> Dict[str, List[int]]:
    """特征 → 节点 id 倒排表，用于快速取候选"""
    inverted: Dict[str, List[int]] = defaultdict(list)
    for n in existing_nodes:
        for tok in _tokens_of(n):
            inverted[tok].append(n["id"])
    return inverted


def _pick_candidates(new_node: Dict, existing_nodes: List[Dict], by_id: Dict[int, Dict],
                     inverted: Dict[str, List[int]], kb, use_full_scan: bool) -> List[Dict]:
    """选择要比较的既有节点：小图全量（行为不变），大图只取有交集的，并截断到上限"""
    if use_full_scan:
        return existing_nodes

    hit_ids = []
    seen = set()
    for tok in _tokens_of(new_node):
        for nid in inverted.get(tok, ()):
            if nid not in seen:
                seen.add(nid)
                hit_ids.append(nid)
    if not hit_ids:
        # 没有任何特征交集：大图下不再全量比较（这也是"知识边界"的体现）
        return []

    candidates = [by_id[i] for i in hit_ids if i in by_id]
    if len(candidates) > settings.MAX_LINK_CANDIDATES:
        # 命中过多时优先保留"特征更多"的节点（关键词多的更可能真的相关）
        candidates.sort(key=lambda n: -len(_tokens_of(n)))
        candidates = candidates[:settings.MAX_LINK_CANDIDATES]
    return candidates


def calculate_score(
    node_a: Dict, node_b: Dict,
    alpha: float, beta: float, gamma: float, delta: float,
    db, kb=None
) -> tuple:
    """四维加权融合打分"""
    detail = {}

    # 同名互连守门：不同节点但实体同名（同一术语在多篇笔记重复出现），
    # 不直接互连 —— 同名节点应在「跨文件同名合并 / 孤儿收养」流程中统一为一个概念节点，
    # 在此之前自连只会造成图谱视觉噪音与语义分叉。同文件内同名已被 parser 合并，不会走到此分支。
    # （四维推理/8 类关系完整实现见 Task 4，此处只拦截最刺眼的同名自环）
    if (node_a.get("id") != node_b.get("id")
            and node_a.get("entity")
            and node_a.get("entity") == node_b.get("entity")):
        detail["source_text"] = f"同名实体「{node_a.get('entity')}」跨文件重复出现，等待同名合并"
        return 0.0, detail

    # 层级稳定性公理（§12）：仅 L1 与 L4 不直接连线（除非有知识库桥接），其余层级组合放行
    level_a = node_a.get("level", 3)
    level_b = node_b.get("level", 3)
    if abs(level_a - level_b) >= 3:
        has_bridge = check_corpus_bridge(node_a, node_b, db, kb=kb)
        if not has_bridge:
            return 0.0, detail

    # α: 关键词 Jaccard
    kw_a = node_a.get("keywords", [])
    kw_b = node_b.get("keywords", [])
    sim_text = jaccard_similarity(kw_a, kw_b)
    detail["sim_text"] = sim_text

    # β: 语义向量余弦
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

    # γ: 知识库推理
    sim_corpus = check_corpus_bridge_score(node_a, node_b, db, kb=kb)
    detail["sim_corpus"] = sim_corpus

    # δ: 拓扑邻居重叠（简化版）
    sim_topology = 0.0
    detail["sim_topology"] = sim_topology

    score = alpha * sim_text + beta * sim_vector + gamma * sim_corpus + delta * sim_topology
    return min(1.0, score), detail


def can_connect(node_a: Dict, node_b: Dict) -> bool:
    """上下文窗口检查"""
    if node_a.get("id") == node_b.get("id"):
        return False

    # 同一文件 → 强关联
    if node_a.get("file_id") and node_b.get("file_id") and node_a["file_id"] == node_b["file_id"]:
        return True

    # 同一分组（非default）
    if (node_a.get("group_id") and node_b.get("group_id") and
        node_a["group_id"] == node_b["group_id"] and
        node_a["group_id"] != "default"):
        return True

    # 同时期
    t_a = node_a.get("upload_time", 0)
    t_b = node_b.get("upload_time", 0)
    if t_a > 0 and t_b > 0 and abs(t_a - t_b) < 7 * 24 * 3600:
        return True

    return False


def check_corpus_bridge(node_a: Dict, node_b: Dict, db, kb=None) -> bool:
    """检查知识库桥接"""
    score = check_corpus_bridge_score(node_a, node_b, db, kb=kb)
    return score > 0


def check_corpus_bridge_score(node_a: Dict, node_b: Dict, db, kb=None) -> float:
    """计算知识库桥接分数

    优先走内存索引（kb）：把两侧实体归一到规范知识点，再看它们在知识库关系图上是否
    互为邻居 —— 与原「查 related_terms / 别名」的语义一致，但不再每对节点查一次数据库。
    """
    try:
        ent_a = set(node_a.get("entities", []) + node_a.get("keywords", []))
        ent_b = set(node_b.get("entities", []) + node_b.get("keywords", []))
        if not ent_a or not ent_b:
            return 0.0

        if kb is not None:
            try:
                from app.services.kb_index import normalize_key
                canon_a = {kb.alias_map.get(normalize_key(x)) for x in ent_a}
                canon_b = {kb.alias_map.get(normalize_key(x)) for x in ent_b}
                canon_a.discard(None)
                canon_b.discard(None)
                if not canon_a or not canon_b:
                    return 0.0
                bridge_count = 0
                for c in canon_a:
                    if (set(kb.adj.get(c, {})) | {c}) & canon_b:
                        bridge_count += 1
                for c in canon_b:
                    if (set(kb.adj.get(c, {})) | {c}) & canon_a:
                        bridge_count += 1
                if bridge_count > 0:
                    return min(0.8, bridge_count * 0.2)
                return 0.0
            except Exception as exc:
                logger.warning(f"内存知识库桥接失败，退回库内查询：{exc}")

        # 退化路径（无索引时）：原来的库内查询实现
        entities_a, entities_b = ent_a, ent_b
        kb_entries = db.query(KnowledgeBase).filter(
            KnowledgeBase.entity.in_(list(entities_a | entities_b))
        ).all()

        if not kb_entries:
            return 0.0

        bridge_count = 0
        for kb_entry in kb_entries:
            related = set(kb_entry.related_terms or [])
            related_aliases = set(kb_entry.aliases or [])
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
    """分类关系类型"""
    level_a = node_a.get("level", 3)
    level_b = node_b.get("level", 3)
    diff = level_a - level_b

    # 层级差判断
    if diff == 1:
        return {"type": "prerequisite", "label": "前置知识"}
    elif diff == -1:
        return {"type": "implementation", "label": "实现关系"}
    elif diff == 0:
        # 同层级用语义相似度判断
        if detail.get("sim_vector", 0) > 0.8:
            return {"type": "extension", "label": "扩展延伸"}
        elif detail.get("sim_corpus", 0) > 0.3:
            return {"type": "theory", "label": "理论关联"}
        else:
            return {"type": "related", "label": "相关"}
    else:
        return {"type": "related", "label": "相关"}


def get_evidence(node_a: Dict, node_b: Dict, detail: Dict) -> str:
    """生成证据描述"""
    parts = []
    if detail.get("sim_text", 0) > 0.3:
        parts.append(f"关键词重合度 {detail['sim_text']:.2f}")
    if detail.get("sim_vector", 0) > 0.6:
        parts.append(f"语义相似度 {detail['sim_vector']:.2f}")
    if detail.get("sim_corpus", 0) > 0:
        parts.append(f"知识库桥接")
    return "; ".join(parts) if parts else "弱关联"


def _node_to_dict(node: Node) -> Dict:
    """将Node对象转换为字典"""
    return {
        "id": node.id,
        "entity": node.entity,
        "title": node.title,
        "description": node.description or "",
        "keywords": node.keywords or [],
        "entities": node.entities or [],
        "level": node.level or 3,
        "domain": node.domain or "",
        "file_id": node.file_id,
        "group_id": node.group_id or "default",
        "upload_time": node.upload_time or 0,
        "embedding": node.embedding,
        "isolate_blacklist": node.isolate_blacklist or []
    }