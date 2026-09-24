"""文件解析服务：从 Markdown/文本中提取知识点"""
import re
import json
from datetime import datetime
from typing import List, Dict, Tuple
from loguru import logger
from app.models.models import File, Node, NodeSource


def parse_and_extract(file_id: int, user_id: int = 1):
    """解析文件内容，提取知识点节点

    流程：逐行抽取 → 归一化实体/别名 → 按(实体,领域)合并同义知识点 → 存库 → 向量化 → 自动推理。
    """
    from app.database import SessionLocal
    from app.services.vector_engine import embed_to_db

    db = SessionLocal()
    try:
        file_record = db.query(File).filter_by(id=file_id).first()
        if not file_record:
            logger.error(f"File {file_id} not found")
            return
        content = file_record.content or ""
        file_record.status = "parsing"
        nodes_data = extract_nodes_from_text(content, file_id, user_id)
        merged = merge_same_entity(nodes_data)
        saved_nodes = []
        for nd in merged:
            node = Node(
                user_id=user_id, file_id=file_id, entity=nd["entity"],
                title=nd.get("title", nd["entity"]), type=nd.get("type", "knowledge"),
                description=nd.get("description", ""), content=nd.get("content", ""),
                keywords=nd.get("keywords", []), entities=nd.get("entities", []),
                level=nd.get("level", 3), level_label=nd.get("level_label", ""),
                domain=nd.get("domain", ""), group_id=nd.get("group_id", "default"),
                group_name=nd.get("group_name", file_record.name),
                upload_time=datetime.utcnow().timestamp(),
                confidence=nd.get("confidence", 0.7), status="active"
            )
            db.add(node)
            db.flush()
            saved_nodes.append({
                "id": node.id, "entity": node.entity, "description": node.description,
                "keywords": node.keywords, "entities": node.entities,
                "level": node.level, "domain": node.domain,
                "group_id": node.group_id, "upload_time": node.upload_time
            })
            for raw in nd.get("raw_sources", []) or [nd.get("raw_text", "")]:
                source = NodeSource(
                    node_id=node.id, source_type="file", source_id=file_id,
                    paragraph=raw, line_start=nd.get("line_start", 0),
                    line_end=nd.get("line_end", 0), confidence=nd.get("confidence", 0.7)
                )
                db.add(source)
        file_record.status = "done"
        file_record.node_count = len(saved_nodes)
        file_record.parsed_at = datetime.utcnow()
        db.commit()
        if saved_nodes:
            embed_to_db(saved_nodes, db)
        if saved_nodes:
            try:
                from app.services.kb_link import kb_incremental_for_file
                kb_stats = kb_incremental_for_file(db, file_id, user_id)
                logger.info(
                    f"KB anchoring for {file_record.name}: "
                    f"{kb_stats['anchor']['anchored_nodes']} nodes anchored, "
                    f"kb node links={kb_stats['node_links']['total']}, "
                    f"file links={kb_stats['file_links']['links']}"
                )
            except Exception as kb_exc:
                logger.warning(f"KB anchoring skipped for file {file_id}: {kb_exc}")
        if saved_nodes:
            from app.services.inference import infer_links_for_new_file
            infer_links_for_new_file(file_id, user_id, db)
        logger.info(f"File {file_record.name} parsed: {len(saved_nodes)} nodes")
    except Exception as e:
        logger.error(f"Parse error for file {file_id}: {e}")
        if file_record:
            file_record.status = "error"
            db.commit()
    finally:
        db.close()


_VERB_MARKERS = [
    "特别擅长", "主要用于", "是一种", "指的是", "通常用于", "擅长",
    "基于", "通过", "利用", "采用", "引入", "降低", "提升", "解决",
    "使用", "适合", "得到", "分为", "包括", "包含", "依赖", "负责",
    "让", "把", "将", "从", "由", "使", "指", "是",
]

_SUBJECT_TRIM = re.compile(r"(完全|主要|通常|常|等|和|与|及|并且|之后|之中|中)$")
_EN_SUFFIX = ["架构", "技术", "模型", "机制", "方法", "算法", "框架", "语言", "网络", "结构"]


def _first_verb_pos(text: str) -> int:
    best = -1
    for verb in _VERB_MARKERS:
        idx = text.find(verb, 2)
        if idx != -1:
            best = idx if best == -1 else min(best, idx)
    return best


def _extract_subject(text: str) -> str:
    m = re.match(r'^([\u4e00-\u9fffA-Za-z0-9]{2,20})[（(]([A-Za-z0-9_\-]{1,10})[)）]([是:：]|$)', text)
    if m:
        return m.group(1)
    pos = _first_verb_pos(text)
    if pos >= 2:
        subject = text[:pos].strip(" ，,。:：")
        subject = _SUBJECT_TRIM.sub("", subject)
        if subject and len(subject) >= 2:
            return subject
    return ""


def normalize_entity(name: str) -> Tuple[str, List[str]]:
    name = name.strip(" ，,。:：.")
    if not name:
        return name, []
    aliases: List[str] = []
    m = re.match(r'^([\u4e00-\u9fff]{2,20})([A-Z]{2,8})$', name)
    if m:
        cn, abbr = m.groups()
        aliases.append(cn)
        return abbr, aliases
    m = re.match(r'^([A-Z]{2,10})([\u4e00-\u9fff]{4,20})$', name)
    if m:
        abbr, cn = m.groups()
        aliases.append(cn)
        return abbr, aliases
    m = re.match(r'^([\u4e00-\u9fff]{2,20})[（(]([A-Za-z0-9_\-]{1,12})[)）]$', name)
    if m:
        cn, abbr = m.groups()
        aliases.append(abbr)
        return cn, aliases
    m = re.match(r'^([A-Za-z][A-Za-z0-9_\-]{2,30})([\u4e00-\u9fff]{1,4})$', name)
    if m:
        en, suffix = m.groups()
        if suffix in _EN_SUFFIX:
            aliases.append(name)
            return en, aliases
    return name, aliases


def extract_entity(text: str, heading: str = "") -> str:
    subject = _extract_subject(text)
    if subject:
        ent, _ = normalize_entity(subject)
        return ent[:50]
    m = re.findall(r'[A-Z]{2,10}\d?', text)
    if m:
        return m[0]
    if heading and len(heading) <= 16 and len(heading) >= 2:
        return heading[:50]
    cn = re.findall(r'[\u4e00-\u9fff]{2,}', text)
    if cn:
        return cn[0][:50]
    return text[:50]


def extract_nodes_from_text(text: str, file_id: int, user_id: int) -> List[Dict]:
    nodes = []
    if not text or not text.strip():
        return nodes
    lines = text.split("\n")
    current_heading = ""
    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("#"):
            current_heading = stripped.lstrip("#").strip()
            continue
        sent_type = classify_sentence(stripped)
        if sent_type == "meta":
            continue
        entity = extract_entity(stripped, current_heading)
        keywords = extract_keywords(stripped)
        domain = classify_domain(stripped, current_heading)
        level = classify_level(entity, stripped)
        nodes.append({
            "entity": entity, "title": entity, "type": sent_type,
            "description": stripped[:500], "content": stripped,
            "keywords": keywords, "entities": keywords[:5],
            "level": level, "level_label": get_level_label(level),
            "domain": domain, "group_id": "default", "group_name": "",
            "confidence": estimate_confidence(stripped, sent_type),
            "raw_text": stripped, "raw_sources": [stripped],
            "line_start": i + 1, "line_end": i + 1
        })
    return nodes


def merge_same_entity(nodes: List[Dict]) -> List[Dict]:
    buckets: Dict[Tuple[str, str], Dict] = {}
    order: List[Tuple[str, str]] = []
    for nd in nodes:
        key = (nd["entity"], nd.get("domain", ""))
        if key not in buckets:
            buckets[key] = {
                "entity": nd["entity"], "title": nd["entity"], "type": nd["type"],
                "description": nd["description"], "content": nd.get("content", ""),
                "keywords": list(nd.get("keywords", [])), "entities": list(nd.get("entities", [])),
                "level": nd["level"], "level_label": nd["level_label"],
                "domain": nd.get("domain", ""), "group_id": nd.get("group_id", "default"),
                "group_name": nd.get("group_name", ""),
                "confidence": nd.get("confidence", 0.7),
                "raw_sources": list(nd.get("raw_sources", []) or [nd.get("raw_text", "")]),
                "line_start": nd.get("line_start", 0), "line_end": nd.get("line_end", 0),
            }
            order.append(key)
        else:
            b = buckets[key]
            if len(nd["description"]) > len(b["description"]):
                b["description"] = nd["description"]
            for raw in (nd.get("raw_sources", []) or [nd.get("raw_text", "")]):
                if raw not in b["raw_sources"]:
                    b["raw_sources"].append(raw)
            for kw in (nd.get("keywords", []) or []):
                if kw and kw not in b["keywords"]:
                    b["keywords"].append(kw)
            for ent in (nd.get("entities", []) or []):
                if ent and ent not in b["entities"]:
                    b["entities"].append(ent)
            b["confidence"] = max(b["confidence"], nd.get("confidence", 0))
            b["line_end"] = nd.get("line_end", b["line_end"])
    return [buckets[k] for k in order]


def classify_sentence(text: str) -> str:
    if re.match(r'^[#\-\*>\d]+', text) or re.match(r'^\d{4}[年/-]', text):
        return "meta"
    if re.search(r'[为什么|如何|怎么|怎样|什么|哪|谁|何时|是否|能否]', text):
        if text.endswith("?") or text.endswith("?") or "?" in text or "?" in text:
            return "question"
        if len(text) < 30 and re.search(r'[为什么|如何|怎么]', text):
            return "question"
    if re.search(r'[我觉得|我认为|可能|大概|似乎|不确定|不懂|不太清楚]', text):
        return "thought"
    if re.search(r'^(例如|比如|举例|如|举个|例如说)', text):
        return "example"
    return "knowledge"


def classify_level(entity: str, text: str = "") -> int:
    probe = f"{entity} {text}"
    l1_terms = [
        "人工智能", "机器学习", "深度学习", "编程范式", "面向对象编程", "函数式编程",
        "设计模式", "架构模式", "软件工程", "计算机科学", "数据结构", "算法",
        "操作系统", "计算机网络", "数据库", "知识图谱", "本体论", "语义网"
    ]
    if entity in l1_terms:
        return 1
    l4_patterns = [
        "pip", "npm", "docker", "git", "vscode", "intellij", "pycharm",
        "pytorch", "tensorflow", "spring", "django", "flask", "fastapi",
        "postgresql", "mongodb", "redis", "kafka", "kubernetes", "nginx",
        "vue", "react", "webpack", "vite", "electron", "typescript",
        "node.js", "javascript", "python", "java", "c++", "linux", "ubuntu",
    ]
    en = entity.lower()
    for p in l4_patterns:
        if p in en:
            return 4
    l2_words = ["原理", "理论", "模型", "定理", "定律", "机制", "策略", "协议",
                "标准", "规范", "范式", "方法论"]
    if any(w in entity for w in l2_words):
        return 2
    if any(w in probe for w in l2_words):
        return 2
    return 3


def get_level_label(level: int) -> str:
    labels = {1: "元概念", 2: "核心理论", 3: "应用实践", 4: "实现工具"}
    return labels.get(level, "应用实践")


def extract_keywords(text: str) -> List[str]:
    cn_words = re.findall(r'[\u4e00-\u9fff]{2,6}', text)
    en_words = re.findall(r'[A-Z]{2,8}|[A-Z][a-z]{2,}(?:\s+[A-Z][a-z]+)*|[a-z]+(?:_[a-z]+)+', text)
    words = list(dict.fromkeys(cn_words[:6] + [w for w in en_words if len(w) >= 2]))
    return words[:12]


def classify_domain(text: str, heading: str = "") -> str:
    combined = heading + " " + text
    domains = {
        "software": ["编程", "代码", "开发", "软件", "框架", "API", "库", "模块"],
        "embedded": ["嵌入式", "单片机", "硬件", "MCU", "ARM", "FPGA", "RTOS", "GPIO"],
        "ai": ["AI", "机器学习", "深度学习", "神经网络", "模型", "训练", "推理"],
        "network": ["网络", "HTTP", "TCP", "协议", "路由", "交换机", "DNS"],
        "database": ["数据库", "SQL", "NoSQL", "索引", "查询", "事务", "存储"],
        "writing": ["写作", "文章", "笔记", "文档", "阅读", "学习", "思考"],
    }
    for domain, keywords in domains.items():
        for kw in keywords:
            if kw.lower() in combined.lower():
                return domain
    return "software"


def estimate_confidence(text: str, sent_type: str) -> float:
    base = 0.7
    if sent_type == "knowledge":
        base = 0.8
    elif sent_type == "question":
        base = 0.4
    elif sent_type == "thought":
        base = 0.5
    if len(text) > 50:
        base += 0.1
    if len(text) > 100:
        base += 0.05
    if extract_keywords(text):
        base += 0.05
    return min(1.0, base)
