"""批量判定与批量入库的针对性回归

盯的是三个「改了不易察觉、坏了很难查」的点：
  1. 重跑判定不能把人工裁决推翻（要覆盖必须显式 force）
  2. 批量入库不能每条都全量重建知识库关系
  3. 同一实体的跨片重复候选要归于 merged，而不是一直占着待审队列
"""
from app.models.models import KnowledgeCandidate


def _make(db, entity, **kw):
    """造一条候选。entity 一律带 _TEST_ 前缀，conftest 会自动清理"""
    row = KnowledgeCandidate(
        user_id=1, entity=entity, title=entity,
        description="这是一种用于回归测试的部件，属于测试领域",
        keywords=["测试"], domain="general", level=3,
        source_text="原文证据", line_start=1, line_end=2, status="open", **kw)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def test_rerun_does_not_override_human(client, admin_headers, db):
    """人工裁过的条目，非 force 的重跑必须跳过"""
    c = _make(db, "_TEST_人工裁决甲")

    r = client.post(f"/api/admin/candidates/{c.id}/review",
                    json={"action": "accept", "note": "人工认可", "reviewer": "tester"},
                    headers=admin_headers)
    assert r.status_code == 200, r.text
    # 裁决走的是另一个会话；本会话必须失效缓存才能读到它的写入
    db.expire_all()
    before = db.query(KnowledgeCandidate).filter_by(id=c.id).first()
    assert before.verdict_stage == "human"
    assert before.status == "accepted"

    # 默认：跳过。机器不许推翻人判过的
    r = client.post("/api/admin/candidates/verify",
                    json={"ids": [c.id], "auto_ingest": False}, headers=admin_headers)
    assert r.status_code == 200, r.text
    assert r.json()["stats"]["skipped_human"] == 1
    db.expire_all()
    after = db.query(KnowledgeCandidate).filter_by(id=c.id).first()
    assert (after.status, after.verdict_decision, after.verdict_stage) == \
           (before.status, before.verdict_decision, before.verdict_stage)

    # force=True 才允许重判
    r = client.post("/api/admin/candidates/verify",
                    json={"ids": [c.id], "force": True, "auto_ingest": False},
                    headers=admin_headers)
    assert r.status_code == 200, r.text
    assert r.json()["stats"]["skipped_human"] == 0


def test_bulk_ingest_rebuilds_relations_once(client, admin_headers, db, monkeypatch):
    """批量入库：关系重建一次即可，不能每条都来一遍"""
    from app.api import admin as admin_mod
    from app.services import kb_index

    calls = {"n": 0}
    # 补丁之前先留下原函数：counting 要真的把活干掉，只是顺便计数
    real = kb_index.build_relations_from_entries

    def counting(*a, **kw):
        calls["n"] += 1
        return real(*a, **kw)

    # 两处都要打：knowledge_verifier 是函数体内 `from ... import`，运行时才取
    # kb_index 的当前属性；admin 里是模块级绑定，必须单独换掉。
    # 只打一处的话，「defer 失效」这种回归是抓不到的。
    monkeypatch.setattr(kb_index, "build_relations_from_entries", counting)
    monkeypatch.setattr(admin_mod, "build_relations_from_entries", counting)

    rows = [_make(db, f"_TEST_批量概念{i}") for i in range(5)]
    r = client.post("/api/admin/candidates/bulk-review",
                    json={"ids": [x.id for x in rows], "action": "accept", "ingest": True},
                    headers=admin_headers)
    assert r.status_code == 200, r.text
    assert r.json()["count"] == 5
    assert calls["n"] == 1, f"关系重建被调用了 {calls['n']} 次，应该只有 1 次"


def test_twin_candidates_merged(client, admin_headers, db):
    """同一实体被多片抽出时，其余还开着的候选应归为 merged 并回填条目 id"""
    a = _make(db, "_TEST_重复概念")
    b = _make(db, "_TEST_重复概念")
    c = _make(db, "_TEST_重复概念")

    r = client.post("/api/admin/candidates/bulk-review",
                    json={"ids": [a.id], "action": "accept", "ingest": True},
                    headers=admin_headers)
    assert r.status_code == 200, r.text

    db.expire_all()
    for row in (b, c):
        fresh = db.query(KnowledgeCandidate).filter_by(id=row.id).first()
        assert fresh.status == "merged", f"候选 {row.id} 仍停在 {fresh.status}"
        assert fresh.kb_entry_id, "合并后应回填入库的知识库条目 id"
    assert db.query(KnowledgeCandidate).filter_by(id=a.id).first().status == "accepted"
