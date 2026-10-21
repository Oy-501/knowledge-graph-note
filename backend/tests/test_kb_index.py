"""知识库索引：缓存正确性 + 端点输出形状

这块出过两类问题，都很难从日志看出来：

  1. `load_index` 每次请求都重建（读全表 + 重建别名表/邻接表，约 60ms），
     24 并发下把它放大到 9.6s。修法是加进程级缓存。
  2. 缓存键曾经想用 `count(*) + max(id)` 这种**计数级**指纹 —— 它对
     「改了一条已有条目」不敏感，缓存会一直供旧数据。现在用**内容级**。

第 2 条是这里最该守的不变量：改一条已有条目的别名，缓存必须失效。
"""
import pytest

from app.models.models import KnowledgeBase
from app.services.kb_index import (
    KbIndex, _content_key, invalidate_index, load_index,
)

TEST_PREFIX = "_TEST_"


@pytest.fixture()
def kb_entry(db):
    """造一条测试条目，用完由 conftest 按前缀清掉。"""
    def _make(entity=f"{TEST_PREFIX}缓存探针", **kw):
        row = KnowledgeBase(
            entity=entity,
            aliases=kw.get("aliases", ["缓存别名"]),
            domain=kw.get("domain", "general"),
            level=kw.get("level", 3),
            definition=kw.get("definition", "用于测试定义"),
            related_terms=kw.get("related_terms", []),
            bridge_sentences=[], opposite_terms=[], source="manual",
            credibility=6,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return row
    return _make


# ---------------------------------------------------------------- 缓存

def test_load_index_hits_cache(db):
    """两次调用必须是同一个实例 —— 否则等于没缓存。"""
    invalidate_index()
    a = load_index(db)
    b = load_index(db)
    assert a is b, "未命中缓存：索引被重建了"


def test_invalidate_index_forces_rebuild(db):
    invalidate_index()
    a = load_index(db)
    invalidate_index()
    b = load_index(db)
    assert a is not b, "invalidate_index 之后应当重建"


def test_cache_invalidated_when_existing_entry_changes(db, kb_entry):
    """核心不变量：**改一条已有条目**（不新增、不删除）也要让缓存失效。

    计数级指纹（count + max(id)）在这里会失效不了，缓存会一直供旧数据，
    而且这种错极难发现 —— 所以单独立一条用例钉住它。
    """
    row = kb_entry()
    invalidate_index()
    load_index(db)                      # 让缓存建立

    key_before = _content_key(db)
    row.aliases = ["缓存别名", "新增别名"]
    db.commit()
    key_after = _content_key(db)

    assert key_before != key_after, "改别名后内容指纹没变，缓存会一直供旧数据"


def test_cache_invalidated_on_insert_and_delete(db, kb_entry):
    invalidate_index()
    k0 = _content_key(db)

    row = kb_entry(entity=f"{TEST_PREFIX}插入探针")
    k1 = _content_key(db)
    assert k1 != k0, "新增条目后指纹没变"

    db.delete(row)
    db.commit()
    assert _content_key(db) != k1, "删除条目后指纹没变"


def test_cache_content_matches_fresh_build(db):
    """缓存里的索引必须与「全新构建」的索引内容一致，否则缓存会改变行为。"""
    invalidate_index()
    cached = load_index(db)

    def row_of(e):
        return {
            "entity": e.entity, "aliases": e.aliases or [], "domain": e.domain,
            "level": e.level or 3, "definition": e.definition,
            "bridge_sentences": e.bridge_sentences or [],
            "related_terms": e.related_terms or [], "opposite_terms": e.opposite_terms or [],
            "source": e.source, "credibility": e.credibility,
        }

    from app.models.models import KbRelation

    fresh = KbIndex(
        [row_of(e) for e in db.query(KnowledgeBase).all()],
        [{"source_entity": r.source_entity, "target_entity": r.target_entity,
          "relation_type": r.relation_type, "relation_label": r.relation_label,
          "weight": r.weight, "evidence": r.evidence}
         for r in db.query(KbRelation).all()],
    )
    assert cached.stats() == fresh.stats()
    assert cached.alias_map == fresh.alias_map
    assert dict(cached.adj) == dict(fresh.adj)


def test_seed_index_is_populated(db):
    invalidate_index()
    index = load_index(db)
    assert len(index.entries) > 100, "种子知识库未进入索引"
    assert len(index.alias_map) > 100


# ---------------------------------------------------------------- 端点输出

def test_kb_graph_shape(client, admin_headers):
    r = client.get("/api/kb/graph?limit=50", headers=admin_headers)
    assert r.status_code == 200
    data = r.json()
    assert {"nodes", "links", "truncated", "total_entries"} <= set(data)

    for node in data["nodes"]:
        assert {"id", "entity", "domain", "level", "definition", "aliases",
                "source", "isolated", "credibility"} <= set(node)
        assert len(node["definition"]) <= 200, "definition 应在 SQL 侧就截断到 200 字"

    for link in data["links"]:
        assert {"source", "target", "relation_type", "relation_label",
                "weight", "evidence", "origin"} <= set(link)


def test_kb_graph_total_entries_matches_table(client, db, admin_headers):
    total = db.query(KnowledgeBase).count()
    r = client.get("/api/kb/graph?limit=10", headers=admin_headers)
    assert r.json()["total_entries"] == total


def test_kb_graph_links_only_reference_returned_nodes(client, admin_headers):
    """边过滤必须下推到 SQL 且口径一致：不能出现指向本页之外节点的边。"""
    r = client.get("/api/kb/graph?limit=30", headers=admin_headers)
    data = r.json()
    names = {n["id"] for n in data["nodes"]}
    for link in data["links"]:
        assert link["source"] in names, f"边指向页外节点：{link['source']}"
        assert link["target"] in names, f"边指向页外节点：{link['target']}"


def test_kb_stats_no_duplicate_source_count(db, client, admin_headers):
    """来源计数不能把别名归并掉的重复条目算两遍（曾出现「知识点 404 / 来源合计 406」）。"""
    r = client.get("/api/kb/stats", headers=admin_headers)
    assert r.status_code == 200
    data = r.json()
    kb_total = sum(v for k, v in data["sources"].items() if not k.startswith("relation:"))
    assert kb_total <= data["entries"], (
        f"来源合计 {kb_total} 超过了知识点数 {data['entries']}，说明重复计数"
    )


def test_list_entries_relation_count_is_grouped(db, client, admin_headers):
    """每实体的关系数应与直接聚合一致（验证 GROUP BY 下推没改口径）。"""
    from sqlalchemy import func

    from app.models.models import KbRelation

    expected = dict(
        db.query(KbRelation.source_entity, func.count())
          .group_by(KbRelation.source_entity).all()
    )
    r = client.get("/api/kb/entries?limit=20", headers=admin_headers)
    for item in r.json()["entries"]:
        assert item.get("relation_count", 0) == expected.get(item["entity"], 0), (
            f"{item['entity']} 的关系数与聚合结果不一致"
        )
