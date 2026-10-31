"""四路证据加权判定的模型化测试（数据驱动）

先把算法抽成模型：
    score    = clamp(Σw, 0, 1)
    decision = accept  当 score ≥ auto_accept 且无冲突
               reject  当 score < reject_below
               pending 其余

于是可验证的不再只是「某条候选判成了什么」，而是几条**数学性质**：
有界（clamp 生效）、单调（加正证据不减分）、冲突否决（再高分也不自动入库）、
边界（0.80 / 0.35 两侧）、以及联网不可用必须是中性 0 权重。

用例数据全部来自 `tests/data/verdict_model.json`，代码里不硬编码。
改阈值或权重时，前两条守卫用例会提醒你同步数据文件。
"""
import json
import pathlib
import re
import types

import pytest

from app.config import settings
from app.services import knowledge_verifier as kv

DATA = json.loads(
    (pathlib.Path(__file__).parent / "data" / "verdict_model.json")
    .read_text(encoding="utf-8"))


def _build(score, conflict=False):
    """按目标分数构造一个 Verdict 并取结果（跳过四路证据的实际采集）"""
    v = kv.Verdict("构造用例")
    if score:
        v.add("rule", score, "用于验证决策函数的构造分")
    v.conflict = conflict
    return v.to_dict()


# ---------------------------------------------------------------- 边界


@pytest.mark.parametrize("case", DATA["boundary_cases"], ids=lambda c: c["name"])
def test_decision_boundaries(case):
    """阈值两侧的分级必须落在正确一侧"""
    out = _build(case["score"], case.get("conflict", False))
    assert out["score"] == pytest.approx(case["score"])
    assert out["decision"] == case["expect"]


# ---------------------------------------------------------------- 有界


@pytest.mark.parametrize("case", DATA["clamp_cases"], ids=lambda c: c["name"])
def test_score_is_clamped(case):
    """累加越界时分数必须被夹住，而不是直接溢出到 1.2 或 -0.9"""
    v = kv.Verdict("构造用例")
    for w in case["weights"]:
        v.add("rule", w, "构造")
    out = v.to_dict()
    assert out["score"] == pytest.approx(case["expect_score"])
    assert out["decision"] == case["expect"]


# ---------------------------------------------------------------- 单调


def test_positive_evidence_is_monotonic():
    """继续加正面证据，分数不能反而下降"""
    v = kv.Verdict("构造用例")
    prev = 0.0
    for w in DATA["monotonic_weights"]:
        v.add("rule", w, "构造")
        now = v.to_dict()["score"]
        assert now >= prev - 1e-9, f"加了 +{w} 之后分数从 {prev} 掉到 {now}"
        prev = now


# ---------------------------------------------------------------- 冲突否决


@pytest.mark.parametrize("case", DATA["conflict_cases"], ids=lambda c: c["name"])
def test_conflict_blocks_auto_accept(case):
    """冲突位置起后自动入库必须被挡住，但仍按分数分级"""
    out = _build(case["score"], conflict=True)
    assert out["decision"] == case["expect"]
    assert out["conflict"] is True
    if case["score"] >= DATA["thresholds"]["auto_accept"]:
        assert out["decision"] != "accept"


# ---------------------------------------------------------------- 守卫：数据与代码不漂移


def test_thresholds_match_config():
    """数据文件里的阈值必须与生效配置一致，否则用例测的是另一套模型"""
    assert settings.VERDICT_AUTO_ACCEPT == pytest.approx(DATA["thresholds"]["auto_accept"])
    assert settings.VERDICT_REJECT_BELOW == pytest.approx(DATA["thresholds"]["reject_below"])


def test_weight_table_in_sync():
    """源码里每条证据的权重都要在数据文件里有一行，反向也一样

    这条是防漂移的：有人在代码里调了某个权重却没同步数据文件，
    模型文档就会开始说谎，而其余用例不会红 —— 只有这条会。
    """
    src = pathlib.Path(kv.__file__).read_text(encoding="utf-8")
    in_code = {float(m) for m in re.findall(
        r'\.add\(\s*"(?:rule|kb|graph|web)"\s*,\s*(-?[0-9.]+)', src)}
    in_data = {float(e["weight"]) for e in DATA["evidence"]}

    missing = in_code - in_data      # 代码里有、数据没记
    stale = in_data - in_code        # 数据记着、代码已删
    assert not missing, f"这些权重在代码里缺失数据记录：{sorted(missing)}"
    assert not stale, f"这些权重代码里已不存在，数据文件过时了：{sorted(stale)}"


# ---------------------------------------------------------------- 性质：联网中性


def test_web_unavailable_is_neutral(db, monkeypatch):
    """联网抓不到时必须是 0 权重且记为正面，不能当成负面证据

    这条性质来自一次真实误判：领域内的正当专有名词（如「Memory 记忆模块」）
    本来就搜不到，早先当成负面证据把它们全驳回了。
    """
    from app.services import web_probe

    monkeypatch.setattr(web_probe, "search_multi",
                        lambda *a, **kw: {"online": False, "provider": "",
                                          "results": [], "error": "测试：不可达"})

    cand = types.SimpleNamespace(
        entity="自造概念Xyz", title="自造概念Xyz",
        description="这是一种用于测试的概念", keywords=["测试"],
        domain="general", node_id=None)

    out = kv.verify_candidate(db, cand, use_web=True, web_budget={"left": 5})
    web_ev = [e for e in out["evidence"] if e["type"] == "web"]

    assert web_ev, "联网不可用也应当留下一条记录，说明当时是按本地证据判的"
    for e in web_ev:
        assert e["weight"] == pytest.approx(DATA["web_neutral"]["weight"])
        assert e["positive"] is DATA["web_neutral"]["positive"]
    assert out["web_status"] == "unavailable"
