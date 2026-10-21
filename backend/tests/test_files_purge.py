"""删除文件时的外键清理

这是本项目踩过的一个真实坑，而且报错点极具误导性：

    数据库开了 `PRAGMA foreign_keys=ON`。删文件时如果漏清任何一张
    引用 `files.id` 的子表，就会抛 `FOREIGN KEY constraint failed` ——
    **报错点在 `DELETE FROM files`，看不出是哪张子表没清**。
    上一轮就漏了「知识画像」和「文件知识关联」两张表。

代码里那句注释（`files.py` 的 `_purge_file_nodes`）已经写明
「新增此类表时必须同步补一行」。这里把这个约定固化成可执行的检查：
**造齐所有子表的行，删一次文件，断言全清干净且不报外键错。**

这样以后有人新加一张引用 files 的表却忘了补清理，删文件会失败，
或者残留行会被下面的断言抓到。
"""
import pytest
from sqlalchemy import text

from app.models.models import (
    File, FileKnowledgeLink, FileKnowledgeProfile, KnowledgeCandidate,
    Link, Node, NodeSource,
)


@pytest.fixture()
def file_with_children(db):
    """造一个「什么子表都有行」的文件，用来把清理逻辑压到边界。"""
    def _make(name="_TEST_被删文件.md"):
        f = File(user_id=1, name=name, content="内容", status="parsed")
        db.add(f)
        db.commit()
        db.refresh(f)

        n1 = Node(file_id=f.id, user_id=1, entity=f"{name}-节点1", upload_time=0)
        n2 = Node(file_id=f.id, user_id=1, entity=f"{name}-节点2", upload_time=0)
        db.add_all([n1, n2])
        db.commit()
        db.refresh(n1)
        db.refresh(n2)

        db.add_all([
            NodeSource(node_id=n1.id, source_type="text", paragraph="段"),
            KnowledgeCandidate(user_id=1, file_id=f.id, node_id=n1.id,
                               entity=f"{name}-候选"),
            FileKnowledgeProfile(user_id=1, file_id=f.id),
            Link(source_id=n1.id, target_id=n2.id, relation_type="related",
                 score=0.5, final_weight=0.5),
        ])
        # 文件间关联：自己连自己也算一条，确保两个方向都被清
        db.add(FileKnowledgeLink(user_id=1, source_file_id=f.id, target_file_id=f.id))
        db.commit()

        return {
            "file_id": f.id, "node_ids": [n1.id, n2.id],
        }
    return _make


def _counts(db, file_id, node_ids):
    rows = {
        "nodes": db.execute(text("select count(*) from nodes where file_id=:f"),
                            {"f": file_id}).scalar(),
        "knowledge_candidates": db.execute(
            text("select count(*) from knowledge_candidates where file_id=:f"),
            {"f": file_id}).scalar(),
        "file_knowledge_profiles": db.execute(
            text("select count(*) from file_knowledge_profiles where file_id=:f"),
            {"f": file_id}).scalar(),
        "file_knowledge_links": db.execute(
            text("select count(*) from file_knowledge_links "
                 "where source_file_id=:f or target_file_id=:f"),
            {"f": file_id}).scalar(),
    }
    if node_ids:
        marks = ",".join(str(i) for i in node_ids)
        rows["node_sources"] = db.execute(
            text(f"select count(*) from node_sources where node_id in ({marks})")).scalar()
        rows["links"] = db.execute(
            text(f"select count(*) from links where source_id in ({marks}) "
                 f"or target_id in ({marks})")).scalar()
    return rows


def test_children_exist_before_delete(db, file_with_children):
    """先确认样本是有效的 —— 否则下面的「全清干净」可能只是本来就没有。"""
    ctx = file_with_children()
    counts = _counts(db, ctx["file_id"], ctx["node_ids"])
    for table, n in counts.items():
        assert n > 0, f"样本无效：{table} 没有行，这条用例会假通过（{counts}）"


def test_delete_file_purges_every_child_table(client, db, admin_headers, file_with_children):
    """核心用例：删文件必须把所有子表清干净，且不能报外键错。"""
    ctx = file_with_children()

    r = client.delete(f"/api/files/{ctx['file_id']}", headers=admin_headers)
    assert r.status_code == 200, (
        f"删除失败（很可能是漏清某张引用 files.id 的子表，导致 "
        f"FOREIGN KEY constraint failed —— 报错点在 DELETE FROM files，"
        f"看不出是哪张表）：{r.status_code} {r.text[:300]}"
    )

    db.expire_all()
    counts = _counts(db, ctx["file_id"], ctx["node_ids"])
    leftovers = {k: v for k, v in counts.items() if v}
    assert not leftovers, f"删除后仍有残留：{leftovers}"

    assert db.query(File).filter_by(id=ctx["file_id"]).first() is None


def test_delete_nonexistent_file_is_not_500(client, admin_headers):
    """删不存在的文件不能崩。返回 404 或幂等 200 都可以，但不能是 5xx。"""
    r = client.delete("/api/files/99999999", headers=admin_headers)
    assert r.status_code < 500, f"删除不存在的文件返回 {r.status_code}: {r.text[:200]}"
    assert r.status_code in (200, 404), f"未预期的状态码 {r.status_code}"


def test_delete_twice_is_safe(client, db, admin_headers, file_with_children):
    """重复删除（重试场景）不能报外键错。"""
    ctx = file_with_children()
    first = client.delete(f"/api/files/{ctx['file_id']}", headers=admin_headers)
    assert first.status_code == 200
    second = client.delete(f"/api/files/{ctx['file_id']}", headers=admin_headers)
    assert second.status_code < 500, f"重复删除返回 {second.status_code}: {second.text[:200]}"


def test_no_orphan_nodes_after_delete(client, db, admin_headers, file_with_children):
    """全局不变式：库里不应存在指向已删文件的节点。"""
    ctx = file_with_children()
    client.delete(f"/api/files/{ctx['file_id']}", headers=admin_headers)
    db.expire_all()
    orphans = db.execute(text(
        "select count(*) from nodes where file_id not in (select id from files)"
    )).scalar()
    assert orphans == 0, f"存在 {orphans} 个悬空节点"


def test_no_dangling_links_after_delete(client, db, admin_headers, file_with_children):
    """全局不变式：连线两端都必须还能找到对应节点。"""
    ctx = file_with_children()
    client.delete(f"/api/files/{ctx['file_id']}", headers=admin_headers)
    db.expire_all()
    dangling = db.execute(text(
        "select count(*) from links where source_id not in (select id from nodes) "
        "or target_id not in (select id from nodes)"
    )).scalar()
    assert dangling == 0, f"存在 {dangling} 条悬空连线"
