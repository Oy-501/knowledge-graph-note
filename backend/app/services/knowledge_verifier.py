"""知识点智能判定：四路证据加权 + 分级处置

四路证据（每条都写进 evidence 供后台复核）：
  ① 知识库一致性 —— 是否命中知识库条目（规范名/别名）、定义是否与知识库矛盾、是否有关系桥接
  ② 图谱证据     —— 该知识点在文档里的锚定强度、是否已建立关联
  ③ 文本质量规则 —— 标题是否像术语（长度/编号/谓语片段）、描述是否含定义性句式
  ④ 联网证据     —— 抓公开搜索页，看检索结果是否支持该知识点存在（不可用时标注「未联网」）

分级策略（用户已确认）：
  score ≥ VERDICT_AUTO_ACCEPT 且无冲突 → accept（可选自动入知识库）
  score < VERDICT_REJECT_BELOW        → reject
  其余                                → pending（进后台待审队列）
"""
import re
from typing import Dict, List, Optional

from loguru import logger

from app.config import settings

# 与 parser 保持一致的"片段起手词"判断（这些开头的标题多半不是知识点）
_FRAGMENT_START = re.compile(
    r"^(分为|负责|增加|加入|注入|记录|执行|保存|放到|放在|用于|包括|包含|例如|通过|采用|"
    r"基于|作为|实现|提供|指的|表示|说明|解决|支持|遵循|减少|提升|降低|避免|防止|保证|"
    r"确保|需要|可以|不要|能够|使得|这是一段)"
)
_NUM_PREFIX = re.compile(r"^[（(]?[一二三四五六七八九十百千\d]{1,3}[)）、.．]\s*")
_DEFINITIONAL = re.compile(
    r"(是|指的是|是一种|指|属于|用于|用于把|是一种用于|包含|包括|分为|依赖|负责|"
    r"通过|基于|采用|可以|用来|是一种基于|以.*为核心|是一种.*风格)"
)


def _bigrams(text: str) -> set:
    clean = re.sub(r"\s+", "", (text or "").lower())
    if len(clean) < 2:
        return {clean} if clean else set()
    return {clean[i:i + 2] for i in range(len(clean) - 1)}


def _def_similarity(a: str, b: str) -> float:
    ga, gb = _bigrams(a), _bigrams(b)
    if not ga or not gb:
        return 0.0
    return len(ga & gb) / len(ga | gb)


class Verdict:
    """判定结果容器（便于聚合与序列化）"""

    def __init__(self, entity: str = ""):
        self.entity = entity
        self.score = 0.0
        self.evidence: List[Dict] = []
        self.conflict = False
        self.web_status = "skipped"   # ok | unavailable | skipped

    def add(self, kind: str, weight: float, detail: str, source: str = "",
            url: str = "", positive: bool = True):
        self.score += weight
        self.evidence.append({
            "type": kind,                 # kb | graph | rule | web
            "weight": round(weight, 3),
            "positive": positive,
            "detail": detail,
            "source": source,
            "url": url,
        })

    def to_dict(self) -> Dict:
        score = max(0.0, min(1.0, self.score))
        if score >= settings.VERDICT_AUTO_ACCEPT and not self.conflict:
            decision = "accept"
        elif score < settings.VERDICT_REJECT_BELOW:
            decision = "reject"
        else:
            decision = "pending"
        return {
            "entity": self.entity,
            "score": round(score, 3),
            "decision": decision,
            "conflict": self.conflict,
            "web_status": self.web_status,
            "evidence": self.evidence,
            "reason": self.explain(score, decision),
        }

    def explain(self, score: float, decision: str) -> str:
        pos = [e for e in self.evidence if e["positive"]]
        neg = [e for e in self.evidence if not e["positive"]]
        label = {"accept": "建议采纳", "reject": "建议驳回", "pending": "需人工确认"}[decision]
        parts = [f"{label}（综合 {score:.2f}）"]
        if pos:
            parts.append("支持：" + "；".join(e["detail"] for e in pos[:4]))
        if neg:
            parts.append("疑点：" + "；".join(e["detail"] for e in neg[:3]))
        if self.web_status == "unavailable":
            parts.append("联网校验不可用（已按本地证据判定）")
        return "。".join(parts)


# ---------------------------------------------------------------- 判定主流程


def verify_candidate(db, candidate, kb=None, use_web: Optional[bool] = None,
                     web_budget: Optional[Dict] = None) -> Dict:
    """对单条候选知识点做智能判定，返回 {score, decision, reason, evidence, web_status}"""
    from app.services.kb_index import load_index, normalize_key

    entity = (candidate.entity or candidate.title or "").strip()
    description = (candidate.description or "").strip()
    v = Verdict(entity)

    # ---------- ③ 文本质量规则 ----------
    title_len = len(entity)
    if _NUM_PREFIX.match(entity):
        v.add("rule", -0.35, f"标题带章节编号（{entity[:16]}），更像结构标题而非知识点",
              positive=False)
    elif _FRAGMENT_START.match(entity):
        v.add("rule", -0.35, f"标题是谓语片段（{entity[:16]}），缺少术语主语", positive=False)
    elif title_len < 2:
        v.add("rule", -0.4, "标题过短", positive=False)
    elif title_len > 24 and re.search(r"[，,。；;]", entity):
        v.add("rule", -0.20, "标题是长句片段（>24 字且含标点）", positive=False)
    else:
        # 形态正常的术语给足底分：**没有反面证据就等于合格**，
        # 否则文档内的专有概念（如「Memory 记忆模块」）会被误判驳回
        v.add("rule", 0.25, f"标题形态正常（{title_len} 字，无编号/谓语片段）")

    if len(description) >= 10:
        v.add("rule", 0.08, f"有描述文本（{len(description)} 字）")
    else:
        v.add("rule", -0.05, "描述过短，缺少可核验内容", positive=False)

    if _DEFINITIONAL.search(description):
        v.add("rule", 0.10, "描述含定义性句式（是/指的是/用于/包含…）")
    if (candidate.keywords or []):
        v.add("rule", 0.05, f"抽取到 {len(candidate.keywords)} 个关键词")

    # ---------- ① 知识库一致性 ----------
    kb = kb if kb is not None else load_index(db)
    canonical = kb.alias_map.get(normalize_key(entity))
    entry = kb.entries.get(canonical) if canonical else None
    if entry:
        via_alias = normalize_key(entity) != normalize_key(canonical)
        v.add("kb", 0.30,
              f"命中知识库条目「{canonical}」" + ("（经别名匹配）" if via_alias else "（规范名一致）"),
              source="knowledge_base")
        kb_def = entry.get("definition") or ""
        sim = _def_similarity(kb_def, description)
        if sim >= 0.25:
            v.add("kb", 0.15, f"描述与知识库定义一致（相似度 {sim:.2f}）", source="knowledge_base")
        elif kb_def and description and sim < 0.12:
            v.conflict = True
            v.add("kb", -0.25,
                  f"描述与知识库定义差异较大（相似度 {sim:.2f}），需人工确认以哪个为准",
                  source="knowledge_base", positive=False)
        neighbors = set(kb.adj.get(canonical, {}))
        shared = neighbors & {(k or "").strip() for k in (candidate.keywords or [])}
        if shared:
            v.add("kb", 0.10,
                  f"知识库中与 {len(shared)} 个相关概念存在关系（如 {'、'.join(list(shared)[:3])}）",
                  source="knowledge_base")
    else:
        v.add("kb", -0.05, "知识库中暂无该条目（新概念，需靠其他证据判断）",
              source="knowledge_base", positive=False)

    # ---------- ② 图谱证据 ----------
    if candidate.node_id:
        try:
            from app.models.models import Node, Link
            node = db.query(Node).filter_by(id=candidate.node_id).first()
            if node:
                anchors = [e for e in (node.entities or []) if kb.alias_map.get(normalize_key(e))]
                if anchors:
                    v.add("graph", 0.10,
                          f"文档节点已锚定 {len(anchors)} 个知识库概念（如 {'、'.join(anchors[:3])}）",
                          source="graph")
                else:
                    v.add("graph", -0.05, "文档节点未被任何知识库概念锚定（游离知识点）",
                          source="graph", positive=False)
                deg = db.query(Link).filter(
                    (Link.source_id == node.id) | (Link.target_id == node.id)).count()
                if deg:
                    v.add("graph", 0.05, f"已建立 {deg} 条关联", source="graph")
        except Exception as exc:
            logger.debug(f"图谱证据读取失败：{exc}")

    # ---------- ④ 联网证据 ----------
    want_web = settings.VERDICT_USE_WEB if use_web is None else use_web
    if not want_web:
        v.web_status = "skipped"
    elif web_budget is not None and web_budget.get("left", 0) <= 0:
        v.web_status = "unavailable"
        v.evidence.append({"type": "web", "weight": 0, "positive": True,
                           "detail": "本批联网预算已用完，未做联网校验", "source": "web", "url": ""})
    else:
        try:
            from app.services import web_probe
            if web_budget is not None:
                web_budget["left"] = web_budget.get("left", 0) - 1
            query = f"{entity} {candidate.domain or ''}".strip()
            result = web_probe.search_web(
                query, timeout=settings.VERDICT_WEB_TIMEOUT,
                cache_ttl=settings.VERDICT_WEB_CACHE_TTL)
            if not result.get("online"):
                v.web_status = "unavailable"
                v.evidence.append({
                    "type": "web", "weight": 0, "positive": True,
                    "detail": f"联网校验不可用（{result.get('error', '')[:80]}），已仅用本地证据",
                    "source": "web", "url": "",
                })
            else:
                v.web_status = "ok"
                support = web_probe.supports(entity, result["results"])
                if support["hits"] >= 2:
                    v.add("web", 0.15,
                          f"公开检索有 {support['hits']} 条结果提及该概念（{result['provider']}）",
                          source=result["provider"],
                          url=(support["samples"][0]["url"] if support["samples"] else ""))
                elif support["hits"] == 1:
                    v.add("web", 0.08, f"公开检索有 1 条结果提及该概念（{result['provider']}）",
                          source=result["provider"],
                          url=(support["samples"][0]["url"] if support["samples"] else ""))
                else:
                    # 「搜不到」不等于「不存在」（大量领域内专有名词搜不到），
                    # 因此只作为中性记录，不作为负面证据
                    v.add("web", 0.0,
                          f"公开检索未直接命中该概念（{result['provider']} 返回 "
                          f"{len(result['results'])} 条但不含该词）—— 不构成负面证据，交给人工判断",
                          source=result["provider"])
                # 把命中的样例摘要一并留证，便于人工复核
                for s in support["samples"]:
                    v.evidence.append({"type": "web-sample", "weight": 0, "positive": True,
                                       "detail": s["snippet"] or s["title"],
                                       "source": result["provider"], "url": s["url"]})
        except Exception as exc:
            v.web_status = "unavailable"
            v.evidence.append({"type": "web", "weight": 0, "positive": True,
                               "detail": f"联网校验异常：{str(exc)[:80]}", "source": "web", "url": ""})

    return v.to_dict()


# ---------------------------------------------------------------- 落库与审计


def apply_verdict(db, candidate, verdict: Dict, auto_ingest: bool = True,
                  actor: str = "system", write_audit: bool = True) -> Dict:
    """把判定结果写回候选记录；accept 时（可选）自动入知识库"""
    from datetime import datetime
    from app.models.models import KnowledgeBase, KnowledgeCandidate

    candidate.verdict_score = verdict["score"]
    candidate.verdict_decision = verdict["decision"]
    candidate.verdict_reason = verdict["reason"]
    candidate.verdict_evidence = verdict["evidence"]
    candidate.verdict_stage = "auto"
    candidate.verdict_web = verdict.get("web_status", "skipped")

    ingested = None
    if verdict["decision"] == "accept":
        candidate.status = "accepted"
        if auto_ingest and not verdict.get("conflict"):
            ingested = _ingest_to_kb(db, candidate)
    elif verdict["decision"] == "reject":
        candidate.status = "rejected"
    else:
        candidate.status = "open"

    if write_audit:
        from app.services import audit
        audit.log_event(
            db, "verdict", actor=actor, user_id=candidate.user_id,
            target_type="candidate", target_id=candidate.id, target_name=candidate.entity,
            summary=f"判定「{candidate.entity}」→ {verdict['decision']}（{verdict['score']}）",
            detail={
                "decision": verdict["decision"],
                "score": verdict["score"],
                "reason": verdict["reason"],
                "evidence": verdict["evidence"],
                "web_status": verdict.get("web_status"),
                "ingested_kb_entry_id": ingested,
                "thresholds": {
                    "auto_accept": settings.VERDICT_AUTO_ACCEPT,
                    "reject_below": settings.VERDICT_REJECT_BELOW,
                },
            },
            status="ok" if verdict["decision"] != "reject" else "warn",
            commit=False,
        )
    db.commit()
    return {"decision": verdict["decision"], "ingested_kb_entry_id": ingested}


def _ingest_to_kb(db, candidate) -> Optional[int]:
    """把通过判定的候选知识点写入知识库（幂等：已存在则只补别名/关系）"""
    from app.models.models import KnowledgeBase
    from app.services.kb_index import build_relations_from_entries, normalize_key

    existing = db.query(KnowledgeBase).filter(KnowledgeBase.entity == candidate.entity).first()
    if existing:
        changed = False
        aliases = list(existing.aliases or [])
        for kw in (candidate.keywords or [])[:3]:
            if kw and kw not in aliases and normalize_key(kw) != normalize_key(candidate.entity):
                aliases.append(kw)
                changed = True
        if changed:
            existing.aliases = aliases
            db.commit()
        candidate.kb_entry_id = existing.id
        return existing.id

    entry = KnowledgeBase(
        entity=candidate.entity,
        aliases=[],
        domain=candidate.domain or "general",
        level=candidate.level or 3,
        definition=(candidate.description or candidate.entity)[:2000],
        source=f"auto_verdict:file{candidate.file_id or '-'}",
        credibility=6,
        bridge_sentences=[],
        opposite_terms=[],
        related_terms=list(candidate.keywords or [])[:6],
    )
    db.add(entry)
    db.flush()
    candidate.kb_entry_id = entry.id
    db.commit()
    build_relations_from_entries(db)
    return entry.id


def verify_batch(db, candidates: List, use_web: Optional[bool] = None,
                 auto_ingest: bool = True) -> Dict:
    """批量判定（含联网预算控制，避免整批卡在网络上）"""
    from app.services.kb_index import load_index

    kb = load_index(db)
    budget = {"left": settings.VERDICT_MAX_WEB_CALLS if settings.VERDICT_USE_WEB else 0}
    stats = {"total": len(candidates), "accept": 0, "reject": 0, "pending": 0,
             "web_ok": 0, "web_unavailable": 0}
    for c in candidates:
        verdict = verify_candidate(db, c, kb=kb, use_web=use_web, web_budget=budget)
        apply_verdict(db, c, verdict, auto_ingest=auto_ingest)
        stats[verdict["decision"]] = stats.get(verdict["decision"], 0) + 1
        if verdict.get("web_status") == "ok":
            stats["web_ok"] += 1
        elif verdict.get("web_status") == "unavailable":
            stats["web_unavailable"] += 1
    return stats
