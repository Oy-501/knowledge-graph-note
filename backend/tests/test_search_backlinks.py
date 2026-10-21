"""检索与反向链接：把「搜不到 / 找不到谁写过」这两类静默失效钉住。

这一组用例针对的都是「接口返回 200、看起来正常、但结果不对」的问题：
  - 笔记搜索只覆盖正文前 200 字（列表接口的截断被当成了全文）
  - 知识库只搜实体，别名与定义不参与
  - 知识点没有回程：「这个概念我在哪篇笔记里写过」答不出来
"""
import pytest


def _node(db, fid, title, entity=None, level=3, domain="database"):
    from app.models.models import Node

    n = Node(user_id=1, file_id=fid, entity=entity or title, title=title,
             level=level, domain=domain, description=f"{title} 的说明",
             keywords=[title], entities=[], upload_time=1700000000)
    db.add(n)
    db.commit()
    db.refresh(n)
    return n


def _user(db, uid, username):
    """notes.user_id 有外键；造 user#2 之前必须先有这条用户记录。"""
    from app.models.models import User

    if not db.query(User).filter_by(id=uid).first():
        db.add(User(id=uid, username=username))
        db.commit()


def _note(db, title, content, tags=None, user_id=1):
    from app.models.models import Note

    n = Note(user_id=user_id, title=title, content=content, tags=tags or [])
    db.add(n)
    db.commit()
    db.refresh(n)
    return n


def _kb(db, entity, aliases=None, definition=""):
    from app.models.models import KnowledgeBase

    k = KnowledgeBase(entity=entity, aliases=aliases or [], definition=definition,
                      domain="database", level=2)
    db.add(k)
    db.commit()
    db.refresh(k)
    return k


# ---------------------------------------------------------------- 笔记全文检索

def test_search_finds_content_beyond_the_first_200_chars(client, db):
    """正文第 300 字之后的内容也必须能搜到。

    列表接口为了轻量只回 `content[:200]`，前端就在那 200 字上做 includes ——
    这个截断被当成了全文搜索，于是「明明写过却搜不到」。
    """
    filler = "无关内容" * 60                      # 240 字，把关键词顶到 200 之后
    _note(db, "长笔记", filler + "这里提到向量数据库", tags=["检索"])

    # 先确认旧路径确实看不见（否则这条用例证明不了什么）
    listed = client.get("/api/notes", params={"user_id": 1}).json()["notes"]
    assert "向量数据库" not in listed[0]["content"], "列表接口居然回了全文，用例前提不成立"

    r = client.get("/api/notes/search", params={"q": "向量数据库", "user_id": 1})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["total"] == 1, data
    hit = data["notes"][0]
    assert "向量数据库" in hit["snippet"], f"片段里没有命中处：{hit['snippet']}"
    # 片段要有上下文，不能只回关键词本身
    assert len(hit["snippet"]) > len("向量数据库")


def test_search_matches_title_and_tags_too(client, db):
    _note(db, "复盘：索引优化", "正文和关键词无关", tags=["性能"])
    assert client.get("/api/notes/search", params={"q": "索引优化"}).json()["total"] == 1
    assert client.get("/api/notes/search", params={"q": "性能"}).json()["total"] == 1


def test_search_is_scoped_to_the_user(client, db):
    _user(db, 2, "another")
    _note(db, "别人的笔记", "这里也有向量数据库", user_id=2)
    assert client.get("/api/notes/search", params={"q": "向量数据库", "user_id": 1}).json()["total"] == 0


def test_empty_keyword_returns_nothing(client, db):
    """空关键词不能走 ILIKE '%%' —— 那等于把整库倒出来。"""
    _note(db, "甲", "内容一")
    _note(db, "乙", "内容二")
    data = client.get("/api/notes/search", params={"q": "   "}).json()
    assert data["total"] == 0 and data["notes"] == []


def test_wildcards_are_treated_as_text(client, db):
    """`%` 与 `_` 是 LIKE 通配符，必须按字面量处理。"""
    _note(db, "普通笔记", "没有任何通配符的内容")
    assert client.get("/api/notes/search", params={"q": "%"}).json()["total"] == 0
    _note(db, "百分比笔记", "命中率 95% 的案例")
    assert client.get("/api/notes/search", params={"q": "95%"}).json()["total"] == 1


def test_list_notes_reports_total_and_pages(client, db):
    for i in range(5):
        _note(db, f"笔记{i}", f"内容{i}")
    data = client.get("/api/notes", params={"user_id": 1, "limit": 2, "offset": 0}).json()
    assert data["total"] == 5, data
    assert data["count"] == 2


# ---------------------------------------------------------------- 知识库检索

def test_search_matches_alias_and_says_why(client, db):
    """搜别名要能命中，并标出「是按别名命中的」。

    实体叫「索引」、别名是「数据库索引」时，搜后者的旧行为是零结果。
    """
    # 名字刻意不撞种子知识库（那里本来就有「数据库索引」这条）
    _kb(db, "检索测试实体", aliases=["检索测试别名"], definition="用于验证别名匹配")
    r = client.get("/api/knowledge/search", params={"keyword": "检索测试别名"})
    assert r.status_code == 200, r.text
    rows = r.json()["knowledge_base"]
    hit = next((x for x in rows if x["entity"] == "检索测试实体"), None)
    assert hit, f"别名没有参与匹配，结果={rows}"
    assert hit["matched_by"] == "alias", hit


def test_search_matches_definition(client, db):
    _kb(db, "B+ 树", definition="一种适合范围查询的平衡树")
    rows = client.get("/api/knowledge/search", params={"keyword": "范围查询"}).json()["knowledge_base"]
    assert rows and rows[0]["matched_by"] == "definition", rows


def test_unified_search_includes_notes(client, db):
    _note(db, "速记", "今天聊到了知识图谱的稀疏连接")
    data = client.get("/api/knowledge/search", params={"keyword": "稀疏连接"}).json()
    assert data["notes"], data
    assert data["total"] >= 1


def test_unified_search_empty_keyword_is_empty(client, db):
    _kb(db, "任意实体", definition="任意定义")
    data = client.get("/api/knowledge/search", params={"keyword": ""}).json()
    assert data["total"] == 0 and data["knowledge_base"] == []


# ---------------------------------------------------------------- 反向链接

def test_node_references_split_linked_and_mentioned(client, db, make_file):
    """显式关联与「正文提到但没连」必须分开列。

    后者是补齐关联最快的地方：知识已经在笔记里了，只是没连上。
    """
    from app.models.models import NoteNode

    fid = make_file("t.md", nodes=0)
    node = _node(db, fid, "倒排索引")

    linked = _note(db, "索引笔记", "倒排索引 的核心是词典与倒排表")
    mentioned = _note(db, "随手记", "今天读到倒排索引，还没细看")
    unrelated = _note(db, "无关", "完全无关的内容")

    db.add(NoteNode(note_id=linked.id, node_id=node.id))
    db.commit()

    r = client.get(f"/api/knowledge/node/{node.id}/notes", params={"user_id": 1})
    assert r.status_code == 200, r.text
    data = r.json()
    assert [n["id"] for n in data["linked"]] == [linked.id]
    assert [n["id"] for n in data["mentioned"]] == [mentioned.id], data
    assert unrelated.id not in [n["id"] for n in data["mentioned"]]
    assert data["node_title"] == "倒排索引"


def test_node_references_404_for_missing_node(client):
    r = client.get("/api/knowledge/node/999999/notes")
    assert r.status_code == 404, r.text
    assert r.json()["error"]["code"] == "node_not_found"


def test_single_char_title_does_not_match_every_note(client, db, make_file):
    """单字标题会命中几乎所有笔记，等于没有筛选 —— 应当直接不参与匹配。"""
    fid = make_file("t.md", nodes=0)
    node = _node(db, fid, "图", entity="图")
    _note(db, "甲", "这里有个图字")
    _note(db, "乙", "这里也有图")

    data = client.get(f"/api/knowledge/node/{node.id}/notes").json()
    assert data["mentioned"] == [], data["mentioned"]


def test_node_references_scoped_to_user(client, db, make_file):
    _user(db, 2, "another")
    fid = make_file("t.md", nodes=0)
    node = _node(db, fid, "向量检索")
    _note(db, "别人的", "向量检索 很有意思", user_id=2)
    assert client.get(f"/api/knowledge/node/{node.id}/notes",
                      params={"user_id": 1}).json()["mentioned"] == []
