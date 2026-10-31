"""判定结论的自检守卫：矛盾结论必须在落库前被降级。"""
from app.services.knowledge_verifier import _guard_verdict


def _v(score, decision, **extra):
    return {"score": score, "decision": decision, "reason": "原始理由", "evidence": [], **extra}


def test_accept_below_threshold_is_downgraded():
    out = _guard_verdict(_v(0.2, "accept"))
    assert out["decision"] == "pending"
    assert "自检" in out["reason"]
    assert any(e["type"] == "guard" for e in out["evidence"])


def test_reject_above_threshold_is_downgraded():
    out = _guard_verdict(_v(0.9, "reject"))
    assert out["decision"] == "pending"


def test_conflict_blocks_accept():
    out = _guard_verdict(_v(0.95, "accept", conflict=True))
    assert out["decision"] == "pending"
    assert "冲突" in out["reason"]


def test_score_out_of_range_is_clamped():
    out = _guard_verdict(_v(1.7, "pending"))
    assert out["score"] == 1.0
    out2 = _guard_verdict(_v(-0.3, "pending"))
    assert out2["score"] == 0.0


def test_unknown_decision_becomes_pending():
    out = _guard_verdict(_v(0.9, "approved"))
    assert out["decision"] == "pending"


def test_consistent_verdict_passes_through():
    verdict = _v(0.93, "accept")
    assert _guard_verdict(verdict) is verdict
