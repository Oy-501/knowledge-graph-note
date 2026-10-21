"""基于真实数据库的判定用例

语料从正式库 `backend/kg.db` 只读导出（`tests/data/verdict_real_corpus.json`），
但**测试仍在独立的测试库里跑** —— 导出的只是输入文本与当时的判定记录，
不连正式库，不会把测试数据写进用户的库。

与 `test_verdict_model.py` 的分工：
  - 那边用**构造的分数**验证决策函数的数学性质；
  - 这边用**真实的文本**验证实现是否真的遵守模型、证据是否真的可加、
    以及生产库里的历史记录是否与模型自洽。

「生产库历史记录自洽」那条不跑算法，只看记录本身，
因此不受测试库与生产库内容差异的影响。
"""
import json
import pathlib
import types

import pytest

from app.services import knowledge_verifier as kv

HERE = pathlib.Path(__file__).parent
DATA = json.loads((HERE / "data" / "verdict_real_corpus.json").read_text(encoding="utf-8"))
MODEL = json.loads((HERE / "data" / "verdict_model.json").read_text(encoding="utf-8"))

ACCEPT_AT = MODEL["thresholds"]["auto_accept"]
REJECT_BELOW = MODEL["thresholds"]["reject_below"]

REAL_CANDIDATES = DATA["真实候选"]
KB_SAMPLES = DATA["真实知识库样本"]
# 真实语料全集：11 条真实候选 + 30 条真实知识点，性质检验跑在全部 41 条上
ALL_CORPUS = REAL_CANDIDATES + KB_SAMPLES


def _as_candidate(row):
    """把真实语料行变成 verify_candidate 需要的候选对象"""
    return types.SimpleNamespace(
        entity=row["entity"], title=row["entity"],
        description=row.get("description") or row.get("definition") or "",
        keywords=row.get("keywords") or row.get("related_terms") or [],
        domain=row.get("domain") or "general",
        node_id=None)


def _model_decision(score, conflict):
    """决策函数：独立于实现重算一遍（模型不是从代码里抄的，是上一轮抽出来的）"""
    if score >= ACCEPT_AT and not conflict:
        return "accept"
    if score < REJECT_BELOW:
        return "reject"
    return "pending"


def _ids(row):
    if "id" in row:
        return f"{row['id']}-{row['entity']}"
    return f"kb-{row['entity']}"


# ------------------------------------------------ 真实候选：实现是否遵守模型


@pytest.mark.parametrize("row", ALL_CORPUS, ids=_ids)
def test_real_candidate_follows_model(db, row):
    """真实候选的输出必须严格等于模型公式

    用输出自己的 score 与 conflict 反算一遍：证据采集得对不对另说，
    但最终分级**必须**是这两条式子算出来的结果。
    """
    out = kv.verify_candidate(db, _as_candidate(row))
    assert out["decision"] == _model_decision(out["score"], out["conflict"])


@pytest.mark.parametrize("row", ALL_CORPUS, ids=_ids)
def test_evidence_is_additive(db, row):
    """可加性假设：四路证据权重之和（经 clamp）必须等于 score

    这是模型 A1 假设的直接检验 —— 若实现里存在交互项或条件折扣，
    这个等式会不成立，而「加权求和」这个建模方式就不成立。
    """
    out = kv.verify_candidate(db, _as_candidate(row))
    total = sum(e["weight"] for e in out["evidence"]
                if e["type"] in ("rule", "kb", "graph", "web"))
    assert min(1.0, max(0.0, total)) == pytest.approx(out["score"], abs=2e-3)


@pytest.mark.parametrize("row", ALL_CORPUS, ids=_ids)
def test_output_is_bounded_and_enumerated(db, row):
    """有界性与分级完备性：分数落在 [0,1]，决策落在三个合法值里"""
    out = kv.verify_candidate(db, _as_candidate(row))
    assert 0.0 <= out["score"] <= 1.0
    assert out["decision"] in ("accept", "reject", "pending")


def test_same_real_input_is_deterministic(db):
    """同一条真实输入连跑两次必须一致

    判定里混进了时间、字典序或缓存状态的话，这条会先炸。
    """
    row = REAL_CANDIDATES[0]
    a = kv.verify_candidate(db, _as_candidate(row))
    b = kv.verify_candidate(db, _as_candidate(row))
    assert a["score"] == b["score"]
    assert a["decision"] == b["decision"]
    assert a["evidence"] == b["evidence"]


# ------------------------------------------------ 真实文本上的具体行为


def test_predicate_fragment_is_penalized(db):
    """真实数据里的「注入」是谓语片段，规则路必须给出负权重

    这不是我编的例子 —— 它就是生产库里那条被判为 reject 的真实候选。
    """
    row = next(r for r in REAL_CANDIDATES if r["entity"] == "注入")
    out = kv.verify_candidate(db, _as_candidate(row))
    negatives = [e for e in out["evidence"]
                 if e["type"] == "rule" and not e["positive"]]
    assert negatives, "谓语片段没有被规则路识别出来"


def test_kb_evidence_is_reachable_on_real_terms(db):
    """真实知识点上，知识库那一路必须真的取得到证据

    30 条真实术语一条都命中不了，说明那一路在真实输入上是死的。
    """
    hits = 0
    for row in KB_SAMPLES:
        out = kv.verify_candidate(db, _as_candidate(row))
        if any(e["type"] == "kb" and e["positive"] and e["weight"] > 0
               for e in out["evidence"]):
            hits += 1
    assert hits >= 1, "真实知识点一条都没命中知识库，kb 路可能没接上"


# ------------------------------------------------ 生产库历史记录的自洽性


@pytest.mark.parametrize("row", REAL_CANDIDATES, ids=_ids)
def test_production_record_is_consistent(row):
    """生产库里每条历史 (score, decision) 必须满足模型的必要条件

    不跑算法，只看记录本身，因此不受测试库与生产库内容差异影响：
      score < 0.35         → 只能是 reject
      0.35 ≤ score < 0.80  → 只能是 pending
      score ≥ 0.80         → accept，或 pending（后者意味着当时置起了冲突）
    """
    rec = row["生产库判定"]
    if rec["score"] is None:
        pytest.skip("该条在生产库未判定过")
    s = min(1.0, max(0.0, rec["score"]))
    if s < REJECT_BELOW:
        assert rec["decision"] == "reject", f"{row['entity']} 分数 {s} 应驳回"
    elif s < ACCEPT_AT:
        assert rec["decision"] == "pending", f"{row['entity']} 分数 {s} 应待审"
    else:
        assert rec["decision"] in ("accept", "pending"), \
            f"{row['entity']} 分数 {s} 只可能是采纳或因冲突退回待审"


def test_real_corpus_has_duplicate_entities():
    """真实库里确实存在同一实体被多次抽出 —— 这正是 merged 要解决的问题

    若真实数据里从不出现重复，那 merged 分支就是为假想问题写的代码。
    """
    dups = DATA["生产库分布"].get("重复实体组") or []
    assert dups, "真实数据里没有重复实体，需要重新评估 merged 的必要性"


def test_exported_distribution_is_sane():
    """导出的分布统计自身要自洽（防止导出脚本写坏数据）"""
    d = DATA["生产库分布"]
    assert d["候选总数"] == len(REAL_CANDIDATES)
    assert 0 <= d["有分数的"] <= d["候选总数"]
    assert d["待审占比"] + d["驳回占比"] <= 1.0 + 1e-6
