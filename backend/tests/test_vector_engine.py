"""语义向量的可测不变量

这里**不**断言具体数值（数值取决于用哪个引擎、哪版模型），只断言「关系」——
这样同一套用例在降级引擎和真模型上都成立：

  · 中文必须切成多个词元（曾经按空白切词 → 整句变 1 个词元 → 相似度恒为 0）
  · 说法不同但意思相同的两句，必须比无关的两句更像
  · 引擎指纹变了，旧向量就必须被判为陈旧
  · 维度不同的两个向量要能被识别为「没法比」，而不是当成「不相似」

最后两条对应两次真实事故，见 `docs/语义向量说明.md`。
"""
import math

import pytest

from app.services import vector_engine as ve


# ---------------------------------------------------------------- 切词

def test_chinese_is_tokenized_per_character():
    """中文没有空格，必须按字切。整句一个词元是历史 bug，会让相似度恒为 0。"""
    tokens = ve.analyze("数据库索引可以加快查询速度")
    assert len(tokens) > 1, f"中文整句只切出 {len(tokens)} 个词元：{tokens}"
    assert "数据" in tokens, "相邻汉字应切成二元组"


def test_paraphrase_shares_tokens_but_different_words():
    """换了说法的两句要有公共词元，这是 β 维对中文有信息量的前提。"""
    a = set(ve.analyze("数据库索引可以加快查询速度"))
    b = set(ve.analyze("为数据表建立索引能提升检索性能"))
    assert a & b, f"同义改写句零重叠：{a} vs {b}"


def test_unrelated_sentences_share_nothing():
    a = set(ve.analyze("数据库索引可以加快查询速度"))
    b = set(ve.analyze("今天中午食堂的红烧肉有点咸"))
    assert not (a & b), "完全无关的两句不该有公共词元（否则相似度是噪声）"


def test_empty_and_whitespace_yield_no_tokens():
    assert ve.analyze("") == []
    assert ve.analyze("   \n\t ") == []


def test_latin_words_are_tokenized_by_word():
    tokens = ve.analyze("Database index speeds up query")
    assert "database" in tokens and "index" in tokens


def test_stopword_only_bigrams_are_dropped():
    """「的的」这类纯虚词二元组不该进入词表，否则会拉高任意两句的相似度。"""
    assert "的的" not in ve.analyze("的的的的")


# ---------------------------------------------------------------- 排序能力（核心里程碑）

def test_paraphrase_scores_higher_than_unrelated():
    """最重要的一条：改写对的相似度必须高于无关对。

    这条掉了就说明 β 维在瞎打分 —— 分数看着有，实际没信息量。
    """
    para = ve.cosine_similarity(
        ve.encode("索引失效是因为对列使用了函数"),
        ve.encode("在字段上套函数会导致索引无法命中"),
    )
    unrel = ve.cosine_similarity(
        ve.encode("索引失效是因为对列使用了函数"),
        ve.encode("楼下的猫又跑到阳台上晒太阳"),
    )
    assert para > unrel, f"改写对 {para:.3f} 未超过无关对 {unrel:.3f}"


def test_identical_text_scores_one():
    v = ve.encode("数据库索引可以加快查询速度")
    assert ve.cosine_similarity(v, v) == pytest.approx(1.0, abs=1e-6)


# ---------------------------------------------------------------- 余弦与 Jaccard

def test_cosine_basic_geometry():
    assert ve.cosine_similarity([1.0, 0.0], [1.0, 0.0]) == pytest.approx(1.0)
    assert ve.cosine_similarity([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)


def test_cosine_dimension_mismatch_returns_zero():
    """维度不同 → 返回 0。这是「没法比」不是「不相似」，调用方须自行区分。"""
    assert ve.cosine_similarity([1.0, 0.0, 0.0], [1.0, 0.0]) == 0.0


def test_cosine_handles_empty_and_zero_vectors():
    assert ve.cosine_similarity([], []) == 0.0
    assert ve.cosine_similarity([0.0, 0.0], [1.0, 1.0]) == 0.0


def test_cosine_is_symmetric_and_bounded():
    a, b = ve.encode("数据库索引"), ve.encode("查询性能优化")
    assert ve.cosine_similarity(a, b) == pytest.approx(ve.cosine_similarity(b, a))
    assert 0.0 <= ve.cosine_similarity(a, b) <= 1.0


def test_jaccard_basics():
    assert ve.jaccard_similarity(["a", "b"], ["a", "b"]) == pytest.approx(1.0)
    assert ve.jaccard_similarity(["a"], ["b"]) == pytest.approx(0.0)
    assert ve.jaccard_similarity(["a", "b"], ["b", "c"]) == pytest.approx(1 / 3)
    assert ve.jaccard_similarity([], ["a"]) == 0.0


# ---------------------------------------------------------------- 降级编码

def test_tfidf_vector_shape_and_normalization():
    v = ve._tfidf_encode("数据库索引可以加快查询速度")
    assert len(v) == ve.FALLBACK_DIM, "维度必须是约定的固定值"
    norm = math.sqrt(sum(x * x for x in v))
    assert norm == pytest.approx(1.0, abs=1e-6), "必须 L2 归一，否则长度会影响余弦"


def test_tfidf_empty_text_is_zero_vector():
    v = ve._tfidf_encode("")
    assert len(v) == ve.FALLBACK_DIM
    assert all(x == 0.0 for x in v)


def test_tfidf_uses_signed_hashing():
    """纯取模会让碰撞的两个无关词互相加正分、凭空造相似度；带符号哈希让期望为 0。"""
    v = ve._tfidf_encode("数据库索引 java python 缓存 消息队列 分布式锁")
    assert any(x < 0 for x in v), "向量里没有负分量，说明哈希没带符号"


def test_idf_changes_weights():
    """建了 IDF 表之后，稀有词的权重必须高于高频词。

    注意传进去的必须是 `analyze()` 真正会产出的词元（中文是二元组），
    传整个词是查不到的，会走默认权重 —— 那样用例会「永远成立」而没有意义。
    """
    ve.reset_idf()
    common = "数据库索引优化"          # analyze -> 数据/据库/库索/索引/引优/优化
    rare = "布隆过滤器拦截"            # analyze -> 布隆/隆过/过滤/滤器/器拦/拦截
    ve.build_idf([common] * 20 + [rare])
    assert "布隆" in ve.analyze(rare), "样本失效：期望能切出「布隆」"
    assert ve._weight("布隆") > ve._weight("数据"), "稀有词权重应更高"
    ve.reset_idf()


def test_build_idf_returns_doc_count():
    """返回的是「有效文档数」—— 切不出词元的文本不计入。"""
    ve.reset_idf()
    assert ve.build_idf(["alpha beta", "beta gamma", "delta"]) == 3
    # 单字母拉丁词与纯虚词会被过滤，整条文本因此不贡献任何词元
    assert ve.build_idf(["a b c", "x y z"]) == 0
    ve.reset_idf()


# ---------------------------------------------------------------- 引擎指纹与陈旧判定

def test_engine_signature_is_stable_and_identifies_algo():
    sig1 = ve.engine_signature()
    sig2 = ve.engine_signature()
    assert sig1 == sig2, "同一进程内指纹必须稳定，否则每次调用都会以为要重建"
    assert ve.ALGO_VERSION in sig1, "指纹必须包含算法版本 —— 改算法要让旧向量失效"


def test_embedding_is_stale_semantics():
    sig = ve.engine_signature()
    assert ve.embedding_is_stale(sig) is False, "同引擎不该判为陈旧"
    assert ve.embedding_is_stale(None) is True, "没有指纹一律视为陈旧"
    assert ve.embedding_is_stale("") is True
    assert ve.embedding_is_stale("st|other-model|768|1") is True
    assert ve.embedding_is_stale("tfidf|ngram|256|0") is True, "算法版本不同也须判陈旧"


def test_get_engine_info_shape():
    info = ve.get_engine_info()
    for key in ("mode", "dim", "signature", "degraded", "reason", "idf"):
        assert key in info, f"缺字段 {key}"
    assert isinstance(info["dim"], int) and info["dim"] > 0, "维度要从模型/常量读出实值"


def test_node_text_composition():
    """参与编码的文本口径要稳定 —— 改口径等于让所有旧向量失效。"""
    text = ve.node_text({
        "entity": "数据库索引", "title": "索引", "keywords": ["查询"],
        "entities": ["B+树"], "description": "加速检索",
    })
    for part in ("数据库索引", "索引", "查询", "B+树", "加速检索"):
        assert part in text


# ---------------------------------------------------------------- 指纹与陈旧实际落库

def test_embedding_health_classifies_stale_and_broken(db, make_file):
    """陈旧检测机制本身：新指纹算新、旧指纹算陈旧、坏 JSON 单独计数。

    这是「换引擎后必须重建向量」能否被发现的关键 —— 它一旦失灵，
    β 维会静默失效，而且看不出原因（维度不同的 cosine 恒为 0）。
    """
    import json

    from app.models.models import Node

    fid = make_file("vec.md", nodes=0)
    sig = ve.engine_signature()
    vec = json.dumps([0.1, 0.2, 0.3, 0.4])
    db.add_all([
        Node(file_id=fid, user_id=1, entity="新鲜", embedding=vec, embedding_meta=sig),
        Node(file_id=fid, user_id=1, entity="陈旧", embedding=vec,
             embedding_meta="st|other-model|768|1"),
        Node(file_id=fid, user_id=1, entity="无向量", embedding=None, embedding_meta=None),
        Node(file_id=fid, user_id=1, entity="坏向量", embedding="{not json",
             embedding_meta=sig),
    ])
    db.commit()

    h = ve.embedding_health(db)
    assert h["total"] == 4
    assert h["with_embedding"] == 3, f"3 条有向量：{h}"
    assert h["empty"] == 1
    # 两类失败模式必须分开计数，混成一个数字会丢掉「该怎么修」的信息：
    #   stale  —— 引擎指纹不匹配（换过模型/算法）→ 重建即可
    #   broken —— 载荷本身坏了（JSON 解析不了）
    # 坏向量那条的指纹是对的，所以只落在 broken，不算 stale。
    assert h["stale"] == 1, f"只有「旧指纹」那条是陈旧：{h}"
    assert h["broken"] == 1, "坏 JSON 必须单独计数，不能静默吞掉"
    assert h["dims"] == {4: 2}, f"维度分布应只统计能解析的：{h}"


def test_embedding_health_clean_when_all_fresh(db, make_file):
    import json

    from app.models.models import Node

    fid = make_file("vec2.md", nodes=0)
    db.add(Node(file_id=fid, user_id=1, entity="新", embedding=json.dumps([1.0]),
                embedding_meta=ve.engine_signature()))
    db.commit()
    h = ve.embedding_health(db)
    assert h["stale"] == 0 and h["broken"] == 0 and h["empty"] == 0
