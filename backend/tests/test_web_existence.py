"""联网存在性确认：五级状态、精确匹配与保底规则。

两条不能退让的性质：
  1. 搜不到 / 联网不可用必须是中性，不能当成「不存在」；
  2. 只有多源精确命中才算确认，单站多页不算多源。
"""
import types

import pytest

from app.config import settings
from app.services import knowledge_verifier as kv
from app.services import web_existence as we


def _res(*items, online=True):
    return {
        "online": online,
        "provider": "test",
        "results": [
            {"title": t, "url": u, "snippet": s} for t, u, s in items
        ],
    }


def _cand(entity, desc="", keywords=None):
    return types.SimpleNamespace(
        entity=entity, title=entity, description=desc,
        keywords=keywords or [], domain="general", node_id=None)


# ---------------------------------------------------------------- 分级


def test_unavailable_is_neutral():
    out = we.check_existence("检索增强生成", "一种方法", {"online": False, "results": []})
    assert out["status"] == "unavailable"
    assert out["contradicted"] is False


def test_no_hit_is_unverified():
    out = we.check_existence("自造概念", "描述", _res(
        ("完全无关的标题", "https://a.com/x", "无关摘要")))
    assert out["status"] == "unverified"
    assert out["exact_hits"] == 0


def test_multi_domain_with_consistent_description_is_confirmed():
    desc = "检索增强生成是一种结合检索与生成的方法"
    out = we.check_existence("检索增强生成", desc, _res(
        ("检索增强生成是什么", "https://a.com/1", desc),
        ("检索增强生成详解", "https://b.com/2", "检索增强生成结合检索与生成"),
    ))
    assert out["status"] == "confirmed"
    assert len(out["domains"]) == 2


def test_same_domain_is_not_confirmed():
    desc = "检索增强生成是一种方法"
    out = we.check_existence("检索增强生成", desc, _res(
        ("检索增强生成A", "https://a.com/1", desc),
        ("检索增强生成B", "https://a.com/2", desc),
    ))
    assert out["status"] != "confirmed"


def test_empty_description_needs_three_domains():
    two = _res(
        ("检索增强生成", "https://a.com/1", ""),
        ("检索增强生成", "https://b.com/2", ""),
    )
    assert we.check_existence("检索增强生成", "", two)["status"] != "confirmed"

    three = _res(
        ("检索增强生成", "https://a.com/1", ""),
        ("检索增强生成", "https://b.com/2", ""),
        ("检索增强生成", "https://c.com/3", ""),
    )
    assert we.check_existence("检索增强生成", "", three)["status"] == "confirmed"


def test_english_word_boundary():
    """storage 里的 rag 不能当成 RAG 命中"""
    out = we.check_existence("RAG", "检索增强", _res(
        ("Storage layer", "https://a.com", "storage and indexing"),
        ("Storage design", "https://b.com", "storage layout"),
    ))
    assert out["status"] == "unverified"

    hit = we.check_existence("RAG", "检索增强", _res(
        ("RAG 入门", "https://a.com", "RAG 是检索增强生成"),
        ("RAG-based systems", "https://b.com", "RAG-based retrieval"),
    ))
    assert hit["status"] in ("confirmed", "probable")


def test_strong_negation_is_contradicted():
    out = we.check_existence("某伪概念", "描述", _res(
        ("某伪概念", "https://a.com", "某伪概念并不存在，属于谣言"),
    ))
    assert out["status"] == "contradicted"
    assert out["contradicted"] is True


def test_definition_sentence_is_not_contradiction():
    """「X 不是 A，而是 B」是定义句，不是否定 X 存在"""
    out = we.check_existence("某概念", "某概念是一种方法", _res(
        ("某概念", "https://a.com", "某概念不是单一算法，而是一类方法"),
        ("某概念详解", "https://b.com", "某概念是一种方法"),
    ))
    assert out["status"] != "contradicted"


# ---------------------------------------------------------------- 判定机集成


def test_confirmed_has_score_floor(db, monkeypatch):
    """本地规则给出负分的候选，只要联网多源确认存在，就不能被驳回"""
    from app.services import web_probe

    desc = "分为方法是一种用于测试的描述文本"
    monkeypatch.setattr(web_probe, "search_web", lambda *a, **kw: _res(
        ("分为方法是什么", "https://a.com/1", desc),
        ("分为方法详解", "https://b.com/2", desc),
    ))

    out = kv.verify_candidate(db, _cand("分为方法", desc), use_web=True,
                              web_budget={"left": 5})
    assert out["score"] >= settings.VERDICT_WEB_EXISTENCE_FLOOR - 1e-9
    assert out["decision"] != "reject"
    assert any(e["type"] == "web-existence" and "confirmed" in e["detail"]
               for e in out["evidence"])


def test_contradicted_cannot_accept(db, monkeypatch):
    from app.services import web_probe

    monkeypatch.setattr(web_probe, "search_web", lambda *a, **kw: _res(
        ("某概念", "https://a.com", "某概念并不存在，属于谣言"),
        ("某概念", "https://b.com", "某概念纯属虚构"),
    ))
    out = kv.verify_candidate(db, _cand("某概念", "某概念是一种方法"), use_web=True,
                              web_budget={"left": 5})
    assert out["conflict"] is True
    assert out["decision"] == "pending"   # 既不自动入库，也不自动驳回


def test_unverified_is_neutral_in_score(db, monkeypatch):
    """联网成功但没命中，分数必须与不联网完全一致"""
    from app.services import web_probe

    monkeypatch.setattr(web_probe, "search_web", lambda *a, **kw: _res(
        ("完全无关", "https://a.com", "无关内容")))

    with_web = kv.verify_candidate(db, _cand("自造概念Xyz", "这是一种用于测试的概念"),
                                   use_web=True, web_budget={"left": 5})
    without = kv.verify_candidate(db, _cand("自造概念Xyz", "这是一种用于测试的概念"),
                                  use_web=False)
    assert with_web["score"] == pytest.approx(without["score"])


def test_bing_parser_prefers_result_blocks():
    """Bing 专用解析只取 b_algo，不能把页首导航当成结果"""
    from app.services import web_probe

    page = """
    <div class="b_header"><h2><a href="https://nav.example/">CNKI 中国知网</a></h2></div>
    <ol>
      <li class="b_algo"><h2><a href="https://a.com/1">检索增强生成详解</a></h2>
        <p>检索增强生成是一种结合检索与生成的技术</p></li>
      <li class="b_algo"><h2><a href="https://b.com/2">RAG 入门</a></h2>
        <p>RAG 是检索增强生成</p></li>
    </ol>
    """
    rows = web_probe._parse_bing(page, 6)
    assert len(rows) == 2
    assert rows[0]["url"] == "https://a.com/1"
    assert "检索增强生成" in rows[0]["snippet"]
    assert all("nav.example" not in r["url"] for r in rows)
