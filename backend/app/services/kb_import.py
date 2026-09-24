"""知识库文档理解与导入

用户上传知识库文件 → 解析 → 与既有知识库比对（新增 / 同义合并 / 定义冲突）→
落库 → 输出人类可读的「理解报告」。

支持格式：
  - markdown 条目式：`## 实体 (别名)` + `别名:` / `关系:` / `bridge_sentence:` / `domain:` / 正文定义
  - markdown 表格：  `| 实体 | 别名 | 领域 | 定义 |`
  - csv / tsv：     表头含 实体/entity、别名/aliases、领域/domain、定义/definition、关系/related
  - json：          `[{...}]` 或 `{"entries": [...]}`
  - 纯文本：        `实体：定义` / `实体 - 定义` 逐行
"""
import csv
import io
import json
import re
from collections import Counter
from typing import Dict, List, Tuple

from loguru import logger

from app.seed import _infer_level, parse_kb_md

FIELD_ALIASES = {
    "entity": {"实体", "知识点", "名称", "概念", "entity", "name", "concept", "term"},
    "aliases": {"别名", "同义词", "又称", "aliases", "alias", "synonym"},
    "domain": {"领域", "分类", "学科", "domain", "category", "field"},
    "level": {"层级", "级别", "level", "layer"},
    "definition": {"定义", "描述", "释义", "说明", "definition", "desc", "description", "explain"},
    "related": {"关系", "相关", "关联", "相关术语", "related", "relation", "related_terms"},
    "bridge": {"桥接句", "bridge", "bridge_sentence", "例句"},
}

_SPLIT = re.compile(r"[,，;；、|]")


def _to_list(value) -> List[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    text = str(value).strip().strip("[]")
    if not text:
        return []
    return [x.strip() for x in _SPLIT.split(text) if x.strip()]


def _canon_field(name: str) -> str:
    # Excel 导出的 CSV/表头常带 BOM 或零宽字符，先清掉再匹配
    key = (name or "").replace("\ufeff", "").replace("\u200b", "").strip().lower()
    for canon, names in FIELD_ALIASES.items():
        if key in names:
            return canon
    return ""


# ---------------------------------------------------------------- 各格式解析


def _parse_table_rows(rows: List[List[str]]) -> List[Dict]:
    """把带表头的二维表转为条目列表"""
    if not rows:
        return []
    header = [_canon_field(h) for h in rows[0]]
    if "entity" not in header:
        return []
    out: List[Dict] = []
    for row in rows[1:]:
        if not any((c or "").strip() for c in row):
            continue
        item: Dict = {}
        for idx, field in enumerate(header):
            if not field or idx >= len(row):
                continue
            value = (row[idx] or "").strip()
            if not value:
                continue
            if field in ("aliases", "related"):
                item[field] = _to_list(value)
            elif field == "level":
                try:
                    item["level"] = int(float(value))
                except ValueError:
                    pass
            else:
                item[field] = value
        if item.get("entity"):
            out.append(item)
    return out


def _parse_csv(text: str) -> List[Dict]:
    sample = text[:2000]
    delimiter = "\t" if sample.count("\t") > sample.count(",") else ","
    rows = list(csv.reader(io.StringIO(text), delimiter=delimiter))
    return _parse_table_rows([r for r in rows if any((c or "").strip() for c in r)])


def _parse_markdown_table(text: str) -> List[Dict]:
    rows: List[List[str]] = []
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if all(re.fullmatch(r":?-{2,}:?", c or "-") for c in cells):
            continue  # 分隔行
        rows.append(cells)
    return _parse_table_rows(rows)


def _parse_json(text: str) -> List[Dict]:
    data = json.loads(text)
    if isinstance(data, dict):
        data = data.get("entries") or data.get("nodes") or data.get("data") or []
    if not isinstance(data, list):
        return []
    out: List[Dict] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        mapped: Dict = {"entity": "", "aliases": [], "related": []}
        for k, v in item.items():
            field = _canon_field(str(k))
            if not field:
                continue
            if field in ("aliases", "related"):
                mapped[field] = _to_list(v)
            elif field == "level":
                try:
                    mapped["level"] = int(float(v))
                except (TypeError, ValueError):
                    pass
            else:
                mapped[field] = str(v).strip()
        if mapped.get("entity"):
            out.append(mapped)
    return out


def _parse_plain(text: str) -> List[Dict]:
    """纯文本：`实体：定义` / `实体 - 定义` / `实体 — 定义`"""
    out: List[Dict] = []
    for line in text.splitlines():
        line = line.strip().lstrip("-*#> ").strip()
        if len(line) < 4 or len(line) > 300:
            continue
        m = re.match(r"^([^：:\-—]{2,40})\s*[：:—]\s*(.+)$", line) or \
            re.match(r"^([^\-—]{2,40}?)\s+-\s+(.+)$", line)
        if not m:
            continue
        entity, definition = m.group(1).strip(), m.group(2).strip()
        if len(definition) < 4:
            continue
        out.append({"entity": entity, "definition": definition, "aliases": [], "related": []})
    return out


def detect_format(name: str, text: str) -> str:
    lower = (name or "").lower()
    if lower.endswith(".json"):
        return "json"
    if lower.endswith((".csv", ".tsv")):
        return "csv"
    head = text[:1500]
    if re.search(r"^\s*[\[{]", head) and re.search(r"[\}\]]\s*$", text.strip()):
        try:
            json.loads(text)
            return "json"
        except (ValueError, TypeError):
            pass
    if re.search(r"^\s*\|.*\|\s*$", head, re.MULTILINE):
        return "markdown_table"
    if re.search(r"^#{1,3}\s+\S+", head, re.MULTILINE):
        return "markdown"
    return "text"


def parse_kb_document(name: str, content: str) -> Tuple[str, List[Dict]]:
    """解析知识库文档 → (格式, 条目列表[{entity, aliases, domain, level, definition, related, bridge}])"""
    content = (content or "").lstrip("\ufeff")
    fmt = detect_format(name, content)
    entries: List[Dict] = []
    try:
        if fmt == "json":
            entries = _parse_json(content)
        elif fmt == "csv":
            entries = _parse_csv(content)
        elif fmt == "markdown_table":
            entries = _parse_markdown_table(content)
        elif fmt == "markdown":
            entries = parse_kb_md(content)  # 复用项目语料同构解析
        else:
            entries = _parse_plain(content)
    except Exception as exc:  # 解析失败降级再试纯文本
        logger.warning(f"知识库文档解析失败（{fmt}）：{exc}")
        entries = _parse_plain(content)
        fmt = "text"

    normalized = []
    for e in entries:
        entity = (e.get("entity") or "").strip()
        if not entity:
            continue
        definition = (e.get("definition") or "").strip()
        bridges = e.get("bridge_sentences") or ([e["bridge"]] if e.get("bridge") else [])
        if e.get("bridge") and isinstance(e["bridge"], str) and not definition:
            definition = e["bridge"]
        normalized.append({
            "entity": entity[:255],
            "aliases": _to_list(e.get("aliases")),
            "domain": e.get("domain") or "general",
            "level": e.get("level"),
            "definition": definition[:2000] or entity,
            "related": _to_list(e.get("related")) or _to_list(e.get("related_terms")),
            "bridge_sentences": bridges,
            "raw": e,
        })
    return fmt, normalized


# ---------------------------------------------------------------- 理解与入库


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


def _reject_reason(entry: Dict) -> str:
    entity = entry["entity"]
    if len(entity) < 2:
        return "实体名过短"
    if re.fullmatch(r"[\d\W_]+", entity):
        return "实体名无有效字符"
    if entity.lower().startswith(("http", "www.")):
        return "疑似链接"
    if entry["definition"] == entity and not entry["aliases"] and not entry["related"]:
        return "只有名称、无定义/别名/关系（信息量不足）"
    return ""


def understand_kb_document(
    db, name: str, content: str, user_id: int = 1, dry_run: bool = False,
    overwrite_definitions: bool = False,
) -> Dict:
    """理解一份知识库文档并（可选）入库，返回理解报告。"""
    from app.models.models import KnowledgeBase, KbRelation, KbImport
    from app.services.kb_index import KbIndex, build_relations_from_entries, normalize_key

    fmt, entries = parse_kb_document(name, content)

    existing_rows = db.query(KnowledgeBase).all()
    index = KbIndex([{
        "entity": e.entity, "aliases": e.aliases or [], "domain": e.domain,
        "level": e.level or 3, "definition": e.definition,
    } for e in existing_rows])
    by_canonical = {e.entity: e for e in existing_rows}
    taken_entities = {normalize_key(e.entity) for e in existing_rows}
    taken_aliases = {normalize_key(a) for e in existing_rows for a in (e.aliases or [])}

    report = {
        "format": fmt,
        "total": len(entries),
        "new_entries": [], "merged_entries": [], "conflicts": [],
        "relations_added": [], "rejected": [],
        "dry_run": bool(dry_run),
    }
    pending_relations: List[Dict] = []
    new_canonicals: List[str] = []

    for entry in entries:
        reason = _reject_reason(entry)
        if reason:
            report["rejected"].append({"entity": entry["entity"][:60], "reason": reason})
            continue

        key = normalize_key(entry["entity"])
        canonical = index.alias_map.get(key) or index.alias_map.get(
            next((normalize_key(a) for a in entry["aliases"] if normalize_key(a) in index.alias_map), "")
        )
        row = by_canonical.get(canonical) if canonical else None

        # ---- 已存在：同义合并 ----
        if row:
            added_aliases, added_related, added_bridge = [], [], []
            alias_keys = {normalize_key(a) for a in (row.aliases or [])}
            for a in entry["aliases"] + ([entry["entity"]] if key != normalize_key(row.entity) else []):
                if normalize_key(a) and normalize_key(a) not in alias_keys:
                    added_aliases.append(a)
                    alias_keys.add(normalize_key(a))
            related_keys = {normalize_key(r) for r in (row.related_terms or [])}
            for r in entry["related"]:
                if normalize_key(r) and normalize_key(r) not in related_keys:
                    added_related.append(r)
                    related_keys.add(normalize_key(r))
            bridge_keys = {normalize_key(b) for b in (row.bridge_sentences or [])}
            for b in entry["bridge_sentences"]:
                if b and normalize_key(b) not in bridge_keys:
                    added_bridge.append(b)

            sim = _def_similarity(row.definition or "", entry["definition"])
            conflict = sim < 0.25 and len(entry["definition"]) > 8 and len(row.definition or "") > 8

            if conflict:
                report["conflicts"].append({
                    "entity": row.entity,
                    "existing": (row.definition or "")[:300],
                    "incoming": entry["definition"][:300],
                    "similarity": round(sim, 3),
                    "resolution": "覆盖（按用户选择）" if overwrite_definitions else "保留知识库既有定义",
                })
                if overwrite_definitions:
                    row.definition = entry["definition"]
            if added_aliases or added_related or added_bridge or conflict:
                if not dry_run:
                    row.aliases = list(dict.fromkeys((row.aliases or []) + added_aliases))
                    row.related_terms = list(dict.fromkeys((row.related_terms or []) + added_related))
                    row.bridge_sentences = list(dict.fromkeys((row.bridge_sentences or []) + added_bridge))
                report["merged_entries"].append({
                    "entity": row.entity,
                    "added_aliases": added_aliases,
                    "added_related": added_related,
                    "definition_conflict": conflict,
                })
            for r in entry["related"]:
                pending_relations.append({"source": row.entity, "target": r, "type": "related",
                                          "evidence": f"来自上传知识库《{name}》的「{row.entity}」相关术语"})
            continue

        # ---- 新知识点 ----
        level = entry["level"] or _infer_level(entry["entity"], entry["domain"], entry["related"])
        report["new_entries"].append({
            "entity": entry["entity"], "domain": entry["domain"], "level": level,
            "definition": entry["definition"][:200], "aliases": entry["aliases"],
        })
        new_canonicals.append(entry["entity"])
        taken_entities.add(key)
        for a in entry["aliases"]:
            taken_aliases.add(normalize_key(a))
        # 让后续条目也能命中本次新增（同批文件内的引用关系）
        index.alias_map.setdefault(key, entry["entity"])
        for a in entry["aliases"]:
            index.alias_map.setdefault(normalize_key(a), entry["entity"])

        if not dry_run:
            row = KnowledgeBase(
                entity=entry["entity"],
                aliases=entry["aliases"],
                domain=entry["domain"],
                level=level,
                definition=entry["definition"],
                source=f"upload:{name[:80]}",
                credibility=6,
                bridge_sentences=entry["bridge_sentences"],
                opposite_terms=[],
                related_terms=entry["related"],
            )
            db.add(row)
            db.flush()
            by_canonical[entry["entity"]] = row
        for r in entry["related"]:
            pending_relations.append({"source": entry["entity"], "target": r, "type": "related",
                                      "evidence": f"来自上传知识库《{name}》的「{entry['entity']}」相关术语"})

    # ---- 关系落库（目标必须能在知识库中找到，否则只作新术语候选） ----
    if not dry_run:
        known = {normalize_key(e.entity): e.entity for e in by_canonical.values()}
        for aliases_row in by_canonical.values():
            for a in (aliases_row.aliases or []):
                known.setdefault(normalize_key(a), aliases_row.entity)
        for rel in pending_relations:
            target = known.get(normalize_key(rel["target"]))
            source = known.get(normalize_key(rel["source"]))
            if not target or not source or target == source:
                continue
            exists = db.query(KbRelation).filter_by(
                source_entity=source, target_entity=target, relation_type=rel["type"]
            ).first()
            if exists:
                continue
            db.add(KbRelation(
                source_entity=source, target_entity=target, relation_type=rel["type"],
                relation_label="相关", weight=0.55, evidence=rel["evidence"][:400], origin="import",
            ))
            report["relations_added"].append({"source": source, "target": target, "type": rel["type"]})
        db.commit()

        # 由新条目继续推导（别名等价 / 桥接句）；只报告本次导入净增的关系数
        rel_before = db.query(KbRelation).count()
        build_relations_from_entries(db)
        report["relations_derived"] = max(0, db.query(KbRelation).count() - rel_before)

    stats = {
        "kb_total": db.query(KnowledgeBase).count(),
        "relations_total": db.query(KbRelation).count(),
    }
    report["stats"] = stats

    if not dry_run:
        record = KbImport(
            user_id=user_id, name=name, content=content[:200000], format=fmt,
            entry_total=report["total"], new_count=len(report["new_entries"]),
            merged_count=len(report["merged_entries"]), conflict_count=len(report["conflicts"]),
            relation_count=len(report["relations_added"]) + report.get("relations_derived", 0),
            rejected_count=len(report["rejected"]), status="done", report=report,
        )
        db.add(record)
        db.commit()
        report["import_id"] = record.id

    summary = (
        f"识别 {report['total']} 条：新增 {len(report['new_entries'])}、"
        f"同义合并 {len(report['merged_entries'])}、定义冲突 {len(report['conflicts'])}、"
        f"新增关系 {report.get('relations_derived', 0) + len(report['relations_added'])}、"
        f"未采纳 {len(report['rejected'])}"
    )
    report["summary"] = summary
    logger.info(f"知识库文档理解完成《{name}》：{summary}")
    return report
