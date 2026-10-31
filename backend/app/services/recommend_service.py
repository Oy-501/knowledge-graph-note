"""学习推荐：可解释打分 + 信息来源 + 离线回测。

推荐分把「学过的内容」和「还没学但处在学习前沿的内容」放在同一把尺子上：

    score = 0.35·W + 0.30·U + 0.15·C + 0.10·Z + 0.10·S

  W  遗忘缺口  W = 1 − (0.5·R + 0.5·M)
               R = 0.9^(Δt/间隔)   —— 艾宾浩斯保持率，间隔来自 SM-2 调度
               M = min(1, 复习次数/3) × (0.4 + 0.6·ease 归一化) —— 熟练度
  U  到期紧迫  U = 1（已逾期），否则 max(0, 1 − 距到期天数/7)
  C  图谱核心度 log1p(节点度数) / log1p(最大度数) —— 度中心性（Freeman, 1977）
  Z  学习前沿  与已掌握节点相邻=1；同领域=0.5；被近期笔记引用=0.6；其他=0
               —— 最近发展区（Vygotsky, 1978）
  S  来源质量  0.1 + 0.5·原文置信度 + 0.3·min(1, 联网证据数/3) + 0.1·有直达链接

所有权重之和为 1，score ∈ [0, 1]。每项都会把「代入数值」和「贡献值」一起返回，
前端据此展示公式，而不是只给一个黑盒分数。
"""
from __future__ import annotations

import math
from collections import defaultdict
from datetime import datetime
from typing import Dict, List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.models import (KnowledgeCandidate, LearningReview, Link, Node,
                               NodeSource, Note)
from app.services import web_probe

# 权重：合计 1.0。改权重只需改这里，公式字符串与前端展示都读同一份。
WEIGHTS = {
    "weakness": 0.35,
    "urgency": 0.30,
    "centrality": 0.15,
    "frontier": 0.10,
    "source": 0.10,
}

TERM_LABELS = {
    "weakness": "遗忘缺口",
    "urgency": "到期紧迫",
    "centrality": "图谱核心度",
    "frontier": "学习前沿",
    "source": "来源质量",
}

FORMULA = {
    "expression": "score = 0.35·W + 0.30·U + 0.15·C + 0.10·Z + 0.10·S",
    "range": "0 ~ 1",
    "terms": [
        {"key": "W", "name": "遗忘缺口", "value_key": "weakness",
         "definition": "W = 1 − (0.5·R + 0.5·M)",
         "detail": "R = 0.9^(Δt/间隔) 为记忆保持率；M = min(1, 复习次数/3) × (0.4+0.6·ease 归一化) 为熟练度。"},
        {"key": "U", "name": "到期紧迫", "value_key": "urgency",
         "definition": "U = 1（已逾期）；否则 max(0, 1 − 距到期天数/7)",
         "detail": "越接近或超过复习到期日，越应该优先回看。"},
        {"key": "C", "name": "图谱核心度", "value_key": "centrality",
         "definition": "C = log1p(度数) / log1p(最大度数)",
         "detail": "连接越多的知识点，掌握后能带动越多相邻概念。"},
        {"key": "Z", "name": "学习前沿", "value_key": "frontier",
         "definition": "Z = 1（相邻已掌握） / 0.6（近期笔记引用） / 0.5（同领域） / 0",
         "detail": "优先推荐「跳一跳够得着」的内容，避免过难或完全无关。"},
        {"key": "S", "name": "来源质量", "value_key": "source",
         "definition": "S = 0.1 + 0.5·原文置信度 + 0.3·min(1, 联网证据/3) + 0.1·有直达链接",
         "detail": "有原文出处、可核验链接的知识点，学习收益更可靠。"},
    ],
    "basis": [
        {"claim": "遗忘曲线 R = 0.9^(Δt/间隔)", "source": "Ebbinghaus (1885)；SM-2 间隔重复（Wozniak, 1987）",
         "url": "https://www.supermemo.com/en/blog/the-true-history-of-spaced-repetition"},
        {"claim": "度中心性", "source": "Freeman (1977), A set of measures of centrality based on betweenness",
         "url": "https://doi.org/10.2307/2392183"},
        {"claim": "最近发展区（ZPD）", "source": "Vygotsky (1978), Mind in Society",
         "url": "https://en.wikipedia.org/wiki/Zone_of_proximal_development"},
    ],
}


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def _days_between(later: datetime, earlier: Optional[datetime]) -> float:
    if earlier is None:
        return 0.0
    return max(0.0, (later - earlier).total_seconds() / 86400.0)


def _graph_stats(db: Session) -> tuple:
    """一次查询算出度数与邻接表，避免逐节点查库（N+1）。"""
    degrees = defaultdict(int)
    adjacency = defaultdict(set)
    rows = db.query(Link.source_id, Link.target_id).all()
    for source_id, target_id in rows:
        degrees[source_id] += 1
        degrees[target_id] += 1
        adjacency[source_id].add(target_id)
        adjacency[target_id].add(source_id)
    return degrees, adjacency


def _source_stats(db: Session) -> tuple:
    """来源质量的轻量特征：原文最大置信度、联网证据条数。"""
    origin = {node_id: conf for node_id, conf in
              db.query(NodeSource.node_id, func.max(NodeSource.confidence))
              .group_by(NodeSource.node_id).all()}
    web = {node_id: count for node_id, count in
           db.query(KnowledgeCandidate.node_id, func.count(KnowledgeCandidate.id))
           .filter(KnowledgeCandidate.node_id.isnot(None),
                   KnowledgeCandidate.verdict_evidence.isnot(None))
           .group_by(KnowledgeCandidate.node_id).all()}
    return origin, web


def _tracked_reviews(db: Session, user_id: int) -> Dict[int, LearningReview]:
    """每个节点只保留最新的一条复习计划，避免重复记录把分数抬高。"""
    tracked: Dict[int, LearningReview] = {}
    rows = db.query(LearningReview).filter_by(user_id=user_id).all()
    for row in rows:
        if row.node_id is None:
            continue
        current = tracked.get(row.node_id)
        if current is None or (row.due_at or datetime.min) > (current.due_at or datetime.min):
            tracked[row.node_id] = row
    return tracked


def _note_linked_nodes(db: Session, user_id: int) -> set:
    notes = (db.query(Note)
             .filter_by(user_id=user_id)
             .order_by(Note.updated_at.desc()).limit(20).all())
    linked = set()
    for note in notes:
        for node_id in (note.linked_nodes or []):
            try:
                linked.add(int(node_id))
            except (TypeError, ValueError):
                continue
    return linked


def _score_node(node: Node, review: Optional[LearningReview], now: datetime,
                degrees: Dict[int, int], max_degree: int, adjacency,
                mastered_ids: set, mastered_domains: set,
                note_linked: set, origin_conf: float, web_count: int) -> Dict:
    """计算单个知识点的分项，返回 0~1 的组件值和贡献值。"""
    # ---- W 遗忘缺口 ----
    if review and (review.review_count or 0) > 0:
        interval = max(1, review.interval_days or 1)
        last = review.last_reviewed_at or review.created_at or now
        elapsed = _days_between(now, last)
        retention = 0.9 ** (elapsed / interval)
    else:
        # 从未复习过的知识点按「未巩固」处理，而不是当作刚复习完
        retention = 0.2

    ease = _clamp(review.ease if review else 2.5, 1.3, 2.5)
    ease_norm = (ease - 1.3) / 1.2
    review_count = review.review_count if review else 0
    mastery = min(1.0, review_count / 3.0) * (0.4 + 0.6 * ease_norm)
    weakness = _clamp(1 - (0.5 * retention + 0.5 * mastery))

    # ---- U 到期紧迫 ----
    overdue_days = 0.0
    if review and review.due_at:
        remaining = (review.due_at - now).total_seconds() / 86400.0
        if remaining <= 0:
            urgency = 1.0
            overdue_days = -remaining
        else:
            urgency = _clamp(1 - remaining / 7.0)
    else:
        urgency = 0.0

    # ---- C 图谱核心度 ----
    degree = degrees.get(node.id, 0)
    centrality = (math.log1p(degree) / math.log1p(max_degree)) if max_degree > 0 else 0.0

    # ---- Z 学习前沿 ----
    if mastered_ids and adjacency.get(node.id, set()) & mastered_ids:
        frontier = 1.0
    elif node.id in note_linked:
        frontier = 0.6
    elif node.domain and node.domain in mastered_domains:
        frontier = 0.5
    else:
        frontier = 0.0

    # ---- S 来源质量 ----
    has_reference = bool((node.entity or node.title or "").strip())
    source_quality = _clamp(
        0.1
        + 0.5 * (origin_conf or 0.0)
        + 0.3 * min(1.0, (web_count or 0) / 3.0)
        + (0.1 if has_reference else 0.0)
    )

    components = {
        "retention": round(retention, 4),
        "mastery": round(mastery, 4),
        "weakness": round(weakness, 4),
        "urgency": round(urgency, 4),
        "centrality": round(centrality, 4),
        "frontier": round(frontier, 4),
        "source": round(source_quality, 4),
        "overdue_days": round(overdue_days, 2),
    }
    contributions = {
        key: round(WEIGHTS[key] * components[key], 4)
        for key in WEIGHTS
    }
    score = _clamp(sum(contributions.values()))
    return {"score": score, "components": components,
            "contributions": contributions, "overdue_days": overdue_days}


def _reason(contributions: Dict[str, float], overdue_days: float) -> str:
    ranked = sorted(contributions.items(), key=lambda kv: -kv[1])
    parts = [f"{TERM_LABELS[key]} {value:.2f}"
             for key, value in ranked[:2] if value >= 0.02]
    if overdue_days > 0:
        parts.append(f"已逾期 {overdue_days:.0f} 天")
    return " + ".join(parts) or "综合评分靠前"


def _node_sources(db: Session, node: Node) -> List[Dict]:
    """汇总一个知识点的三类来源：本地原文、联网证据、百科直达链接。"""
    entity = (node.entity or node.title or "").strip()
    out: List[Dict] = []
    seen = set()

    def push(item: Dict):
        key = item.get("url") or item.get("title")
        if key and key not in seen:
            seen.add(key)
            out.append(item)

    for row in (db.query(NodeSource)
                .filter_by(node_id=node.id)
                .order_by(NodeSource.confidence.desc()).limit(2).all()):
        location = ""
        if row.line_start:
            location = f"（第 {row.line_start}-{row.line_end or row.line_start} 行）"
        snippet = (row.paragraph or "").strip().replace("\n", " ")[:120]
        push({
            "type": "origin",
            "title": f"原文片段{location}" if location else "原文片段",
            "url": "",
            "provider": row.source_type or "本地文档",
            "confidence": round(row.confidence or 0.6, 2),
            "snippet": snippet,
        })

    if entity:
        candidate = (db.query(KnowledgeCandidate)
                     .filter_by(node_id=node.id)
                     .order_by(KnowledgeCandidate.verdict_score.desc())
                     .first())
        evidence = candidate.verdict_evidence if candidate else []
        for item in web_probe.evidence_sources(entity, evidence, limit=3):
            push({
                "type": "web",
                "title": item.get("title") or item.get("url"),
                "url": item.get("url") or "",
                "provider": item.get("provider") or "联网检索",
                "confidence": 0.85,
                "snippet": "",
            })
        for item in web_probe.reference_links(entity)[:3]:
            push({
                "type": "reference",
                "title": item.get("title"),
                "url": item.get("url") or "",
                "provider": item.get("site") or "直达链接",
                # 直达链接只保证「地址可用」，不代表内容已核验，置信度低于真实证据
                "confidence": 0.5,
                "snippet": "",
            })

    out.sort(key=lambda item: -item.get("confidence", 0))
    return out[:5]


def _evaluate(tracked: Dict[int, LearningReview], scores: Dict[int, float],
              now: datetime, k: int = 5) -> Dict:
    """离线回测：以「是否已到期」为标签，比较推荐排序与随机排序。

    只在复习计划内的条目上回测，因为标签（due_at）只对它们存在。
    这是可复现的排序质量指标，不是拍脑袋的「效果好」。
    """
    rows = [row for row in tracked.values() if row.node_id in scores]
    sample = len(rows)
    if sample < 5:
        return {
            "insufficient": True,
            "sample_size": sample,
            "reason": f"复习计划只有 {sample} 条，至少 5 条才能做回测",
            "method": "Precision@K / Recall@K / Lift（标签：是否已到期）",
        }

    positives = [row for row in rows if row.due_at and row.due_at <= now]
    if not positives:
        return {
            "insufficient": True,
            "sample_size": sample,
            "reason": "当前没有已到期条目，无法回测命中率",
            "method": "Precision@K / Recall@K / Lift（标签：是否已到期）",
        }

    k = max(1, min(k, sample))
    ranked = sorted(rows, key=lambda row: -scores[row.node_id])
    top = ranked[:k]
    hit = sum(1 for row in top if row.due_at and row.due_at <= now)
    precision = hit / k
    recall = hit / len(positives)
    baseline = len(positives) / sample
    lift = (precision / baseline) if baseline > 0 else 0.0
    return {
        "insufficient": False,
        "sample_size": sample,
        "k": k,
        "positives": len(positives),
        "hits": hit,
        "precision_at_k": round(precision, 3),
        "recall_at_k": round(recall, 3),
        "random_baseline": round(baseline, 3),
        "lift": round(lift, 2),
        "method": "Precision@K / Recall@K / Lift（标签：是否已到期）",
        "note": "Precision@K = 前 K 条中已到期的比例；Lift = 该比例 ÷ 随机抽取的到期比例。",
    }


def recommend(db: Session, user_id: int, limit: int = 6,
              now: Optional[datetime] = None) -> Dict:
    """生成学习推荐列表：分数、分项、理由、信息来源与回测指标。"""
    now = now or datetime.utcnow()
    limit = max(1, min(int(limit or 6), 20))

    # 只推荐「知识/问题」类节点：thought、note 是过程性内容，不属于要复习的知识
    nodes = (db.query(Node)
             .filter(Node.user_id == user_id, Node.status == "active",
                     Node.type.in_(("knowledge", "question")))
             .all())
    if not nodes:
        return {"items": [], "formula": FORMULA, "weights": WEIGHTS,
                "evaluation": _evaluate({}, {}, now),
                "message": "还没有知识点，先上传文档建立知识库。"}

    tracked = _tracked_reviews(db, user_id)
    degrees, adjacency = _graph_stats(db)
    origin_stats, web_stats = _source_stats(db)
    note_linked = _note_linked_nodes(db, user_id)
    max_degree = max(degrees.values() or [0])

    mastered_ids = {
        node_id for node_id, row in tracked.items()
        if (row.review_count or 0) >= 3 and (row.interval_days or 0) >= 21
    }
    mastered_domains = {item.domain for item in nodes
                        if item.id in mastered_ids and item.domain}

    scored: List[tuple] = []
    scores: Dict[int, float] = {}
    for node in nodes:
        result = _score_node(
            node, tracked.get(node.id), now, degrees, max_degree, adjacency,
            mastered_ids, mastered_domains, note_linked,
            origin_stats.get(node.id, 0.0), web_stats.get(node.id, 0),
        )
        scores[node.id] = result["score"]
        scored.append((result["score"], node, result))

    scored.sort(key=lambda item: (-item[0], item[1].id))

    # 同名知识点可能来自不同文件，重复出现会让推荐列表像噪声；保留分数最高的那条
    picked = []
    seen_titles = set()
    for entry in scored:
        key = (entry[1].title or entry[1].entity or "").strip().lower()
        if key and key in seen_titles:
            continue
        seen_titles.add(key)
        picked.append(entry)
        if len(picked) >= limit:
            break

    items = []
    for rank, (score, node, result) in enumerate(picked, start=1):
        review = tracked.get(node.id)
        sources = _node_sources(db, node)
        items.append({
            "rank": rank,
            "node_id": node.id,
            "title": node.title or node.entity or f"知识点 {node.id}",
            "entity": node.entity or "",
            "domain": node.domain or "",
            "level": node.level,
            "score": round(score, 3),
            "components": result["components"],
            "contributions": result["contributions"],
            "reason": _reason(result["contributions"], result["overdue_days"]),
            "tracked": review is not None,
            "due_at": (review.due_at.isoformat(timespec="seconds")
                       if review and review.due_at else ""),
            "overdue_days": result["overdue_days"],
            "review_count": (review.review_count if review else 0),
            "interval_days": (review.interval_days if review else 0),
            "sources": sources,
            "source_count": len(sources),
        })

    return {
        "items": items,
        "formula": FORMULA,
        "weights": WEIGHTS,
        "evaluation": _evaluate(tracked, scores, now),
        "generated_at": now.isoformat(timespec="seconds"),
    }
