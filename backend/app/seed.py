"""种子知识库加载（应用启动时自动执行，亦可供 CLI 复用）

解析 kg-vue3/src/domain_corpus/*.md 的**真实格式**（307+ 条目）：
    ## 面向对象编程 (OOP)
    - related_entities: [封装, 继承, 多态, ...]
    - bridge_sentence: 面向对象编程以封装、继承、多态三大特性组织代码结构...
    - domain: programming_paradigm
"""
import os
import re
from typing import List, Dict

from loguru import logger
from sqlalchemy.orm import Session

from app.database import SessionLocal, engine, Base
from app.models.models import User, KnowledgeBase

CORPUS_CANDIDATES = [
    os.path.join(os.path.dirname(__file__), "..", "..", "kg-vue3", "src", "domain_corpus"),
    os.path.join(os.path.dirname(__file__), "..", "..", "domain_corpus"),
]
CORPUS_FILES = ["software_kg.md", "software.md", "embedded.md", "writing.md"]


def _parse_aliases(name: str):
    m = re.match(r"^(.*?)[（(]([^（）()]*)[)）]$", name.strip())
    if m:
        entity = m.group(1).strip()
        alias = m.group(2).strip()
        if entity and alias and alias.lower() not in entity.lower():
            return entity, [alias]
    return name.strip(), []


def _infer_level(entity: str, domain: str, related: List[str]) -> int:
    """启发式推断知识层级（L1 元概念 / L4 具体工具 / L2 核心理论）"""
    en = entity.lower().strip()
    l1_terms = {"编程范式", "面向对象编程", "函数式编程", "软件工程", "计算机科学",
                "人工智能", "机器学习", "深度学习", "数据结构", "算法", "操作系统",
                "计算机网络", "数据库", "知识图谱", "语义网", "设计模式", "架构模式",
                "版本控制", "并发编程", "编译原理", "内存模型"}
    if entity in l1_terms:
        return 1
    l4_tokens = ["git", "docker", "kubernetes", "pytorch", "tensorflow", "vue", "react",
                 "spring", "mysql", "redis", "kafka", "nginx", "webpack", "vite",
                 "flask", "django", "fastapi", "postgresql", "mongodb", "sqlite",
                 "typescript", "javascript", "node.js", "python", "java", "c++",
                 "linux", "http", "tcp", "jvm", "golang", "rust", "electron", "axios"]
    if any(t in en for t in l4_tokens):
        return 4
    l2_words = ["原理", "理论", "模型", "协议", "机制", "范式", "标准", "设计模式", "设计"]
    if any(w in entity for w in l2_words):
        return 2
    return 3


def parse_kb_md(content: str) -> List[Dict]:
    """解析单份知识库语料 md，返回 KnowledgeBase 同构字典列表"""
    entries: List[Dict] = []
    sections = re.split(r"^##\s+", content, flags=re.MULTILINE)
    for section in sections[1:]:
        lines = [ln for ln in section.splitlines() if ln.strip()]
        if not lines:
            continue
        name = lines[0].strip().lstrip("#").strip()
        if not name or name.startswith("<!--"):
            continue
        entity, aliases = _parse_aliases(name)
        related: List[str] = []
        bridge_sentence = ""
        domain = "general"
        definition_paras: List[str] = []
        for line in lines[1:]:
            line = line.strip()
            m = re.match(r"^[-*]\s*related_entities\s*[:：]\s*(.*)$", line)
            if m:
                arr = m.group(1).strip()
                if arr.startswith("["):
                    arr = arr.strip("[]")
                related = [x.strip() for x in arr.split(",") if x.strip()]
                continue
            m = re.match(r"^[-*]\s*bridge_sentence\s*[:：]\s*(.*)$", line)
            if m:
                bridge_sentence = m.group(1).strip()
                continue
            m = re.match(r"^[-*]\s*domain\s*[:：]\s*(.*)$", line)
            if m:
                domain = m.group(1).strip() or "general"
                continue
            m = re.match(r"^[-*]?\s*别名\s*[:：]\s*(.*)$", line)
            if m:
                arr = m.group(1).strip()
                trio_aliases = [x.strip() for x in re.split(r"[,，]", arr) if x.strip()]
                if trio_aliases:
                    aliases = trio_aliases
                continue
            m = re.match(r"^[-*]?\s*(?:关系|关联)\s*[:：]\s*(.*)$", line)
            if m:
                arr = m.group(1).strip()
                if arr.startswith("["):
                    arr = arr.strip("[]")
                related = [x.strip() for x in re.split(r"[,，]", arr) if x.strip()]
                continue
            definition_paras.append(line)
        if not entity:
            continue
        if bridge_sentence:
            definition = bridge_sentence
        elif definition_paras:
            definition = "\n".join(p.strip() for p in definition_paras if p.strip())
        else:
            definition = entity
        entries.append({
            "entity": entity, "aliases": aliases, "domain": domain,
            "level": _infer_level(entity, domain, related),
            "definition": definition,
            "bridge_sentences": [bridge_sentence] if bridge_sentence else [],
            "related_terms": related, "opposite_terms": [],
            "source": "seed_corpus", "credibility": 5,
        })
    return entries


def load_all_corpora() -> List[Dict]:
    corpus_dirs = [c for c in CORPUS_CANDIDATES if os.path.isdir(c)]
    if not corpus_dirs:
        logger.warning("domain_corpus 目录不存在，将使用内置种子数据")
        return _builtin_entries()
    entries: List[Dict] = []
    for corpus_dir in corpus_dirs:
        for fname in CORPUS_FILES:
            path = os.path.join(corpus_dir, fname)
            if not os.path.isfile(path):
                continue
            with open(path, "r", encoding="utf-8") as f:
                parsed = parse_kb_md(f.read())
            logger.info(f"语料 {fname}: 解析 {len(parsed)} 条")
            entries.extend(parsed)
    return entries


def _builtin_entries() -> List[Dict]:
    return [
        {"entity": "面向对象编程", "aliases": ["OOP"], "domain": "programming_paradigm",
         "level": 1, "definition": "以封装、继承、多态组织代码的编程范式",
         "bridge_sentences": ["面向对象编程以封装、继承、多态三大特性组织代码结构"],
         "related_terms": ["封装", "继承", "多态", "类", "接口"], "opposite_terms": ["函数式编程"],
         "source": "builtin", "credibility": 5},
        {"entity": "封装", "aliases": [], "domain": "programming_paradigm", "level": 2,
         "definition": "绑定数据与操作并隐藏内部实现",
         "bridge_sentences": ["封装将数据与操作绑定并隐藏内部实现，是面向对象编程的根基"],
         "related_terms": ["面向对象编程", "继承", "多态"], "opposite_terms": [], "source": "builtin", "credibility": 5},
        {"entity": "继承", "aliases": [], "domain": "programming_paradigm", "level": 2,
         "definition": "子类复用父类成员实现代码复用的机制",
         "bridge_sentences": ["继承允许子类复用父类的字段与方法，是 OOP 实现代码复用的关键机制"],
         "related_terms": ["面向对象编程", "封装", "多态"], "opposite_terms": [], "source": "builtin", "credibility": 5},
        {"entity": "多态", "aliases": [], "domain": "programming_paradigm", "level": 2,
         "definition": "同一接口在不同类型上呈现不同行为",
         "bridge_sentences": ["多态通过动态绑定让同一接口呈现不同行为"],
         "related_terms": ["面向对象编程", "继承", "接口"], "opposite_terms": [], "source": "builtin", "credibility": 5},
        {"entity": "RESTful API", "aliases": ["REST"], "domain": "network", "level": 2,
         "definition": "基于 HTTP 的资源化 Web 服务架构风格",
         "bridge_sentences": ["RESTful API 通过 HTTP 协议实现客户端与服务端无状态通信"],
         "related_terms": ["HTTP", "JSON", "API"], "opposite_terms": [], "source": "builtin", "credibility": 5},
        {"entity": "Git", "aliases": ["Git版本控制"], "domain": "dev_tool", "level": 4,
         "definition": "分布式版本控制系统",
         "bridge_sentences": ["Git 通过分支管理实现并行开发，是团队协作的基础工具"],
         "related_terms": ["GitHub", "分支", "合并"], "opposite_terms": [], "source": "builtin", "credibility": 5},
    ]


def seed_knowledge_base(db: Session, force: bool = False) -> Dict[str, int]:
    if force:
        db.query(KnowledgeBase).filter(KnowledgeBase.source.in_(["seed_corpus", "builtin"])).delete()
        db.commit()
    existing_count = db.query(KnowledgeBase).count()
    if existing_count > 0 and not force:
        return {"status": "skipped", "count": existing_count}
    entries = load_all_corpora()
    imported = 0
    existing = {e.entity for e in db.query(KnowledgeBase).all()}
    for entry in entries:
        if entry["entity"] in existing:
            continue
        db.add(KnowledgeBase(**entry))
        imported += 1
    db.commit()
    total = db.query(KnowledgeBase).count()
    logger.info(f"种子知识库导入完成：新增 {imported} 条，当前共 {total} 条")
    return {"status": "seeded", "imported": imported, "count": total}


def ensure_default_user(db: Session) -> int:
    user = db.query(User).filter_by(id=1).first()
    if not user:
        user = User(id=1, username="default")
        db.add(user)
        db.commit()
        logger.info("已创建默认用户 user#1")
    return user.id


def bootstrap():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        ensure_default_user(db)
        return seed_knowledge_base(db)
    finally:
        db.close()


if __name__ == "__main__":
    import json
    print(json.dumps(bootstrap(), ensure_ascii=False, indent=2))
