"""检索服务：命中判定 + 上下文片段 + 反向引用。

三个入口共用同一套规则：
  GET /api/knowledge/search              全局检索（知识库 / 节点 / 笔记）
  GET /api/notes/search                  笔记全文检索（带分页）
  GET /api/knowledge/node/{id}/notes     反向链接（谁写过这个知识点）

为什么单独成一层：这三处必须口径一致 —— 别名要参与匹配、命中处要给上下文
而不是「正文前 N 字」、未显式关联的提及要能单独列出来。
写在路由里必然各写一份，然后慢慢走偏。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import String, cast, or_
from sqlalchemy.orm import Session

from app.models.models import KnowledgeBase, Node, Note, NoteNode
from app.services.errors import clamp_paging, escape_like

# 片段两侧各留多少字。34 个字在中文里约等于一行的两倍，
# 够看出「这句在讲什么」，又不至于把整段搬进列表。
SNIPPET_WIDTH = 34


def like_pattern(keyword: str) -> str:
    """把用户输入变成 LIKE 模式；通配符按字面量处理。

    不转义的话，搜一个 `%` 会命中全表（等于把库倒出来），
    `_` 也会把匹配范围悄悄放大。
    """
    return f"%{escape_like(keyword)}%"


def json_patterns(keyword: str) -> List[str]:
    """JSON 数组列要同时匹配「字面中文」和「\\uXXXX 转义」两种形态。

    SQLAlchemy 的 JSON 序列化默认 `ensure_ascii=True`，于是中文在 SQLite 里
    实际存成 `["\\u6027\\u80fd"]` —— 直接 `ILIKE '%性能%'` 永远命中不了；
    而 PostgreSQL 的 JSONB 转 text 又是真中文。
    只匹配一种形态，总有一个数据库上「搜别名永远搜不到」，且没有任何报错。
    """
    patterns = [like_pattern(keyword)]
    escaped = keyword.encode("unicode_escape").decode("ascii")
    if escaped != keyword:
        patterns.append(like_pattern(escaped))
    return patterns


def snippet(text: Optional[str], needle: str, width: int = SNIPPET_WIDTH) -> str:
    """取命中位置附近的上下文。

    笔记正文动辄几千字，只回「正文前 200 字」会让「搜到了但看不到命中处」
    成为常态 —— 用户会以为搜错了。这里按命中位置截取。
    """
    body = (text or "").replace("\r", "")
    if not body:
        return ""
    key = (needle or "").strip()
    pos = body.lower().find(key.lower()) if key else -1
    if pos < 0:
        head = body[: width * 2].replace("\n", " ").strip()
        return head + ("…" if len(body) > width * 2 else "")
    start = max(0, pos - width)
    end = min(len(body), pos + len(key) + width)
    piece = body[start:end].replace("\n", " ").strip()
    return ("…" if start > 0 else "") + piece + ("…" if end < len(body) else "")


def _matched_by(entry: KnowledgeBase, key: str) -> str:
    """这条知识库记录是被哪个字段命中的（实体 / 别名 / 定义）。

    前端要能说明「为什么它出现在结果里」：搜「数据库索引」而实体叫「索引」，
    不标注一下，用户会以为排序坏了。
    """
    low = key.lower()
    if low in (entry.entity or "").lower():
        return "entity"
    for alias in (entry.aliases or []):
        if low in str(alias).lower():
            return "alias"
    return "definition"


def search_knowledge_base(db: Session, key: str, limit: int = 10) -> List[Dict[str, Any]]:
    """知识库检索：实体 + 别名 + 定义。

    别名是 JSON 列，跨 SQLite/PostgreSQL 时用 `cast(... AS VARCHAR)` 做粗筛，
    再在 Python 侧判定命中来源 —— 只靠 cast 的子串匹配不知道命中的是哪个字段。
    """
    pat = like_pattern(key)
    alias_cond = or_(*[
        cast(KnowledgeBase.aliases, String).ilike(p, escape="\\")
        for p in json_patterns(key)
    ])
    rows = (
        db.query(KnowledgeBase)
        .filter(or_(
            KnowledgeBase.entity.ilike(pat, escape="\\"),
            KnowledgeBase.definition.ilike(pat, escape="\\"),
            alias_cond,
        ))
        # 下架/取消分享的条目不进检索结果（条目保留在库里，只是不再对外）
        .filter(KnowledgeBase.is_published.isnot(False))
        .limit(limit)
        .all()
    )
    return [
        {
            "id": r.id,
            "entity": r.entity,
            "domain": r.domain,
            "level": r.level,
            "definition": r.definition,
            "aliases": r.aliases or [],
            "matched_by": _matched_by(r, key),
        }
        for r in rows
    ]


def search_nodes(db: Session, key: str, limit: int = 10) -> List[Dict[str, Any]]:
    """图谱节点检索：实体 + 标题。

    旧版只查 entity，而节点展示用的是 title —— 标题和实体不一致的节点
    在搜索结果里永远找不到自己名字。
    """
    pat = like_pattern(key)
    rows = (
        db.query(Node)
        .filter(or_(
            Node.entity.ilike(pat, escape="\\"),
            Node.title.ilike(pat, escape="\\"),
        ))
        .filter(Node.status == "active")
        .limit(limit)
        .all()
    )
    return [
        {
            "id": n.id,
            "entity": n.entity,
            "title": n.title,
            "level": n.level,
            "domain": n.domain,
            "file_id": n.file_id,
        }
        for n in rows
    ]


def search_notes(
    db: Session, key: str, user_id: int = 1, limit: Any = 20, offset: Any = 0
) -> Tuple[List[Dict[str, Any]], int]:
    """笔记全文检索：标题 + 正文 + 标签。

    与列表接口的区别：列表只回 `content[:200]`（列表页要轻量），
    在那上面做搜索等于「只搜每篇笔记的前 200 字」。这里是真正的全文匹配，
    并返回命中处的片段。
    """
    limit, offset = clamp_paging(limit, offset, max_limit=100, default_limit=20)
    pat = like_pattern(key)
    tag_cond = or_(*[
        cast(Note.tags, String).ilike(p, escape="\\")
        for p in json_patterns(key)
    ])
    q = db.query(Note).filter(
        Note.user_id == user_id,
        or_(
            Note.title.ilike(pat, escape="\\"),
            Note.content.ilike(pat, escape="\\"),
            tag_cond,
        ),
    )
    total = q.count()
    rows = q.order_by(Note.updated_at.desc()).offset(offset).limit(limit).all()

    out = []
    for n in rows:
        out.append({
            "id": n.id,
            "title": n.title,
            "snippet": snippet(n.content, key) if key.lower() not in (n.title or "").lower()
                       else snippet(n.title, key),
            "tags": n.tags or [],
            "archived": bool(n.archived),
            "content_length": len(n.content or ""),
            "updated_at": n.updated_at.isoformat() if n.updated_at else None,
        })
    return out, total


def node_references(db: Session, node: Node, user_id: int = 1,
                    limit: int = 30) -> Dict[str, Any]:
    """反向引用：哪些笔记写过这个知识点。

    分两段，这个区分是重点：
      - linked    —— 显式关联（`[[标题]]` 或手动挂上），用户「说过要连」；
      - mentioned —— 正文里提到了标题，但没建立关联，用户「其实写过但没连」。
    第二段是补齐关联最快的地方：它把「已经存在于笔记里的知识」捞回来，
    而不是要求用户重新读一遍再手动连。
    """
    names = []
    for raw in (node.title, node.entity):
        name = (raw or "").strip()
        # 单字标题会命中几乎所有笔记，等于没有筛选
        if len(name) >= 2 and name not in names:
            names.append(name)

    linked_rows = (
        db.query(Note)
        .join(NoteNode, NoteNode.note_id == Note.id)
        .filter(NoteNode.node_id == node.id, Note.user_id == user_id)
        .order_by(Note.updated_at.desc())
        .limit(limit)
        .all()
    )
    linked_ids = {n.id for n in linked_rows}

    mentioned_rows: List[Note] = []
    if names:
        cond = or_(*[Note.content.ilike(like_pattern(n), escape="\\") for n in names])
        rows = (
            db.query(Note)
            .filter(Note.user_id == user_id, cond)
            .order_by(Note.updated_at.desc())
            .limit(limit)
            .all()
        )
        mentioned_rows = [n for n in rows if n.id not in linked_ids]

    def brief(n: Note) -> Dict[str, Any]:
        """给搜索结果节点生成一句命中摘要。"""
        hit = next((x for x in names if x.lower() in (n.content or "").lower()), "")
        return {
            "id": n.id,
            "title": n.title,
            "snippet": snippet(n.content, hit) if hit else snippet(n.content, ""),
            "tags": n.tags or [],
            "updated_at": n.updated_at.isoformat() if n.updated_at else None,
        }

    return {
        "node_id": node.id,
        "node_title": node.title or node.entity,
        "linked": [brief(n) for n in linked_rows],
        "mentioned": [brief(n) for n in mentioned_rows],
    }
