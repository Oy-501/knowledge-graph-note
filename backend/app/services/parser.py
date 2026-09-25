"""文件解析服务：从 Markdown/文本中提取知识点"""
import re
import json
from datetime import datetime
from typing import List, Dict, Tuple
from loguru import logger
from app.models.models import File, Node, NodeSource


def parse_and_extract(file_id: int, user_id: int = 1):
    """解析文件内容，提取知识点节点

    流程：规划切割 → 逐片抽取 → 归一化实体/别名 → 按(实体,领域)合并同义知识点 →
    存库 → 向量化 → 知识库锚定与关联 → 四维推理 → 生成候选知识点并做智能判定。

    大文件策略（不再丢内容）：超过阈值时按**结构边界**切成多片（见 file_splitter），
    每片带上标题上下文单独解析，切完仍能完整读取知识点；片内仍有行数/知识点上限兜底，
    总量上限由 MAX_NODES_PER_FILE_TOTAL 控制。
    """
    import time as _time
    from app.database import SessionLocal
    from app.config import settings
    from app.services.vector_engine import embed_to_db
    from app.services.file_splitter import plan_split, piece_text, describe_plan
    from app.services import audit

    started = _time.time()
    db = SessionLocal()
    try:
        file_record = db.query(File).filter_by(id=file_id).first()
        if not file_record:
            logger.error(f"File {file_id} not found")
            return

        content = file_record.content or ""
        file_record.status = "parsing"
        file_record.parse_note = None

        notes: List[str] = []
        plan = plan_split(
            content,
            target_lines=settings.SPLIT_TARGET_LINES,
            target_chars=settings.SPLIT_TARGET_CHARS,
            max_pieces=settings.SPLIT_MAX_PIECES,
            overlap_lines=settings.SPLIT_OVERLAP_LINES,
        )

        if plan["needed"]:
            audit.log_event(
                db, "split", actor="system", user_id=user_id, target_type="file",
                target_id=file_id, target_name=file_record.name,
                summary=describe_plan(plan),
                detail={
                    "total_lines": plan["total_lines"],
                    "total_chars": plan["total_chars"],
                    "pieces": [{"index": p["index"], "start": p["start"], "end": p["end"],
                                "lines": p["lines"], "heading_path": p["heading_path"],
                                "reason": p["reason"]} for p in plan["pieces"]],
                    "rule": "优先标题边界 → 段落边界 → 强制行数；每片带标题上下文 + 相邻片重叠",
                },
            )
            notes.append(f"文件较大，已智能切割为 {len(plan['pieces'])} 片逐片解析（内容完整覆盖）")

        # ---- 逐片抽取（未切割时就是整篇一片）----
        all_nodes: List[Dict] = []
        per_piece_stat: List[Dict] = []
        total_cap = settings.MAX_NODES_PER_FILE_TOTAL if plan["needed"] else settings.MAX_NODES_PER_FILE

        for piece in plan["pieces"]:
            text = piece_text(content, piece)
            chunk_nodes, trunc = extract_nodes_from_text(
                text, file_id, user_id,
                max_lines=settings.MAX_PARSE_LINES,
                max_nodes=settings.MAX_NODES_PER_FILE,
            )
            for nd in chunk_nodes:
                nd["chunk_index"] = piece["index"]
                nd["heading_path"] = piece.get("heading_path", "")
            all_nodes.extend(chunk_nodes)
            per_piece_stat.append({
                "index": piece["index"], "lines": piece["lines"],
                "extracted": len(chunk_nodes),
                "truncated": bool(trunc["lines_truncated"] or trunc["nodes_truncated"]),
            })
            if len(all_nodes) >= total_cap:
                notes.append(f"知识点总量已达上限 {total_cap} 个，其余分片未再抽取")
                break

        merged = merge_same_entity(all_nodes)
        if len(merged) > total_cap:
            merged = merged[:total_cap]
            notes.append(f"知识点总量已达上限 {total_cap} 个")

        # 存入数据库
        saved_nodes = []
        for nd in merged:
            node = Node(
                user_id=user_id,
                file_id=file_id,
                entity=nd["entity"],
                title=nd.get("title", nd["entity"]),
                type=nd.get("type", "knowledge"),
                description=nd.get("description", ""),
                content=nd.get("content", ""),
                keywords=nd.get("keywords", []),
                entities=nd.get("entities", []),
                level=nd.get("level", 3),
                level_label=nd.get("level_label", ""),
                domain=nd.get("domain", ""),
                group_id=nd.get("group_id", "default"),
                group_name=nd.get("group_name", file_record.name),
                upload_time=datetime.utcnow().timestamp(),
                confidence=nd.get("confidence", 0.7),
                chunk_index=nd.get("chunk_index", 0),
                status="active"
            )
            db.add(node)
            db.flush()  # 获取ID
            saved_nodes.append({
                "id": node.id,
                "entity": node.entity,
                "description": node.description,
                "keywords": node.keywords,
                "entities": node.entities,
                "level": node.level,
                "domain": node.domain,
                "group_id": node.group_id,
                "upload_time": node.upload_time,
                "chunk_index": node.chunk_index,
                "raw_text": (nd.get("raw_sources") or [""])[0],
                "line_start": nd.get("line_start", 0),
                "line_end": nd.get("line_end", 0),
                "confidence": nd.get("confidence", 0.7),
            })

            # 存储来源（一个知识点可对应多个原文段落）
            for raw in nd.get("raw_sources", []) or [nd.get("raw_text", "")]:
                source = NodeSource(
                    node_id=node.id,
                    source_type="file",
                    source_id=file_id,
                    paragraph=raw,
                    line_start=nd.get("line_start", 0),
                    line_end=nd.get("line_end", 0),
                    confidence=nd.get("confidence", 0.7)
                )
                db.add(source)

        # 先更新节点数（让前端在解析过程中就能看到进度），
        # 但状态保持 parsing —— 直到锚定/关联/候选判定全部完成才算 done
        file_record.node_count = len(saved_nodes)
        db.commit()

        audit.log_event(
            db, "parse", actor="system", user_id=user_id, target_type="file",
            target_id=file_id, target_name=file_record.name,
            summary=f"解析出 {len(saved_nodes)} 个知识点（{len(plan['pieces'])} 片）",
            detail={
                "pieces": per_piece_stat,
                "split_plan": describe_plan(plan),
                "merged_nodes": len(saved_nodes),
                "notes": notes,
                "limits": {"per_piece_nodes": settings.MAX_NODES_PER_FILE,
                           "total_nodes": total_cap,
                           "lines_per_piece": settings.MAX_PARSE_LINES},
            },
            duration_ms=int((_time.time() - started) * 1000),
        )

        # 生成向量
        if saved_nodes:
            embed_to_db(saved_nodes, db)

        # ★ 知识库层：先把节点锚定到知识库知识点，再由知识库决定关联
        #   （锚定 → 知识画像 → 知识锚定连线 → 文件间知识关联）
        #   放在四维推理之前：锚定补齐的 entities/层面信息会参与后续推理
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

        # 自动推理关联（四维加权，其中 γ 维直接读知识库桥接）
        if saved_nodes:
            from app.services.inference import infer_links_for_new_file
            infer_links_for_new_file(file_id, user_id, db)

        # ★ 候选知识点：把抽出的知识点存入候选池并立即做智能判定
        #   （分级：高置信自动入知识库 / 中等进后台待审 / 低分驳回）
        if saved_nodes:
            try:
                cand_stats = create_candidates_and_verify(db, file_id, user_id, saved_nodes)
                logger.info(f"候选知识点判定：{cand_stats}")
                if cand_stats.get("total"):
                    notes.append(
                        f"候选知识点 {cand_stats['total']} 条：自动采纳 {cand_stats['accept']}、"
                        f"待审 {cand_stats['pending']}、驳回 {cand_stats['reject']}"
                    )
            except Exception as cand_exc:
                logger.warning(f"候选知识点判定失败（不影响解析）：{cand_exc}")

        logger.info(f"File {file_record.name} parsed: {len(saved_nodes)} nodes")

        # 全流程结束才置 done（前端「解析中/已索引」徽标与后台统计都依赖这个语义）
        file_record.status = "done"
        file_record.parsed_at = datetime.utcnow()
        file_record.parse_note = "；".join(notes)[:250] if notes else None
        db.commit()

    except Exception as e:
        logger.error(f"Parse error for file {file_id}: {e}")
        if file_record:
            file_record.status = "error"
            file_record.parse_note = f"解析失败：{str(e)[:200]}"
            db.commit()
    finally:
        db.close()


def create_candidates_and_verify(db, file_id: int, user_id: int, saved_nodes: List[Dict]) -> Dict:
    """把节点写入候选池并批量智能判定（返回统计）"""
    from app.models.models import KnowledgeCandidate
    from app.services import knowledge_verifier

    # 重复解析时先清掉该文件旧的候选（幂等）
    db.query(KnowledgeCandidate).filter_by(file_id=file_id).delete(synchronize_session=False)
    db.commit()

    candidates = []
    for nd in saved_nodes:
        c = KnowledgeCandidate(
            user_id=user_id, file_id=file_id, node_id=nd.get("id"),
            chunk_index=nd.get("chunk_index", 0),
            entity=nd.get("entity") or "",
            title=nd.get("entity") or "",
            description=nd.get("description") or "",
            keywords=nd.get("keywords") or [],
            domain=nd.get("domain") or "general",
            level=nd.get("level") or 3,
            source_text=(nd.get("raw_text") or "")[:2000],
            line_start=nd.get("line_start"), line_end=nd.get("line_end"),
            extract_confidence=nd.get("confidence", 0.7),
            status="open",
        )
        db.add(c)
        candidates.append(c)
    db.commit()

    return knowledge_verifier.verify_batch(db, candidates)


# ---------------------------------------------------------- 主语/实体识别
# 常见“主语-谓语”连接词/动词（按优先级从长到短匹配），用于切出句子的主语实体
# 注意：剔除易被误命中为“词中成分”的动词（处理/应用/生成/完成等），
#       这些词常出现在复合名词中间（如“自然语言处理”“并行计算”）。
_VERB_MARKERS = [
    "特别擅长", "主要用于", "是一种", "指的是", "通常用于", "擅长",
    "基于", "通过", "利用", "采用", "引入", "降低", "提升", "解决",
    "使用", "适合", "得到", "分为", "包括", "包含", "依赖", "负责",
    "让", "把", "将", "从", "由", "使", "指", "是",
]

# 主语尾缀清理（切分残留的修饰词）
_SUBJECT_TRIM = re.compile(r"(完全|主要|通常|常|等|和|与|及|并且|之后|之中|中)$")

# 编号前缀（章节标题「一、」「（2）」「3.」）
_NUM_PREFIX = re.compile(r"^[（(]?[一二三四五六七八九十百千\d]{1,3}[)）、.．]\s*")

# 谓语片段起手词：这些词开头的短语不是知识点名称（「负责把大任务拆解…」「分为三类记忆」）
_FRAGMENT_START = re.compile(
    r"^(分为|负责|增加|加入|注入|记录|执行|保存|放到|放在|用于|包括|包含|例如|通过|采用|"
    r"基于|作为|实现|提供|指的|表示|说明|解决|支持|遵循|减少|提升|降低|避免|防止|保证|"
    r"确保|需要|可以|不要|能够|使得)"
)

# 主语长度上限：超过说明切出来的是一整句话而非术语
_MAX_SUBJECT_LEN = 24

# 通用后缀：实体归一化时剥离（仅当实体为“纯英文缩写 + 中文类别词”结构）
_EN_SUFFIX = ["架构", "技术", "模型", "机制", "方法", "算法", "框架", "语言", "网络", "结构"]


def _clean_heading(heading: str) -> str:
    """清洗章节标题：去掉编号前缀与空白（「一、基础概念辨析」→「基础概念辨析」）"""
    return _NUM_PREFIX.sub("", (heading or "").strip().lstrip("#").strip()).strip(" ，,。:：.、")


def _first_verb_pos(text: str) -> int:
    """返回首个谓语连接词的位置（从 2 个字之后才开始找，避免吃掉短主语）"""
    best = -1
    for verb in _VERB_MARKERS:
        idx = text.find(verb, 2)
        if idx != -1:
            best = idx if best == -1 else min(best, idx)
    return best


def _extract_subject(text: str) -> str:
    """切分句子得到核心主语（实体名候选）

    返回空串表示「这一句切不出知识点名称」，由 extract_entity 走兜底或丢弃 ——
    宁可少一个节点，也不要产出「负责」「分为三类记忆」这种假知识点。
    """
    # 形如 “X（AI）是/：“ 的括号缩写紧跟主语
    m = re.match(r'^([\u4e00-\u9fffA-Za-z0-9]{2,20})[（(]([A-Za-z0-9_\-]{1,10})[)）]([是:：]|$)', text)
    if m:
        return m.group(1)

    pos = _first_verb_pos(text)
    if pos > _MAX_SUBJECT_LEN:
        # 第一个谓语离句首太远 → 切出来的是一整句话，不是术语
        return ""
    if pos >= 2:
        subject = text[:pos].strip(" ，,。:：")
        # 只取第一个分句（「React 与 Vue 都基于…」→ 去掉后半句）
        subject = re.split(r"[，,；;、]", subject)[0].strip()
        subject = _SUBJECT_TRIM.sub("", subject)
        # 清掉结尾的语气/连接字（「React 与 Vue 都」→「React 与 Vue」）
        subject = re.sub(r"[都也就而并又等和与及的之了]+$", "", subject).strip()
        if not subject or len(subject) < 2:
            return ""
        if _FRAGMENT_START.match(subject):
            # 「分为三类记忆」「负责把大任务…」：谓语片段，不是知识点名
            return ""
        return subject
    return ""


def normalize_entity(name: str) -> Tuple[str, List[str]]:
    """归一化实体名，返回 (实体, 别名列表)

    - “循环神经网络RNN” → (RNN, [循环神经网络])，避免跨文档重复
    - “Transformer架构” → (Transformer, [])
    - “自然语言处理（NLP）” → (自然语言处理, [NLP])
    """
    name = name.strip(" ，,。:：.")
    if not name:
        return name, []

    aliases: List[str] = []

    # 中文 + 尾部大写缩写（如 卷积神经网络CNN / 循环神经网络RNN / 自然语言处理NLP）
    m = re.match(r'^([\u4e00-\u9fff]{2,20})([A-Z]{2,8})$', name)
    if m:
        cn, abbr = m.groups()
        aliases.append(cn)
        return abbr, aliases

    # 大写缩写开头 + 中文全称（如 LSTM长短期记忆网络 → LSTM）
    m = re.match(r'^([A-Z]{2,10})([\u4e00-\u9fff]{4,20})$', name)
    if m:
        abbr, cn = m.groups()
        aliases.append(cn)
        return abbr, aliases

    # 中文（括号缩写）→ 归一为中文本体 + 别名
    m = re.match(r'^([\u4e00-\u9fff]{2,20})[（(]([A-Za-z0-9_\-]{1,12})[)）]$', name)
    if m:
        cn, abbr = m.groups()
        aliases.append(abbr)
        return cn, aliases

    # 英文/中英混合 + 中文类别后缀（Transformer架构 / LSTM网络）
    m = re.match(r'^([A-Za-z][A-Za-z0-9_\-]{2,30})([\u4e00-\u9fff]{1,4})$', name)
    if m:
        en, suffix = m.groups()
        if suffix in _EN_SUFFIX:
            aliases.append(name)
            return en, aliases

    return name, aliases


def extract_entity(text: str, heading: str = "") -> str:
    """提取句子的核心实体名（优先真实主语，其次正文名词短语，标题兜底）

    取不到合适的实体名时返回空串 —— 调用方据此丢弃该行，
    避免把章节标题或谓语片段（「负责」「一、基础概念辨析」）做成假知识点。
    """
    subject = _extract_subject(text)
    if subject:
        ent, _ = normalize_entity(subject)
        return ent[:50]

    # 兜底 1：正文中出现的大写缩写（CNN / NLP / BERT / 循环神经网络RNN 等）
    m = re.findall(r'[A-Z]{2,10}\d?', text)
    if m:
        return m[0]

    # 兜底 2：标题（先清掉编号，且只接受长度适中的标题）
    clean_heading = _clean_heading(heading)
    if clean_heading and 2 <= len(clean_heading) <= 16:
        return clean_heading[:50]

    # 兜底 3：正文前 2~4 个汉字组成的短语（谓语片段起手则放弃）
    if not _FRAGMENT_START.match(text.strip(" ，,。:：、-")):
        cn = re.findall(r'[\u4e00-\u9fff]{2,}', text)
        if cn:
            return cn[0][:50]
    return ""


def extract_nodes_from_text(text: str, file_id: int, user_id: int,
                            max_lines: int = 0, max_nodes: int = 0) -> Tuple[List[Dict], Dict]:
    """从文本中提取知识点（按行抽取；同义合并交给 merge_same_entity）

    返回 (节点列表, 截断信息)。max_lines / max_nodes 为 0 表示不限制；
    大文件必须限量，否则几万行会同时压垮解析、关联推理与前端渲染。
    """
    nodes: List[Dict] = []
    trunc = {"lines_truncated": False, "nodes_truncated": False,
             "total_lines": 0, "scanned_lines": 0}
    if not text or not text.strip():
        return nodes, trunc

    lines = text.split("\n")
    trunc["total_lines"] = len(lines)
    if max_lines and len(lines) > max_lines:
        lines = lines[:max_lines]
        trunc["lines_truncated"] = True
    trunc["scanned_lines"] = len(lines)

    current_heading = ""
    current_section = ""

    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            continue

        # 标题行：记录层级标题（去掉编号前缀），不生成节点
        if stripped.startswith("#"):
            current_heading = _clean_heading(stripped)
            continue

        # 分类句子
        sent_type = classify_sentence(stripped)

        if sent_type == "meta":
            continue

        # 提取实体（主语优先）；切不出知识点名称的行直接丢弃
        entity = extract_entity(stripped, current_heading)
        if not entity:
            continue
        keywords = extract_keywords(stripped)
        domain = classify_domain(stripped, current_heading)
        level = classify_level(entity, stripped)

        nodes.append({
            "entity": entity,
            "title": entity,
            "type": sent_type,
            "description": stripped[:500],
            "content": stripped,
            "keywords": keywords,
            "entities": keywords[:5],
            "level": level,
            "level_label": get_level_label(level),
            "domain": domain,
            "group_id": "default",
            "group_name": "",
            "confidence": estimate_confidence(stripped, sent_type),
            "raw_text": stripped,
            "raw_sources": [stripped],
            "line_start": i + 1,
            "line_end": i + 1
        })

        # 知识点数上限：到顶就停，剩下的内容不再抽取
        if max_nodes and len(nodes) >= max_nodes:
            trunc["nodes_truncated"] = True
            break

    return nodes, trunc


def merge_same_entity(nodes: List[Dict]) -> List[Dict]:
    """同文件内按 (实体, 领域) 合并同义知识点（§8 同义去重的保守实现：
    仅合并实体名完全一致且来源于同一文件的节点，保留各自原文作为多条来源）"""
    buckets: Dict[Tuple[str, str], Dict] = {}
    order: List[Tuple[str, str]] = []

    for nd in nodes:
        key = (nd["entity"], nd.get("domain", ""))
        if key not in buckets:
            buckets[key] = {
                "entity": nd["entity"],
                "title": nd["entity"],
                "type": nd["type"],
                "description": nd["description"],
                "content": nd.get("content", ""),
                "keywords": list(nd.get("keywords", [])),
                "entities": list(nd.get("entities", [])),
                "level": nd["level"],
                "level_label": nd["level_label"],
                "domain": nd.get("domain", ""),
                "group_id": nd.get("group_id", "default"),
                "group_name": nd.get("group_name", ""),
                "confidence": nd.get("confidence", 0.7),
                "raw_sources": list(nd.get("raw_sources", []) or [nd.get("raw_text", "")]),
                "line_start": nd.get("line_start", 0),
                "line_end": nd.get("line_end", 0),
            }
            order.append(key)
        else:
            b = buckets[key]
            # 取最长描述，合并其余原文与关键词
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
    """句子分类：knowledge/question/thought/example/meta"""
    if re.match(r'^[#\-\*>\d]+', text) or re.match(r'^\d{4}[年/-]', text):
        return "meta"
    # 中文编号小节标题（「一、基础概念辨析」「（2）实现」「3. Tools 工具模块」）：
    # 与 `# 标题` 同性质，属于结构而非知识点 —— 否则会产出名为「一、基础概念辨析」的假知识点
    if re.match(r'^[（(]?[一二三四五六七八九十百千\d]{1,3}[)）、.．]\s*\S', text):
        return "meta"
    if re.search(r'[为什么|如何|怎么|怎样|什么|哪|谁|何时|是否|能否]', text):
        if text.endswith("?") or text.endswith("？") or "?" in text or "？" in text:
            return "question"
        if len(text) < 30 and re.search(r'[为什么|如何|怎么]', text):
            return "question"
    if re.search(r'[我觉得|我认为|可能|大概|似乎|不确定|不懂|不太清楚]', text):
        return "thought"
    if re.search(r'^(例如|比如|举例|如|举个|例如说)', text):
        return "example"
    return "knowledge"


def classify_level(entity: str, text: str = "") -> int:
    """层级判定（基于实体 + 句内证据，避免被章节标题带偏）：

    L1 元概念 / L2 核心理论 / L3 具体技术 / L4 实现工具
    """
    probe = f"{entity} {text}"

    # L1: 实体本身是顶层元概念
    l1_terms = [
        "人工智能", "机器学习", "深度学习", "编程范式", "面向对象编程", "函数式编程",
        "设计模式", "架构模式", "软件工程", "计算机科学", "数据结构", "算法",
        "操作系统", "计算机网络", "数据库", "知识图谱", "本体论", "语义网"
    ]
    if entity in l1_terms:
        return 1
    # 句内以“XX 是 YY 的分支/学科/领域”方式定义 L1 元概念的下级关系，仍按实体主判定

    # L4: 实体是具体实现/工具/语言/库
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

    # L2: 术语本身或句内出现核心理论特征词
    l2_words = ["原理", "理论", "模型", "定理", "定律", "机制", "策略", "协议",
                "标准", "规范", "范式", "方法论"]
    if any(w in entity for w in l2_words):
        return 2
    if any(w in probe for w in l2_words):
        return 2

    # L3: 具体技术（默认）
    return 3


def get_level_label(level: int) -> str:
    labels = {1: "元概念", 2: "核心理论", 3: "应用实践", 4: "实现工具"}
    return labels.get(level, "应用实践")


def extract_keywords(text: str) -> List[str]:
    """提取关键词（中文 2~5 字词 + 英文缩写/术语）"""
    # 中文词：连续 2-6 个汉字片段取前 6
    cn_words = re.findall(r'[\u4e00-\u9fff]{2,6}', text)
    # 英文：全大写缩写（CNN/NLP/BERT）+ 驼峰/普通词
    en_words = re.findall(r'[A-Z]{2,8}|[A-Z][a-z]{2,}(?:\s+[A-Z][a-z]+)*|[a-z]+(?:_[a-z]+)+', text)
    words = list(dict.fromkeys(cn_words[:6] + [w for w in en_words if len(w) >= 2]))
    return words[:12]


def classify_domain(text: str, heading: str = "") -> str:
    """领域分类"""
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
    """估算置信度"""
    base = 0.7
    if sent_type == "knowledge":
        base = 0.8
    elif sent_type == "question":
        base = 0.4
    elif sent_type == "thought":
        base = 0.5

    # 长度加成
    if len(text) > 50:
        base += 0.1
    if len(text) > 100:
        base += 0.05

    # 关键词加成
    if extract_keywords(text):
        base += 0.05

    return min(1.0, base)