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
    # ---- 认证（补列，走 database._COLUMN_MIGRATIONS）----
    password_hash = Column(String(255))        # bcrypt；NULL=未初始化（旧 default 行）
    role = Column(String(20), default="user")  # user | admin
    is_disabled = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    files = relationship("File", back_populates="user", cascade="all, delete-orphan")
    nodes = relationship("Node", back_populates="user", cascade="all, delete-orphan")
    notes = relationship("Note", back_populates="user", cascade="all, delete-orphan")


class AuthSession(Base):
    """登录会话：不透明令牌的服务端记录（库中只存令牌的 SHA-256 哈希）。

    滑动续期：每次鉴权命中时 expires_at 顺延 SESSION_TTL_DAYS 天；
    登出/禁用用户时把 revoked 置 True，立即失效。
    """
    __tablename__ = "auth_sessions"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    token_hash = Column(String(64), unique=True, nullable=False)  # sha256 十六进制
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=False)
    last_seen_at = Column(DateTime, default=datetime.utcnow)
    revoked = Column(Boolean, default=False)

    __table_args__ = (
        Index("idx_session_user", "user_id"),
    )


class Diary(Base):
    """日记（Markdown，仅本人可见）"""
    __tablename__ = "diaries"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    title = Column(String(200))
    content_md = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("idx_diary_user_time", "user_id", "created_at"),
    )


class Favorite(Base):
    """公共知识库条目收藏；group_name 本期落库，UI 分组筛选属后续预留"""
    __tablename__ = "favorites"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    kb_entry_id = Column(Integer, ForeignKey("knowledge_base.id"), nullable=False)
    group_name = Column(String(50), default="")
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("user_id", "kb_entry_id", name="uq_fav_pair"),
    )


class MediaAsset(Base):
    """相册媒体（图片/视频）；大视频异步转码，状态机写回本表"""
    __tablename__ = "media_assets"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    kind = Column(String(10))                            # image | video
    url = Column(String(500))                            # /uploads/... 相对路径
    size_bytes = Column(Integer)
    duration_s = Column(Float)                           # 视频时长（ffprobe）
    transcode_status = Column(String(15), default="none")  # none|pending|processing|done|failed
    transcode_error = Column(String(300))
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("idx_media_user", "user_id"),
    )


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
    # 解析备注：如「文件过大，已截断为前 20000 行 / 600 个知识点」
    parse_note = Column(String(255))

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
    # 产生上面这条向量的引擎指纹（模式|模型|维度|算法版本）。
    # 换模型/换算法后旧向量与新向量维度不同、不可比较，靠它识别出来并重建。
    embedding_meta = Column(String(255))
    metadata_ = Column("metadata", JSON)
    validated = Column(Boolean, default=False)
    validate_status = Column(String(20), default="pending")  # passed, warning, error, pending
    confidence = Column(Float)
    status = Column(String(20), default="active")  # active, discarded, pending
    visible = Column(Boolean, default=True)
    isolate_blacklist = Column(JSON)  # JSON array of blocked node IDs
    upload_time = Column(Float)  # timestamp
    chunk_index = Column(Integer, default=0)  # 大文件被切割时，本节点来自第几片
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="nodes")
    file = relationship("File", back_populates="nodes")
    sources = relationship("NodeSource", back_populates="node", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_nodes_file_id", "file_id"),
        Index("idx_nodes_user_status", "user_id", "status"),
    )


class KnowledgeCandidate(Base):
    """候选知识点（待判定/已判定）

    大文件被智能切割后逐片解析，抽出的知识点先落这里；随后由「智能判定」给出
    分数与依据，按分级策略决定：自动入知识库 / 进待审队列 / 驳回。
    管理员可在后台看到每一条的判定依据（证据链）并人工裁决。
    """
    __tablename__ = "knowledge_candidates"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, default=1)
    file_id = Column(Integer, ForeignKey("files.id"))
    node_id = Column(Integer, ForeignKey("nodes.id"))
    chunk_index = Column(Integer, default=0)      # 来自第几片
    entity = Column(String(255), nullable=False)
    title = Column(String(255))
    description = Column(Text)
    keywords = Column(JSON)
    domain = Column(String(100))
    level = Column(Integer, default=3)
    source_text = Column(Text)                    # 原文证据
    line_start = Column(Integer)
    line_end = Column(Integer)
    extract_confidence = Column(Float, default=0.7)   # 抽取阶段置信度
    # ---- 判定结果 ----
    verdict_score = Column(Float)                 # 智能判定总分 0~1
    verdict_decision = Column(String(20), default="pending")  # accept|reject|pending
    verdict_reason = Column(Text)                 # 人类可读理由
    verdict_evidence = Column(JSON)               # 证据链 [{type, source, detail, url, weight}]
    verdict_stage = Column(String(20), default="auto")  # auto|human
    verdict_web = Column(String(20), default="skipped")  # ok|unavailable|skipped
    reviewed_by = Column(String(50))
    reviewed_at = Column(DateTime)
    review_note = Column(Text)
    status = Column(String(20), default="open")   # open|accepted|rejected|merged
    kb_entry_id = Column(Integer)                 # 入库后的知识库条目 id
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("idx_cand_status", "status", "verdict_decision"),
        Index("idx_cand_file", "file_id"),
    )


class AuditLog(Base):
    """操作审计：记录「谁做了什么、依据是什么」

    detail 里保存可复核的依据：输入快照、触发的规则/判定证据、结果与耗时。
    后台管理页据此还原"用户操作的根据"。
    """
    __tablename__ = "audit_logs"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, default=1)
    actor = Column(String(50), default="user")    # user|admin|system
    action = Column(String(60), nullable=False)   # upload|parse|split|verdict|review|delete|profile|kb_import...
    target_type = Column(String(40))              # file|node|candidate|kb_entry|profile|user
    target_id = Column(Integer)
    target_name = Column(String(255))
    summary = Column(String(500))
    detail = Column(JSON)                         # 依据明细
    status = Column(String(20), default="ok")     # ok|warn|error
    duration_ms = Column(Integer)
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("idx_audit_action", "action"),
        Index("idx_audit_created", "created_at"),
    )


class UserProfile(Base):
    """个人主页：昵称/简介/头像/自定义背景（图片存服务端 uploads 目录）"""
    __tablename__ = "user_profiles"
    user_id = Column(Integer, ForeignKey("users.id"), primary_key=True)
    display_name = Column(String(100))
    bio = Column(Text)
    avatar_url = Column(String(500))
    background_url = Column(String(500))
    background_config = Column(JSON)   # {opacity, blur, scope, fit}
    updated_at = Column(DateTime, default=datetime.utcnow)


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
    # ---- 公共知识库（补列，走 database._COLUMN_MIGRATIONS）----
    shared_by_user_id = Column(Integer)          # 署名用户；NULL=系统/种子条目（恒可见）
    is_published = Column(Boolean, default=True) # 下架/取消分享=FALSE（条目保留）
    shared_at = Column(DateTime)
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