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
    source_path = Column(String(255))
    uploaded_at = Column(DateTime, default=datetime.utcnow)
    parsed_at = Column(DateTime)
    status = Column(String(20), default="pending")
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
    type = Column(String(50), default="knowledge")
    description = Column(Text)
    content = Column(Text)
    keywords = Column(JSON)
    entities = Column(JSON)
    group_id = Column(String(100), default="default")
    group_name = Column(String(255), default="默认分组")
    level = Column(Integer, default=3)
    level_label = Column(String(50))
    domain = Column(String(100))
    embedding = Column(Text)
    metadata_ = Column("metadata", JSON)
    validated = Column(Boolean, default=False)
    validate_status = Column(String(20), default="pending")
    confidence = Column(Float)
    status = Column(String(20), default="active")
    visible = Column(Boolean, default=True)
    isolate_blacklist = Column(JSON)
    upload_time = Column(Float)
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
    source_type = Column(String(20))
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
    tags = Column(JSON)
    linked_files = Column(JSON)
    linked_nodes = Column(JSON)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)
    version = Column(Integer, default=1)
    archived = Column(Boolean, default=False)
    verified = Column(Boolean, default=False)
    validation_status = Column(String(20), default="pending")
    accuracy_score = Column(Float)
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
    weights = Column(JSON)
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
    aliases = Column(JSON)
    domain = Column(String(100))
    level = Column(Integer)
    definition = Column(Text)
    source = Column(String(100))
    credibility = Column(Integer, default=5)
    bridge_sentences = Column(JSON)
    opposite_terms = Column(JSON)
    related_terms = Column(JSON)
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("idx_kb_entity", "entity"),
        Index("idx_kb_domain", "domain"),
    )


class KbRelation(Base):
    __tablename__ = "kb_relations"
    id = Column(Integer, primary_key=True, autoincrement=True)
    source_entity = Column(String(255), nullable=False)
    target_entity = Column(String(255), nullable=False)
    relation_type = Column(String(30), nullable=False, default="related")
    relation_label = Column(String(50))
    weight = Column(Float, default=0.5)
    evidence = Column(Text)
    origin = Column(String(20), default="derived")
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("idx_kbrel_source", "source_entity"),
        Index("idx_kbrel_target", "target_entity"),
        UniqueConstraint("source_entity", "target_entity", "relation_type", name="uq_kbrel_triple"),
    )


class KbImport(Base):
    __tablename__ = "kb_imports"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, default=1)
    name = Column(String(255), nullable=False)
    content = Column(Text)
    format = Column(String(20))
    entry_total = Column(Integer, default=0)
    new_count = Column(Integer, default=0)
    merged_count = Column(Integer, default=0)
    conflict_count = Column(Integer, default=0)
    relation_count = Column(Integer, default=0)
    rejected_count = Column(Integer, default=0)
    status = Column(String(20), default="done")
    report = Column(JSON)
    created_at = Column(DateTime, default=datetime.utcnow)


class FileKnowledgeProfile(Base):
    __tablename__ = "file_knowledge_profiles"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, default=1)
    file_id = Column(Integer, ForeignKey("files.id"), nullable=False)
    concepts = Column(JSON)
    domains = Column(JSON)
    levels = Column(JSON)
    anchor_count = Column(Integer, default=0)
    concept_count = Column(Integer, default=0)
    coverage = Column(Float, default=0.0)
    updated_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("file_id", name="uq_fkp_file"),
    )


class FileKnowledgeLink(Base):
    __tablename__ = "file_knowledge_links"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, default=1)
    source_file_id = Column(Integer, ForeignKey("files.id"), nullable=False)
    target_file_id = Column(Integer, ForeignKey("files.id"), nullable=False)
    kb_similarity = Column(Float, default=0.0)
    direct_score = Column(Float, default=0.0)
    bridge_score = Column(Float, default=0.0)
    domain_score = Column(Float, default=0.0)
    shared_concepts = Column(JSON)
    bridges = Column(JSON)
    method = Column(String(30), default="kb_space")
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("source_file_id", "target_file_id", name="uq_fkl_pair"),
        Index("idx_fkl_source", "source_file_id"),
    )
