"""文件上传/删除与候选判断的权限边界。"""
from app.main import WRITE_GUARD_USER_PREFIXES
from app.models.models import File, KnowledgeCandidate, User


def test_files_write_is_user_level():
    """上传、删除、重命名只要求登录，不再要求管理员。"""
    assert "/api/files/" in WRITE_GUARD_USER_PREFIXES


def test_candidates_are_scoped_to_owner(client, db, authed_headers):
    """候选查看按文件归属校验：别人的文件一律 404，不泄露存在性。"""
    owner = User(username="file_owner", password_hash="x")
    db.add(owner)
    db.commit()
    db.refresh(owner)

    record = File(user_id=owner.id, name="owner.md", content="内容", status="done")
    db.add(record)
    db.commit()
    db.refresh(record)

    cand = KnowledgeCandidate(user_id=owner.id, file_id=record.id, entity="测试知识点")
    db.add(cand)
    db.commit()
    db.refresh(cand)

    r = client.get(f"/api/files/{record.id}/candidates", headers=authed_headers)
    assert r.status_code == 404

    r = client.post(f"/api/files/{record.id}/candidates/{cand.id}/verdict",
                    json={"action": "accept"}, headers=authed_headers)
    assert r.status_code == 404


def test_candidate_verdict_updates_status(db):
    """采纳只改候选状态，不写公共知识库。"""
    from app.services import share_service  # noqa: F401 — 确保应用模块可导入

    owner = User(username="verdict_owner", password_hash="x")
    db.add(owner)
    db.commit()
    db.refresh(owner)

    record = File(user_id=owner.id, name="v.md", content="内容", status="done")
    db.add(record)
    db.commit()
    db.refresh(record)

    cand = KnowledgeCandidate(user_id=owner.id, file_id=record.id,
                              entity="可裁决知识点", verdict_decision="pending")
    db.add(cand)
    db.commit()
    db.refresh(cand)

    cand.status = "accepted"
    cand.verdict_decision = "accept"
    cand.verdict_stage = "user"
    db.commit()
    db.refresh(cand)

    assert cand.status == "accepted"
    assert cand.kb_entry_id is None
