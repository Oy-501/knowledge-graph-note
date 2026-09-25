"""知识图谱总结引擎

把一张「网状」的知识图谱，总结成三样东西：

  1. 结构化总结（JSON）—— 概览指标 / 层级结构 / 领域分布 / 核心枢纽 / 连通簇 /
     学习路径主线 / 知识库桥接 / 孤立点 / 优化建议
  2. Mermaid 流程图 —— `flowchart TD` + 按阶段(层级)或领域分组的 subgraph，
     把"网"整理成"流"，人看得懂，大模型也读得懂（Mermaid 是 LLM 原生熟悉的图语言）
  3. AI 可读摘要 —— 紧凑的纯文本 digest（概览 + 学习主线 + 三元组清单 + 知识缺口），
     可直接投喂给大模型做学习/续写/问答，token 友好

设计原则：**只做归纳，不臆造**。所有结论都能回溯到真实的节点、连线和知识库条目。
"""
import re
from collections import Counter, defaultdict, deque
from datetime import datetime
from typing import Dict, List, Optional

from loguru import logger

LEVEL_LABELS = {1: "元概念", 2: "核心理论", 3: "应用实践", 4: "实现工具"}

# 关系类型 → 学习先后顺序（数字越小越"上层/越先学"）
RELATION_FLOW_RANK = {
    "prerequisite": 0,   # 前置知识：最该先看
    "theory": 1,         # 理论基础
    "implementation": 2, # 具体实现
    "extension": 3,      # 扩展延伸
    "evolution": 4,      # 演进
    "application": 5,    # 应用场景
    "comparison": 6,     # 对比
    "equivalent": 7,     # 等价
    "bridged": 8,        # 知识库桥接
    "related": 9,        # 弱关联
}

RELATION_LABELS = {
    "prerequisite": "前置知识", "implementation": "实现关系", "theory": "理论基础",
    "comparison": "对比关系", "application": "应用场景", "extension": "扩展延伸",
    "contradiction": "矛盾争议", "evolution": "演进关系", "equivalent": "等价知识点",
    "bridged": "知识库桥接", "related": "相关",
}


# ---------------------------------------------------------------- 底层工具


def _short(text: str, limit: int = 46) -> str:
    text = (text or "").replace("\n", " ").strip()
    return text if len(text) <= limit else text[:limit - 1] + "…"


_NOISY_TITLE = re.compile(
    r"^[（(]?[一二三四五六七八九十\d]+[)）、.．]|"          # 编号/章节序号开头
    r"^(分为|负责|用于|包括|包含|例如|其中|通过|采用|基于|作为|实现|提供|指的|表示|说明|"
    r"解决|支持|遵循|增加|注入|记录|执行|保存|确保|需要)"     # 谓语片段起手
)


def _looks_noisy(title: str) -> bool:
    """粗判知识点标题是否像抽取噪音（编号开头、谓语片段、超长句子片段）

    注意：中文两字词（读者/结构/笔记）是正常术语，只有单字或空标题才算异常。
    """
    t = (title or "").strip()
    if len(t) < 2:
        return True
    if _NOISY_TITLE.match(t):
        return True
    if len(t) > 24 and re.search(r"[，,。；;]", t):
        return True
    return False


def _node_brief(node, degree: int = 0) -> Dict:
    return {
        "id": node.id,
        "title": node.title or node.entity,
        "entity": node.entity,
        "level": node.level or 3,
        "level_label": node.level_label or LEVEL_LABELS.get(node.level or 3, "应用实践"),
        "domain": node.domain or "general",
        "type": node.type or "knowledge",
        "description": _short(node.description, 120),
        "file_id": node.file_id,
        "degree": degree,
        "keywords": (node.keywords or [])[:6],
        "entities": (node.entities or [])[:6],
    }


class _UnionFind:
    def __init__(self):
        self.parent: Dict[int, int] = {}

    def find(self, x):
        self.parent.setdefault(x, x)
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[rb] = ra


# ---------------------------------------------------------------- 结构分析


def build_summary(db, user_id: int = 1, max_paths: int = 6, max_depth: int = 6) -> Dict:
    """对当前用户的图谱做结构化总结"""
    from app.models.models import Node, Link, File
    from app.services.kb_index import load_index, normalize_key

    nodes = db.query(Node).filter(Node.user_id == user_id, Node.status == "active").all()
    node_ids = {n.id for n in nodes}
    files = {f.id: f for f in db.query(File).filter_by(user_id=user_id).all()}

    if not nodes:
        return {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "empty": True,
            "overview": {"node_count": 0, "link_count": 0, "file_count": len(files)},
            "message": "图谱还没有知识点，先上传文档再生成总结。",
        }

    links = db.query(Link).filter(
        Link.source_id.in_(list(node_ids)), Link.target_id.in_(list(node_ids))
    ).all() if node_ids else []
    links = [l for l in links if l.is_render is not False and l.source_id != l.target_id]

    # ---- 邻接表（有向保留方向，另建无向用于连通性） ----
    out_edges: Dict[int, List] = defaultdict(list)
    in_edges: Dict[int, List] = defaultdict(list)
    undirected: Dict[int, List] = defaultdict(list)
    degree: Counter = Counter()
    relation_counter: Counter = Counter()
    for l in links:
        if l.source_id not in node_ids or l.target_id not in node_ids:
            continue
        out_edges[l.source_id].append(l)
        in_edges[l.target_id].append(l)
        undirected[l.source_id].append(l.target_id)
        undirected[l.target_id].append(l.source_id)
        degree[l.source_id] += 1
        degree[l.target_id] += 1
        relation_counter[l.relation_type or "related"] += 1

    node_map = {n.id: n for n in nodes}

    # ---- 层级结构 ----
    level_buckets: Dict[int, List] = defaultdict(list)
    for n in nodes:
        level_buckets[n.level or 3].append(n)
    levels = []
    for lv in sorted(level_buckets):
        bucket = sorted(level_buckets[lv], key=lambda x: -degree[x.id])
        levels.append({
            "level": lv,
            "label": LEVEL_LABELS.get(lv, "应用实践"),
            "count": len(bucket),
            "samples": [_short(b.title or b.entity, 20) for b in bucket[:8]],
        })

    # ---- 领域分布 ----
    domain_buckets: Dict[str, List] = defaultdict(list)
    for n in nodes:
        domain_buckets[n.domain or "general"].append(n)
    domains = []
    for dom, bucket in sorted(domain_buckets.items(), key=lambda kv: -len(kv[1])):
        bucket_sorted = sorted(bucket, key=lambda x: -degree[x.id])
        domains.append({
            "domain": dom,
            "count": len(bucket),
            "share": round(len(bucket) / len(nodes), 4),
            "top_nodes": [(b.title or b.entity) for b in bucket_sorted[:5]],
            "avg_level": round(sum(b.level or 3 for b in bucket) / len(bucket), 2),
        })

    # ---- 核心枢纽 ----
    hubs = []
    for nid, deg in degree.most_common(12):
        if deg < 2:
            break
        n = node_map[nid]
        rel_types = Counter((l.relation_type or "related") for l in (out_edges[nid] + in_edges[nid]))
        hubs.append({
            **_node_brief(n, deg),
            "relation_breakdown": {RELATION_LABELS.get(k, k): v for k, v in rel_types.most_common()},
            "connected_titles": [
                _short(node_map[o].title or node_map[o].entity, 18)
                for o in dict.fromkeys(undirected[nid])
            ][:6],
        })

    # ---- 连通簇（并查集） ----
    uf = _UnionFind()
    for nid in node_ids:
        uf.find(nid)
    for a, targets in undirected.items():
        for b in targets:
            uf.union(a, b)
    comps: Dict[int, List[int]] = defaultdict(list)
    for nid in node_ids:
        comps[uf.find(nid)].append(nid)

    clusters = []
    for root, members in sorted(comps.items(), key=lambda kv: -len(kv[1])):
        if len(members) < 2:
            continue
        member_nodes = [node_map[m] for m in members]
        dom_counter = Counter(n.domain or "general" for n in member_nodes)
        top = sorted(member_nodes, key=lambda x: -degree[x.id])
        clusters.append({
            "size": len(members),
            "label": top[0].title or top[0].entity,
            "dominant_domain": dom_counter.most_common(1)[0][0],
            "domains": [d for d, _ in dom_counter.most_common(4)],
            "file_count": len({n.file_id for n in member_nodes}),
            "top_nodes": [{"id": n.id, "title": n.title or n.entity, "degree": degree[n.id]}
                          for n in top[:6]],
        })

    # ---- 学习路径（把网拉成线） ----
    paths = _build_learning_paths(nodes, node_map, out_edges, in_edges, degree, max_paths, max_depth)

    # ---- 知识库锚定与桥接 ----
    index = load_index(db)
    kb_anchor_counter: Counter = Counter()
    for n in nodes:
        for ent in (n.entities or []):
            canonical = index.alias_map.get(normalize_key(ent))
            if canonical:
                kb_anchor_counter[canonical] += 1
    kb_anchors = [{
        "entity": ent,
        "anchored_nodes": cnt,
        "level": (index.entries.get(ent, {}) or {}).get("level"),
        "domain": (index.entries.get(ent, {}) or {}).get("domain"),
        "definition": _short((index.entries.get(ent, {}) or {}).get("definition"), 120),
    } for ent, cnt in kb_anchor_counter.most_common(15)]

    bridges = []
    for l in links:
        if l.source_file == "知识库" or l.semantic_bridge:
            a, b = node_map.get(l.source_id), node_map.get(l.target_id)
            if not a or not b:
                continue
            bridges.append({
                "source": a.title or a.entity,
                "target": b.title or b.entity,
                "relation_type": l.relation_type,
                "relation_label": l.relation_label or RELATION_LABELS.get(l.relation_type, "相关"),
                "score": round(l.score or 0, 3),
                "evidence": _short(l.evidence, 120),
                "source_text": _short(l.source_text, 160),
                "cross_file": a.file_id != b.file_id,
            })
    bridges.sort(key=lambda x: -x["score"])

    # ---- 孤立与问题 ----
    isolated = [_node_brief(n, 0) for n in nodes if degree[n.id] == 0]
    multi_domain_clusters = [c for c in clusters if len(c["domains"]) > 1]

    covered_domains = {d["domain"] for d in domains if d["domain"] != "general"}
    kb_domains = set()
    for ent in kb_anchor_counter:
        kb_domains.add((index.entries.get(ent, {}) or {}).get("domain") or "general")
    missing = sorted(d for d in kb_domains if d not in covered_domains and d != "general")

    suggestions = []
    if isolated:
        suggestions.append(
            f"{len(isolated)} 个知识点没有任何关联（如「{_short(isolated[0]['title'], 16)}」），"
            f"建议补充上下文或锚定到知识库后再重建关联。"
        )
    if missing:
        suggestions.append(
            f"知识库还有这些领域未被文档覆盖：{'、'.join(missing[:6])}，可上传相关文档补齐。"
        )
    if levels and not any(l["level"] == 1 for l in levels):
        suggestions.append("缺少 L1 元概念层知识点，图谱缺少「顶层骨架」，建议补充领域总览类文档。")
    hub_fanout = [h for h in hubs[:5] if h["degree"] >= 6]
    if hub_fanout:
        suggestions.append(
            f"「{hub_fanout[0]['title']}」连接了 {hub_fanout[0]['degree']} 个知识点，"
            f"建议拆分为更细的知识点或建立子分组，避免单点过载。"
        )
    if len(clusters) > 1 and multi_domain_clusters:
        suggestions.append(
            f"{len(clusters)} 个知识簇中有 {len(multi_domain_clusters)} 个横跨多领域，"
            f"跨领域簇是知识迁移的枢纽，可作为论文/汇报的重点案例。"
        )
    weak_ratio = 0.0
    if links:
        weak = len([l for l in links if (l.score or 0) < 0.45])
        weak_ratio = weak / len(links)
        if weak_ratio > 0.5:
            suggestions.append(
                f"{weak_ratio * 100:.0f}% 的连线是低分弱关联（多由时间窗/层级差推出，非知识依据），"
                f"建议在「知识库」页点「重建知识关联」，让关联改由知识库概念空间决定；"
                f"否则学习主线的可信度会受影响。"
            )

    noisy = [n for n in nodes if _looks_noisy(n.title or n.entity)]
    if len(noisy) >= 3:
        samples = "、".join(_short(n.title or n.entity, 12) for n in noisy[:4])
        suggestions.append(
            f"{len(noisy)} 个知识点标题疑似抽取噪音（如「{samples}」），"
            f"多为标题行/谓语片段被当成知识点；建议整理原文格式或手工编辑这些节点标题，"
            f"否则总结与流程图的可用度会打折扣。"
        )

    if not suggestions:
        suggestions.append("图谱结构健康：层级完整、关联充分，可直接作为学习材料使用。")

    overview = {
        "node_count": len(nodes),
        "link_count": len(links),
        "file_count": len(files),
        "domain_count": len(domains),
        "cluster_count": len(clusters),
        "isolated_count": len(isolated),
        "avg_degree": round(sum(degree.values()) / max(1, len(nodes)), 2),
        "density": round(len(links) / max(1, len(nodes) * (len(nodes) - 1) / 2), 4),
        "kb_anchor_count": len(kb_anchor_counter),
        "kb_bridge_count": len(bridges),
        "cross_file_bridge_count": len([b for b in bridges if b["cross_file"]]),
        "level_distribution": {str(l["level"]): l["count"] for l in levels},
        "relation_distribution": {RELATION_LABELS.get(k, k): v for k, v in relation_counter.most_common()},
    }

    summary = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "empty": False,
        "overview": overview,
        "levels": levels,
        "domains": domains,
        "hubs": hubs,
        "clusters": clusters,
        "paths": paths,
        "kb_anchors": kb_anchors,
        "bridges": bridges[:40],
        "isolated": isolated[:40],
        "suggestions": suggestions,
        "node_index": {str(n.id): _node_brief(n, degree[n.id]) for n in nodes},
    }
    logger.info(
        f"图谱总结完成：{overview['node_count']} 节点 / {overview['link_count']} 连线 / "
        f"{overview['cluster_count']} 簇 / {len(paths)} 条学习主线"
    )
    return summary


def _build_learning_paths(nodes, node_map, out_edges, in_edges, degree,
                          max_paths: int, max_depth: int) -> List[Dict]:
    """沿真实连线走出「学习主线」：优先从前置/理论边前进，避免回头路。

    排序策略（从主到次）：
      1) 不跨领域优先（学习线应当成链而不是乱跳）
      2) 关系类型的先后顺序（前置 → 理论 → 实现 → …）
      3) 连线分数（越强越先走）
      4) 目标节点层级（先抽象后具体）
    并且要求每条主线与已选主线重合度 < 60%，保证 N 条主线讲的是 N 件事。
    """

    # 弱关系（等价/桥接/弱关联）不足以支撑「下一步学什么」，只在分数够高时才允许跨出去
    WEAK_RELATIONS = {"equivalent", "bridged", "related"}
    # 低于该分数的连线不足以支撑学习顺序（多为时间窗/层级差推出来的弱关联）
    MIN_STEP_SCORE = 0.45

    def successors(cur_id, cur_domain, cur_level):
        ranked = []
        for l in out_edges.get(cur_id, []):
            t = l.target_id
            if t not in node_map:
                continue
            nxt = node_map[t]
            rel = l.relation_type or "related"
            score = round(l.score or 0, 3)
            next_level = nxt.level or 3

            # 学习主线必须踩在"有依据的强关联"上：弱连线的分数门槛更高
            if score < MIN_STEP_SCORE:
                continue
            if rel in WEAK_RELATIONS and score < 0.6:
                continue
            # 层级大幅回退（L3 → L1）只有前置关系才合理
            if next_level < cur_level - 1 and rel != "prerequisite":
                continue
            # 跨领域：学习主线按领域成链，跨域只放行强前置/强理论关系
            cross = 0 if (nxt.domain or "general") == cur_domain else 1
            if cross and not (rel in ("prerequisite", "theory") and score >= 0.6):
                continue

            ranked.append((
                cross,
                RELATION_FLOW_RANK.get(rel, 9),
                -score,
                next_level,
                -degree[t],
                t,
                rel,
            ))
        ranked.sort()
        return ranked

    # 起点优先：L1/L2 且入边少（越像"根"越先讲）
    def root_rank(n):
        lv = n.level or 3
        return (lv, len(in_edges.get(n.id, [])), -degree[n.id])

    candidates = [n for n in nodes if degree[n.id] > 0]
    candidates.sort(key=root_rank)

    paths, used_roots, accepted_sets = [], set(), []
    for root in candidates:
        if len(paths) >= max_paths:
            break
        if root.id in used_roots:
            continue
        path_ids, relations = [root.id], []
        visited = {root.id}
        # 同名知识点不重复进同一条主线（图谱里可能存在同名不同 id 的节点）
        used_titles = {(root.title or root.entity)}
        cur = root.id
        cur_domain = root.domain or "general"
        cur_level = root.level or 3
        while len(path_ids) < max_depth:
            nxt = None
            for _cross, _rank, _score, _lv, _deg, t, rel in successors(cur, cur_domain, cur_level):
                title = node_map[t].title or node_map[t].entity
                if t in visited or title in used_titles:
                    continue
                nxt = (t, rel)
                break
            if not nxt:
                break
            path_ids.append(nxt[0])
            relations.append(nxt[1])
            visited.add(nxt[0])
            used_titles.add(node_map[nxt[0]].title or node_map[nxt[0]].entity)
            cur = nxt[0]
            cur_domain = node_map[cur].domain or "general"
            cur_level = node_map[cur].level or 3
        if len(path_ids) < 3:
            continue

        # 与已选主线重合太多 → 换一条起点重新走（避免 N 条主线其实是同一条）
        current = set(path_ids)
        too_similar = any(
            len(current & prev) / max(1, len(current | prev)) > 0.5
            for prev in accepted_sets
        )
        if too_similar:
            continue

        used_roots.add(root.id)
        accepted_sets.append(current)
        steps = []
        for i, nid in enumerate(path_ids):
            n = node_map[nid]
            steps.append({
                "order": i + 1,
                "id": nid,
                "title": n.title or n.entity,
                "level": n.level or 3,
                "level_label": n.level_label or LEVEL_LABELS.get(n.level or 3, "应用实践"),
                "domain": n.domain or "general",
                "relation_from_prev": relations[i - 1] if i > 0 else None,
                "relation_label_from_prev": (RELATION_LABELS.get(relations[i - 1], "相关")
                                             if i > 0 else None),
            })
        paths.append({
            "title": f"{steps[0]['title']} → {steps[-1]['title']}",
            "start": steps[0]["title"],
            "end": steps[-1]["title"],
            "length": len(steps),
            "domains": list(dict.fromkeys(s["domain"] for s in steps)),
            "steps": steps,
        })
    return paths


# ---------------------------------------------------------------- Mermaid 流程图


def _safe_id(nid) -> str:
    return f"n{re.sub(r'[^0-9A-Za-z_]', '', str(nid))}"


def _escape_label(text: str) -> str:
    return (text or "").replace('"', "'").replace("[", "(").replace("]", ")").replace("\n", " ")


LEVEL_CLASSDEF = {
    1: "fill:#4F6F8F,stroke:#3D5A75,color:#FFFFFF",
    2: "fill:#7CB8A0,stroke:#4E9679,color:#10312B",
    3: "fill:#D4A574,stroke:#B58554,color:#3A2A16",
    4: "fill:#B9A7CC,stroke:#8E7BA8,color:#2A2036",
}


def to_mermaid(summary: Dict, group_by: str = "level", max_nodes: int = 120,
               include_bridges: bool = True) -> str:
    """把总结转成 Mermaid flowchart（AI 与人都读得懂的"流程图"）

    group_by: level（按学习阶段，默认，最像流程）| domain（按领域）
    """
    if summary.get("empty"):
        return "flowchart TD\n  empty[\"图谱暂无知识点\"]\n"

    node_index = summary.get("node_index") or {}
    ordered = sorted(node_index.values(), key=lambda n: (-n["degree"], n["level"]))
    picked = ordered[:max_nodes]
    picked_ids = {str(n["id"]) for n in picked}

    groups: Dict[str, List[Dict]] = {}
    if group_by == "domain":
        for n in picked:
            groups.setdefault(f"D_{n['domain'] or 'general'}", []).append(n)
    else:
        for lv in (1, 2, 3, 4):
            bucket = [n for n in picked if n["level"] == lv]
            if bucket:
                groups[f"L{lv}_{LEVEL_LABELS[lv]}"] = bucket

    lines = [
        "flowchart TD",
        "  %% 由知识图谱自动生成的总结流程图（可直接粘贴到 Mermaid / 支持 Mermaid 的编辑器）",
    ]
    used_ids = set()
    for gname, items in groups.items():
        gid = re.sub(r"[^0-9A-Za-z_]", "_", gname)
        label = gname.replace("_", " ")
        lines.append(f'  subgraph {gid}["{_escape_label(label)}"]')
        lines.append("    direction LR")
        for n in items:
            used_ids.add(str(n["id"]))
            lines.append(f'    {_safe_id(n["id"])}["{_escape_label(_short(n["title"], 22))}"]')
        lines.append("  end")
    lines.append("")

    # 边：只画两端都在图里的连线（流程图必须闭合可读）
    edge_lines, bridge_lines = [], []
    for l in summary.get("_raw_links", []):
        s, t = str(l["source"]), str(l["target"])
        if s not in used_ids or t not in used_ids:
            continue
        label = l.get("relation_label") or RELATION_LABELS.get(l.get("relation_type"), "相关")
        if l.get("kb_bridge") and include_bridges:
            bridge_lines.append(f'  {_safe_id(s)} -. 知识库桥接 .-> {_safe_id(t)}')
        else:
            edge_lines.append(f'  {_safe_id(s)} -->|{_escape_label(label)}| {_safe_id(t)}')

    lines.extend(edge_lines[:400] or [])
    if bridge_lines:
        lines.append("  %% 知识库桥接（虚线）：跨文件、靠知识库推理建立的知识通路")
        lines.extend(bridge_lines[:120])
    lines.append("")

    for lv, style in LEVEL_CLASSDEF.items():
        lines.append(f"  classDef lv{lv} {style},stroke-width:1px;")
    for lv in (1, 2, 3, 4):
        ids = [_safe_id(n["id"]) for n in picked if n["level"] == lv]
        for i in range(0, len(ids), 25):
            chunk = ids[i:i + 25]
            if chunk:
                lines.append(f"  class {','.join(chunk)} lv{lv};")
    return "\n".join(lines) + "\n"


def to_ai_digest(summary: Dict, max_triples: int = 220) -> str:
    """AI 可读摘要：紧凑纯文本，直接投喂大模型（token 友好、结构固定便于解析）"""
    if summary.get("empty"):
        return "[KNOWLEDGE-GRAPH-SUMMARY v1]\nSTATUS: empty\nNOTE: 图谱暂无知识点\n"

    ov = summary["overview"]
    out: List[str] = [
        "[KNOWLEDGE-GRAPH-SUMMARY v1]",
        f"GENERATED: {summary.get('generated_at', '')}",
        "",
        "## META",
        f"nodes={ov['node_count']} links={ov['link_count']} files={ov['file_count']} "
        f"domains={ov['domain_count']} clusters={ov['cluster_count']} "
        f"isolated={ov['isolated_count']} kb_bridges={ov['kb_bridge_count']}",
        f"relations: " + ", ".join(f"{k}={v}" for k, v in ov["relation_distribution"].items()),
        "",
        "## STAGES (知识层级：1 最抽象 → 4 最具体)",
    ]
    for lv in summary["levels"]:
        out.append(f"L{lv['level']} {lv['label']} ({lv['count']}): " +
                   "、".join(lv["samples"][:8]))

    out += ["", "## DOMAINS"]
    for d in summary["domains"]:
        out.append(f"{d['domain']} ({d['count']}, {int(d['share'] * 100)}%): " +
                   "、".join(d["top_nodes"]))

    if summary["paths"]:
        out += ["", "## LEARNING-FLOW (建议学习主线，按顺序读)"]
        for i, p in enumerate(summary["paths"], 1):
            chain = " -> ".join(f"[L{s['level']}]{s['title']}" for s in p["steps"])
            out.append(f"PATH{i}: {chain}")

    if summary["hubs"]:
        out += ["", "## HUBS (核心枢纽，先掌握它们收益最大)"]
        for h in summary["hubs"][:10]:
            out.append(f"- {h['title']} (L{h['level']} {h['level_label']}, {h['domain']}, "
                       f"度={h['degree']}, 连到: {'、'.join(h['connected_titles'][:5])})")

    if summary["kb_anchors"]:
        out += ["", "## KB-CONCEPTS (已被知识库锚定的知识点)"]
        for k in summary["kb_anchors"][:12]:
            out.append(f"- {k['entity']} (锚定 {k['anchored_nodes']} 个节点): {k['definition']}")

    out += ["", "## TRIPLES (图谱三元组：源 --关系--> 目标)"]
    for l in (summary.get("_raw_links") or [])[:max_triples]:
        label = l.get("relation_label") or RELATION_LABELS.get(l.get("relation_type"), "相关")
        tag = " [KB]" if l.get("kb_bridge") else ""
        out.append(f"{l['source_title']} --{label}--> {l['target_title']}{tag}")

    if summary["isolated"]:
        out += ["", "## GAPS (孤立/待补全)"]
        for n in summary["isolated"][:12]:
            out.append(f"- {n['title']} (L{n['level']}, {n['domain']})")

    if summary["suggestions"]:
        out += ["", "## SUGGESTIONS"]
        out.extend(f"- {s}" for s in summary["suggestions"])
    return "\n".join(out) + "\n"


def attach_raw_links(summary: Dict, db, user_id: int = 1) -> Dict:
    """把连线明细挂到 summary 上（Mermaid 与 digest 需要标题与方向）"""
    from app.models.models import Node, Link

    node_index = summary.get("node_index") or {}
    ids = [int(k) for k in node_index.keys()]
    if not ids:
        summary["_raw_links"] = []
        return summary
    links = db.query(Link).filter(
        Link.source_id.in_(ids), Link.target_id.in_(ids)
    ).all()
    raw = []
    for l in links:
        if l.is_render is False or l.source_id == l.target_id:
            continue
        s, t = str(l.source_id), str(l.target_id)
        if s not in node_index or t not in node_index:
            continue
        raw.append({
            "source": l.source_id,
            "target": l.target_id,
            "source_title": node_index[s]["title"],
            "target_title": node_index[t]["title"],
            "relation_type": l.relation_type or "related",
            "relation_label": l.relation_label or RELATION_LABELS.get(l.relation_type, "相关"),
            "score": round(l.score or 0, 3),
            "kb_bridge": bool(l.semantic_bridge) or l.source_file == "知识库",
        })
    raw.sort(key=lambda x: (-x["score"], x["source"]))
    summary["_raw_links"] = raw
    return summary
