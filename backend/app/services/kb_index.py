"""知识库索引与锚定引擎

本项目「有知识库」而不是「简单语义相似」的关键就在这一层：

  1. 别名归一    —— 所有知识点/别名 → 唯一规范实体
  2. 最长匹配扫描 —— 文档文本 → 命中的知识库知识点（带原文位置与证据）
  3. 概念空间画像 —— 文件在知识库概念空间上的稀疏权重向量
  4. 知识图相似度 —— 由「共享知识点 + 关系图桥接 + 领域层级一致性」计算
"""
import json
import math
import re
from collections import Counter, defaultdict
from typing import Dict, List, Optional, Tuple

from loguru import logger

_FULLWIDTH = {chr(0xFF01 + i): chr(0x21 + i) for i in range(94)}
_FULLWIDTH["\u3000"] = " "

_ASCII_KEY = re.compile(r"^[A-Za-z0-9_\-\.\+\#]+$")
_ASCII_ALNUM = re.compile(r"[A-Za-z0-9_]")


def normalize_text(text: str) -> str:
    if not text:
        return ""
    return "".join(_FULLWIDTH.get(ch, ch) for ch in text)


def normalize_key(key: str) -> str:
    if not key:
        return ""
    return normalize_text(key).strip().lower()


def _is_boundary_char(ch: str) -> bool:
    return bool(ch) and not _ASCII_ALNUM.match(ch)


_GENERIC_ALIASES = {
    "类型", "结构", "主题", "内容", "信息", "数据", "系统", "方法", "技术", "过程",
    "结果", "状态", "模式", "关系", "对象", "属性", "场景", "原理", "问题", "时间",
    "空间", "基础", "框架", "形式", "方式", "功能", "作用", "特点", "要素", "部分",
    "type", "data", "system", "model", "content", "theme", "mode", "value", "story",
}


class KbIndex:
    """知识库内存索引（从 DB 条目与关系构建，只读、可随时重建）"""

    MIN_KEY_LEN = 2
    MAX_ALIAS_LEN = 40

    def __init__(self, entries: List[Dict], relations: Optional[List[Dict]] = None):
        self.entries: Dict[str, Dict] = {}
        self.alias_map: Dict[str, str] = {}
        self.adj: Dict[str, Dict[str, float]] = defaultdict(dict)
        self.rel_detail: Dict[Tuple[str, str], Dict] = {}
        self._by_first: Dict[str, List[str]] = defaultdict(list)
        for e in entries or []:
            self._add_entry(e)
        self._build_scan_table()
        for r in relations or []:
            self._add_relation(r)
        self.degree = {k: len(v) for k, v in self.adj.items()}

    def specificity(self, entity: str) -> float:
        d = self.degree.get(entity, 0)
        if d <= 1:
            return 1.0
        return round(max(0.25, 1.0 / (1.0 + math.log2(1 + d))), 4)

    def _add_entry(self, e: Dict):
        entity = (e.get("entity") or "").strip()
        if not entity:
            return
        key = normalize_key(entity)
        canonical = self.alias_map.get(key, entity)
        record = self.entries.setdefault(canonical, {
            "entity": canonical, "aliases": [], "domain": e.get("domain") or "general",
            "level": e.get("level") or 3, "definition": e.get("definition") or "",
            "bridge_sentences": e.get("bridge_sentences") or [],
            "related_terms": e.get("related_terms") or [],
            "opposite_terms": e.get("opposite_terms") or [],
            "source": e.get("source") or "", "credibility": e.get("credibility") or 5,
        })
        self.alias_map[key] = canonical
        for a in [entity] + list(e.get("aliases") or []):
            a = (a or "").strip()
            if not a or len(a) > self.MAX_ALIAS_LEN:
                continue
            ak = normalize_key(a)
            if len(ak) < self.MIN_KEY_LEN:
                continue
            if ak not in record["aliases"]:
                record["aliases"].append(a)
            if ak != key and ak in _GENERIC_ALIASES:
                continue
            self.alias_map.setdefault(ak, canonical)

    def _add_relation(self, r: Dict):
        a = (r.get("source_entity") or "").strip()
        b = (r.get("target_entity") or "").strip()
        if not a or not b:
            return
        ca = self.alias_map.get(normalize_key(a), a)
        cb = self.alias_map.get(normalize_key(b), b)
        if ca == cb:
            return
        w = float(r.get("weight") or 0.5)
        detail = {
            "relation_type": r.get("relation_type") or "related",
            "relation_label": r.get("relation_label") or "",
            "evidence": r.get("evidence") or "", "weight": w,
        }
        self.adj[ca][cb] = max(self.adj[ca].get(cb, 0.0), w)
        self.adj[cb][ca] = max(self.adj[cb].get(ca, 0.0), w)
        self.rel_detail[(ca, cb)] = detail
        self.rel_detail.setdefault((cb, ca), detail)

    def _build_scan_table(self):
        self._by_first = defaultdict(list)
        for key, canonical in self.alias_map.items():
            if len(key) < self.MIN_KEY_LEN:
                continue
            self._by_first[key[0]].append(key)
        for ch in self._by_first:
            self._by_first[ch].sort(key=len, reverse=True)

    def scan(self, text: str, max_hits: int = 500) -> List[Dict]:
        if not text:
            return []
        norm = normalize_text(text)
        low = norm.lower()
        if len(low) != len(norm):
            low = norm
        hits: List[Dict] = []
        i, n = 0, len(low)
        while i < n:
            matched_key = None
            for key in self._by_first.get(low[i], ()):
                end = i + len(key)
                if end > n or not low.startswith(key, i):
                    continue
                if _ASCII_KEY.match(key):
                    if i > 0 and not _is_boundary_char(low[i - 1]):
                        continue
                    if end < n and not _is_boundary_char(low[end]):
                        continue
                matched_key = key
                break
            if not matched_key:
                i += 1
                continue
            canonical = self.alias_map[matched_key]
            entry = self.entries.get(canonical, {})
            hits.append({
                "entity": canonical, "matched": norm[i:i + len(matched_key)],
                "start": i, "end": i + len(matched_key),
                "via_alias": normalize_key(canonical) != matched_key,
                "level": entry.get("level", 3), "domain": entry.get("domain") or "general",
            })
            if len(hits) >= max_hits:
                break
            i += len(matched_key)
        return hits

    def build_profile(self, text: str, max_concepts: int = 80) -> Dict:
        hits = self.scan(text)
        if not hits:
            return {
                "concepts": [], "domains": {}, "levels": {},
                "anchor_count": 0, "concept_count": 0, "coverage": 0.0, "entities": [],
            }
        counts = Counter(h["entity"] for h in hits)
        raw = {e: 1.0 + math.log2(c) for e, c in counts.items()}
        max_w = max(raw.values()) or 1.0
        concepts = []
        for entity, w in sorted(raw.items(), key=lambda kv: -kv[1])[:max_concepts]:
            entry = self.entries.get(entity, {})
            sample = next(h for h in hits if h["entity"] == entity)
            ctx = text[max(0, sample["start"] - 20): sample["end"] + 20].replace("\n", " ")
            concepts.append({
                "entity": entity, "weight": round(w / max_w, 4), "count": counts[entity],
                "via_alias": any(h["via_alias"] for h in hits if h["entity"] == entity),
                "level": entry.get("level", 3), "domain": entry.get("domain") or "general",
                "definition": (entry.get("definition") or "")[:200], "evidence": ctx.strip(),
            })
        domains: Dict[str, float] = defaultdict(float)
        levels: Dict[str, int] = defaultdict(int)
        for h in hits:
            domains[h.get("domain") or "general"] += 1.0
            levels[str(h.get("level") or 3)] += 1
        dom_total = sum(domains.values()) or 1.0
        covered_chars = sum(h["end"] - h["start"] for h in hits)
        body_len = len(re.sub(r"\s", "", text)) or 1
        return {
            "concepts": concepts,
            "domains": {k: round(v / dom_total, 4) for k, v in domains.items()},
            "levels": dict(levels),
            "anchor_count": len(hits), "concept_count": len(counts),
            "coverage": round(min(1.0, covered_chars / body_len), 4),
            "entities": list(counts.keys()),
        }

    def similarity(self, prof_a: Dict, prof_b: Dict, bridge_hops: int = 2) -> Dict:
        a = {c["entity"]: float(c.get("weight") or 0.0) for c in prof_a.get("concepts", [])}
        b = {c["entity"]: float(c.get("weight") or 0.0) for c in prof_b.get("concepts", [])}
        empty = {
            "kb_similarity": 0.0, "direct_score": 0.0, "bridge_score": 0.0,
            "domain_score": 0.0, "shared_concepts": [], "bridges": [],
        }
        if not a or not b:
            return empty
        shared = sorted(set(a) & set(b), key=lambda e: -(a[e] + b[e]))
        def norm(vec: Dict[str, float]) -> Dict[str, float]:
            m = math.sqrt(sum(v * v for v in vec.values())) or 1.0
            return {k: v / m for k, v in vec.items()}
        na, nb = norm(a), norm(b)
        direct = sum(na[e] * nb[e] for e in shared)
        direct = min(1.0, direct * 1.6)
        def expand(vec: Dict[str, float]) -> Dict[str, float]:
            out = dict(vec)
            for e, w in vec.items():
                for nb_ent, rw in self.adj.get(e, {}).items():
                    out[nb_ent] = max(out.get(nb_ent, 0.0), w * rw * 0.6 * self.specificity(nb_ent))
            return out
        exp_a, exp_b = norm(expand(a)), norm(expand(b))
        keys = set(exp_a) & set(exp_b)
        expanded = sum(exp_a[k] * exp_b[k] for k in keys)
        bridge_score = min(1.0, max(0.0, (expanded - direct) * 2.5))
        bridges: List[Dict] = []
        for ea in a:
            if ea in b:
                continue
            for nb1, rw1 in self.adj.get(ea, {}).items():
                if nb1 in a:
                    continue
                if nb1 in b and len(bridges) < 40:
                    d = self.rel_detail.get((ea, nb1), {})
                    bridges.append({
                        "from": ea, "to": nb1, "hops": 1,
                        "relation_type": d.get("relation_type", "related"),
                        "relation_label": d.get("relation_label", ""),
                        "evidence": (d.get("evidence") or "")[:160],
                        "score": round(min(a[ea], b[nb1]) * rw1 * self.specificity(nb1), 4),
                    })
                if bridge_hops < 2:
                    continue
                for nb2, rw2 in self.adj.get(nb1, {}).items():
                    if nb2 in a or nb2 not in b or len(bridges) >= 40:
                        continue
                    d = self.rel_detail.get((nb1, nb2), {})
                    bridges.append({
                        "from": ea, "to": nb2, "hops": 2, "via": nb1,
                        "relation_type": d.get("relation_type", "related"),
                        "relation_label": d.get("relation_label", ""),
                        "evidence": (d.get("evidence") or "")[:160],
                        "score": round(min(a[ea], b[nb2]) * rw1 * rw2 * 0.5
                                       * self.specificity(nb1) * self.specificity(nb2), 4),
                    })
        bridges = [br for br in bridges if br["score"] >= 0.02]
        bridges.sort(key=lambda x: -x["score"])
        dom_a = {k: v for k, v in (prof_a.get("domains") or {}).items() if k != "general"}
        dom_b = {k: v for k, v in (prof_b.get("domains") or {}).items() if k != "general"}
        if dom_a and dom_b:
            sa, sb = sum(dom_a.values()) or 1.0, sum(dom_b.values()) or 1.0
            dom_overlap = sum(min(dom_a.get(k, 0) / sa, dom_b.get(k, 0) / sb)
                              for k in set(dom_a) | set(dom_b))
        else:
            dom_overlap = 0.0
        lv_a = self._dominant_level(prof_a)
        lv_b = self._dominant_level(prof_b)
        level_score = 1.0 - min(1.0, abs(lv_a - lv_b) / 3.0)
        domain_score = round(min(1.0, 0.6 * min(1.0, dom_overlap) + 0.4 * level_score), 4)
        kb_similarity = 0.50 * direct + 0.35 * bridge_score + 0.15 * domain_score
        return {
            "kb_similarity": round(min(1.0, kb_similarity), 4),
            "direct_score": round(direct, 4), "bridge_score": round(bridge_score, 4),
            "domain_score": domain_score, "shared_concepts": shared[:20],
            "bridges": bridges[:20], "dominant_level_a": lv_a, "dominant_level_b": lv_b,
        }

    @staticmethod
    def _dominant_level(prof: Dict) -> int:
        levels = prof.get("levels") or {}
        if not levels:
            return 3
        return int(max(levels.items(), key=lambda kv: kv[1])[0])

    def neighbors(self, entity: str, limit: int = 20) -> List[Dict]:
        canonical = self.alias_map.get(normalize_key(entity), entity)
        out = []
        for nb_ent, rw in sorted(self.adj.get(canonical, {}).items(), key=lambda kv: -kv[1])[:limit]:
            d = self.rel_detail.get((canonical, nb_ent), {})
            out.append({
                "entity": nb_ent, "weight": round(rw, 4),
                "relation_type": d.get("relation_type", "related"),
                "relation_label": d.get("relation_label", ""),
                "evidence": (d.get("evidence") or "")[:160],
                "definition": (self.entries.get(nb_ent, {}).get("definition") or "")[:160],
            })
        return out

    def stats(self) -> Dict:
        domains: Dict[str, int] = defaultdict(int)
        levels: Dict[str, int] = defaultdict(int)
        for e in self.entries.values():
            domains[e.get("domain") or "general"] += 1
            levels[str(e.get("level") or 3)] += 1
        return {
            "entities": len(self.entries), "aliases": len(self.alias_map),
            "relations": len({tuple(sorted(k)) for k in self.rel_detail}),
            "domains": dict(domains), "levels": dict(levels),
        }


def load_index(db) -> KbIndex:
    from app.models.models import KnowledgeBase, KbRelation
    entries = []
    for e in db.query(KnowledgeBase).all():
        entries.append({
            "entity": e.entity, "aliases": e.aliases or [], "domain": e.domain,
            "level": e.level or 3, "definition": e.definition,
            "bridge_sentences": e.bridge_sentences or [],
            "related_terms": e.related_terms or [], "opposite_terms": e.opposite_terms or [],
            "source": e.source, "credibility": e.credibility,
        })
    relations = []
    for r in db.query(KbRelation).all():
        relations.append({
            "source_entity": r.source_entity, "target_entity": r.target_entity,
            "relation_type": r.relation_type, "relation_label": r.relation_label,
            "weight": r.weight, "evidence": r.evidence,
        })
    return KbIndex(entries, relations)


def build_relations_from_entries(db, force: bool = False) -> Dict:
    from app.models.models import KnowledgeBase, KbRelation
    if force:
        db.query(KbRelation).filter(KbRelation.origin == "derived").delete(synchronize_session=False)
        db.commit()
    entries = db.query(KnowledgeBase).all()
    if not entries:
        return {"created": 0, "total": 0}
    index = KbIndex([{
        "entity": e.entity, "aliases": e.aliases or [], "domain": e.domain,
        "level": e.level or 3, "definition": e.definition,
        "bridge_sentences": e.bridge_sentences or [],
    } for e in entries])
    existing = {(r.source_entity, r.target_entity, r.relation_type) for r in db.query(KbRelation).all()}
    created = 0
    def _push(src: str, dst: str, rtype: str, label: str, weight: float, evidence: str):
        nonlocal created
        if not src or not dst or src == dst:
            return
        key = (src, dst, rtype)
        if key in existing:
            return
        existing.add(key)
        db.add(KbRelation(
            source_entity=src, target_entity=dst, relation_type=rtype,
            relation_label=label, weight=weight, evidence=evidence[:500], origin="derived",
        ))
        created += 1
    for e in entries:
        src = e.entity
        for term in (e.related_terms or []):
            t = (term or "").strip()
            if not t:
                continue
            target = index.alias_map.get(normalize_key(t))
            if target and target != src:
                _push(src, target, "related", "相关", 0.6, f"知识库条目「{src}」的相关术语包含「{t}」")
        for sent in (e.bridge_sentences or []):
            if not sent:
                continue
            for hit in index.scan(sent):
                if hit["entity"] != src:
                    _push(src, hit["entity"], "bridge", "桥接", 0.5, sent)
        for a in (e.aliases or []):
            target = index.alias_map.get(normalize_key(a))
            if target and target != src and normalize_key(target) == normalize_key(a):
                _push(src, target, "equivalent", "等价", 0.9,
                      f"「{a}」同时是「{src}」的别名与「{target}」的规范名")
    db.commit()
    total = db.query(KbRelation).count()
    logger.info(f"知识库关系构建完成：新增 {created} 条，当前共 {total} 条")
    return {"created": created, "total": total}
