"""SQLAlchemy 数据模型"""
from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Float, Boolean, Text, DateTime,
    ForeignKey, JSON, Index, UniqueConstraint
)
from sqlalchemy.orm import relationship
from app.database import Base


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(100), unique=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    files = relationship("File", back_populates="user", cascade="all, delete-orphan")
    nodes = relationship("Node", back_populates="user", cascade="all, delete-orphan")
    notes = relationship("Note", back_populates="user", cascade="all, delete-orphan")


class File(Base):
    __tablename__ = "files"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, default=1)
    name = Column(String(255), nullable=False)
    content = Column(Text)
    # 本地文件夹工作区（模块1）映射键：'ws:{workspaceId}:{relPath}'，普通上传为 NULL
    source_path = Column(String(255))
    uploaded_at = Column(DateTime, default=datetime.utcnow)
    parsed_at = Column(DateTime)
    status = Column(String(20), default="pending")  # pending, parsing, done, error
    node_count = Column(Integer, default=0)

    user = relationship("User", back_populates="files")
    nodes = relationship("Node", back_populates="file", cascade="all, delete-orphan")


class Node(Base):
    __tablename__ = "nodes"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, default=1)
    file_id = Column(Integer, ForeignKey("files.id"), nullable=False)
    entity = Column(String(255), nullable=False)
    title = Column(String(255))
    type = Column(String(50), default="knowledge")  # knowledge, note, question, thought
    description = Column(Text)
    content = Column(Text)
    keywords = Column(JSON)  # JSON array of strings
    entities = Column(JSON)  # JSON array of strings
    group_id = Column(String(100), default="default")
    group_name = Column(String(255), default="默认分组")
    level = Column(Integer, default=3)  # 1-4
    level_label = Column(String(50))
    domain = Column(String(100))
    embedding = Column(Text)  # JSON string of float array (SQLite兼容)
    metadata_ = Column("metadata", JSON)
    validated = Column(Boolean, default=False)
    validate_status = Column(String(20), default="pending")  # passed, warning, error, pending
    confidence = Column(Float)
    status = Column(String(20), default="active")  # active, discarded, pending
    visible = Column(Boolean, default=True)
    isolate_blacklist = Column(JSON)  # JSON array of blocked node IDs
    upload_time = Column(Float)  # timestamp
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="nodes")
    file = relationship("File", back_populates="nodes")
    sources = relationship("NodeSource", back_populates="node", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_nodes_file_id", "file_id"),
        Index("idx_nodes_user_status", "user_id", "status"),
    )


class NodeSource(Base):
    __tablename__ = "node_sources"
    id = Column(Integer, primary_key=True, autoincrement=True)
    node_id = Column(Integer, ForeignKey("nodes.id"), nullable=False)
    source_type = Column(String(20))  # file, note, corpus
    source_id = Column(Integer)
    paragraph = Column(Text)
    line_start = Column(Integer)
    line_end = Column(Integer)
    confidence = Column(Float)
    user_verified = Column(Boolean, default=False)

    node = relationship("Node", back_populates="sources")


class Link(Base):
    __tablename__ = "links"
    id = Column(Integer, primary_key=True, autoincrement=True)
    source_id = Column(Integer, ForeignKey("nodes.id"), nullable=False)
    target_id = Column(Integer, ForeignKey("nodes.id"), nullable=False)
    relation_type = Column(String(30), nullable=False, default="related")
    relation_label = Column(String(50))
    relation_color = Column(String(20))
    relation_line_style = Column(String(20))
    score = Column(Float)
    final_weight = Column(Float)
    is_render = Column(Boolean, default=True)
    evidence = Column(Text)
    evidence_source_id = Column(Integer)
    source_text = Column(Text)
    source_file = Column(String(255))
    auto_generated = Column(Boolean, default=True)
    user_confirmed = Column(Boolean, default=False)
    semantic_bridge = Column(Boolean, default=False)
    time_bridge = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("idx_links_source", "source_id"),
        Index("idx_links_target", "target_id"),
    )


class Note(Base):
    __tablename__ = "notes"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, default=1)
    title = Column(String(255), nullable=False)
    content = Column(Text)
    tags = Column(JSON)  # JSON array
    linked_files = Column(JSON)  # JSON array of file IDs
    linked_nodes = Column(JSON)  # JSON array of node IDs
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)
    version = Column(Integer, default=1)
    archived = Column(Boolean, default=False)
    verified = Column(Boolean, default=False)
    validation_status = Column(String(20), default="pending")
    accuracy_score = Column(Float)
    # 校验报告（v2：7 类 × 4 级 issue 列表 + summary），由 POST /api/validate 或前端保存时写入
    validation_report = Column(JSON)

    user = relationship("User", back_populates="notes")


class NoteNode(Base):
    __tablename__ = "note_nodes"
    note_id = Column(Integer, ForeignKey("notes.id"), primary_key=True)
    node_id = Column(Integer, ForeignKey("nodes.id"), primary_key=True)
    relation_type = Column(String(30))
    manual = Column(Boolean, default=False)
    confirmed = Column(Boolean, default=False)


class UserSettings(Base):
    __tablename__ = "user_settings"
    user_id = Column(Integer, ForeignKey("users.id"), primary_key=True)
    theme = Column(JSON)
    background = Column(JSON)
    weights = Column(JSON)  # { alpha, beta, gamma, delta }
    threshold = Column(Float)
    auto_confirm = Column(Boolean, default=False)
    strict_mode = Column(Boolean, default=False)
    corpus_enabled = Column(Boolean, default=True)
    show_system_nodes = Column(Boolean, default=False)


class IsolateBlacklist(Base):
    __tablename__ = "isolate_blacklist"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, default=1)
    node_id = Column(Integer, ForeignKey("nodes.id"), nullable=False)
    blocked_node_id = Column(Integer, ForeignKey("nodes.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("user_id", "node_id", "blocked_node_id", name="uq_isolate_pair"),
    )


class KnowledgeBase(Base):
    __tablename__ = "knowledge_base"
    id = Column(Integer, primary_key=True, autoincrement=True)
    entity = Column(String(255), nullable=False)
    aliases = Column(JSON)  # JSON array
    domain = Column(String(100))
    level = Column(Integer)
    definition = Column(Text)
    source = Column(String(100))
    credibility = Column(Integer, default=5)
    bridge_sentences = Column(JSON)  # JSON array
    opposite_terms = Column(JSON)  # JSON array
    related_terms = Column(JSON)  # JSON array
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("idx_kb_entity", "entity"),
        Index("idx_kb_domain", "domain"),
    )


# ============================================================ 知识库层（KB Layer）
# 知识库是本项目的「知识权威源」：文档上传后先锚定到知识库知识点，再由知识库
# 概念空间决定文件之间/知识点之间的关联，而不是直接拿文本向量比相似度。


class KbRelation(Base):
    """知识库内部关系边（本体图）。

    由条目自身的 related_terms / bridge_sentences 推导，也可由用户上传的知识库
    文档或手工维护补充。知识库推理（前置/包含/等价/对比）依赖此表。
    """
    __tablename__ = "kb_relations"
    id = Column(Integer, primary_key=True, autoincrement=True)
    source_entity = Column(String(255), nullable=False)
    target_entity = Column(String(255), nullable=False)
    relation_type = Column(String(30), nullable=False, default="related")
    relation_label = Column(String(50))
    weight = Column(Float, default=0.5)  # 0~1 关系强度
    evidence = Column(Text)              # 支撑原文（桥接句 / 相关术语行）
    origin = Column(String(20), default="derived")  # derived|import|manual
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("idx_kbrel_source", "source_entity"),
        Index("idx_kbrel_target", "target_entity"),
        UniqueConstraint("source_entity", "target_entity", "relation_type", name="uq_kbrel_triple"),
    )


class KbImport(Base):
    """用户上传知识库文档的导入记录与「理解报告」。"""
    __tablename__ = "kb_imports"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, default=1)
    name = Column(String(255), nullable=False)
    content = Column(Text)
    format = Column(String(20))          # markdown|csv|json|text
    entry_total = Column(Integer, default=0)
    new_count = Column(Integer, default=0)
    merged_count = Column(Integer, default=0)
    conflict_count = Column(Integer, default=0)
    relation_count = Column(Integer, default=0)
    rejected_count = Column(Integer, default=0)
    status = Column(String(20), default="done")  # done|dry_run|error
    report = Column(JSON)                # 完整理解报告（明细可下钻）
    created_at = Column(DateTime, default=datetime.utcnow)


class FileKnowledgeProfile(Base):
    """文件的知识画像：该文件在知识库概念空间上的稀疏权重向量。

    只由知识库锚定结果构成 —— 未被知识库覆盖的内容不进画像（知识边界）。
    """
    __tablename__ = "file_knowledge_profiles"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, default=1)
    file_id = Column(Integer, ForeignKey("files.id"), nullable=False)
    concepts = Column(JSON)      # [{entity, weight, count, via_alias, evidence}]
    domains = Column(JSON)       # {domain: weight}
    levels = Column(JSON)        # {"1": n, ...}
    anchor_count = Column(Integer, default=0)   # 命中知识点次数
    concept_count = Column(Integer, default=0)  # 去重知识点数
    coverage = Column(Float, default=0.0)       # 知识库覆盖率（命中字符/总字符）
    updated_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("file_id", name="uq_fkp_file"),
    )


class FileKnowledgeLink(Base):
    """文件与文件之间的知识关联边（由知识库概念空间计算，非文本语义相似度）。"""
    __tablename__ = "file_knowledge_links"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, default=1)
    source_file_id = Column(Integer, ForeignKey("files.id"), nullable=False)
    target_file_id = Column(Integer, ForeignKey("files.id"), nullable=False)
    kb_similarity = Column(Float, default=0.0)  # 综合知识相似度
    direct_score = Column(Float, default=0.0)   # 共享知识点
    bridge_score = Column(Float, default=0.0)   # 知识库关系边桥接
    domain_score = Column(Float, default=0.0)   # 领域/层级一致性
    shared_concepts = Column(JSON)  # [entity, ...]
    bridges = Column(JSON)          # [{from, to, relation_type, evidence}, ...]
    method = Column(String(30), default="kb_space")
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("source_file_id", "target_file_id", name="uq_fkl_pair"),
        Index("idx_fkl_source", "source_file_id"),
    )