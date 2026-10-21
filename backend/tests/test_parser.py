"""抽取阶段：不要把「一句话」当成「一个知识点」

知识图谱的质量上限就是节点质量 —— 标题里混进句子残骸，会一路污染
总结的层级样例、核心枢纽、领域代表，最后印在 PPT 的**学习主线**上
（实际出现过「DOM → JavaScript → Vue → Vue 的学习曲线较平缓」）。

残骸有两个来源，本文件各钉一条：

  1. 按「首个谓语词」截断主语时，切出的是小句 ——
     `笔记要定期整理成知识结构，否则只是资料堆积。` 里的「只是」命中了谓语词表。
  2. 谓语不在动词表里（「可以」「能够」），主语切分直接放弃，
     随后从**兜底分支**把整句原样捞回来。

**测试跑的是完整抽取管线 `extract_nodes_from_text`，不是 `extract_entity`。**
单独调 `extract_entity` 会高估问题（句子类型分类与行角色判定在后面把关），
断言就会变成在测一个用户永远看不到的中间态。
"""
import pytest

from app.services.parser import extract_nodes_from_text, looks_like_clause

# test_data/kb_demo 里真实抽出来过的句子残骸
FRAGMENTS = [
    "笔记要定期整理成知识结构",
    "写文章之前先想清楚读者",
    "Vue 的学习曲线较平缓",
]

DOC = """# 写作与知识整理

## 知识整理

笔记要定期整理成知识结构，否则只是资料堆积。
读者决定了文章的起点。

## 写作

写文章之前先想清楚读者是谁，读者的知识背景决定了你从哪里讲起。
结构清晰的文章更容易被读懂。

## 前端工程

Vue 的学习曲线较平缓，适合中小型项目快速交付。
构建工具可以把多个模块打包成一个文件。
"""

# 合法术语：这些绝不能被判成残骸
REAL_TERMS = [
    "读者", "结构", "笔记", "阅读", "构建工具", "服务端",
    "优先级", "先进先出", "人工智能", "性能", "功能", "技能",
    "核心要素", "主要矛盾", "规则引擎", "原则", "首都",
    "青鸟缓存协议", "彩虹标签体系", "HTTP 的状态码",
    "高可用架构设计", "可扩展性设计", "可靠性", "可行性",
    "JavaScript", "Node.js", "RESTful API",
]


def _entities(text: str) -> list:
    nodes, _ = extract_nodes_from_text(text, 1, 1)
    return [n["entity"] for n in nodes]


# ---------------------------------------------------------------- 管线级

def test_sentence_fragments_are_not_extracted_as_nodes():
    """完整管线上，三句残骸都不能变成知识点。"""
    entities = _entities(DOC)
    assert entities, "一个节点都没抽出来，用例失去意义"
    for frag in FRAGMENTS:
        assert frag not in entities, f"句子残骸被当成知识点了：{frag!r}（实得 {entities}）"


def test_fragments_do_not_fall_back_to_section_heading():
    """残骸被拦掉后不能回落到本节标题 —— 标题是结构，不是内容。"""
    entities = _entities(DOC)
    assert entities, "一个节点都没抽出来，用例失去意义"
    assert "知识整理" not in entities, entities
    assert "写作" not in entities, entities
    assert "前端工程" not in entities, entities


def test_legitimate_sentences_still_produce_nodes():
    """正例对照：能抽出主语的正文句仍产生节点。"""
    entities = _entities("知识图谱是一种用图结构表示实体关系的技术。")
    assert "知识图谱" in entities, entities


def test_whole_sentence_without_a_known_verb_is_not_a_node():
    """没有标题可兜底时，整句也不能顺着兜底分支漏出来。

    `数据库索引可以加快查询速度。` 这种句子很常见：谓语「可以」不在
    动词表里 → 主语切分放弃 → 若无长度/形态检查，整句就会被当成知识点。
    """
    entities = _entities("数据库索引可以加快查询速度。")
    assert "数据库索引可以加快查询速度" not in entities, f"整句成了知识点：{entities}"


# ---------------------------------------------------------------- 规则级

@pytest.mark.parametrize("term", REAL_TERMS)
def test_real_terms_are_kept(term):
    """真术语一个都不能被误杀 —— 这是这条规则能不能用的前提。"""
    assert not looks_like_clause(term), f"误杀真术语：{term!r}"


def test_clause_rule_needs_both_length_and_a_mid_sentence_marker():
    """两个约束缺一不可，拆开验证它们各自在防什么。"""
    # 短词一律放行：术语普遍很短，长度门槛把误杀挡在门外
    assert not looks_like_clause("核心要素")
    assert not looks_like_clause("优先级")        # 「先」在词首，不是状语
    assert not looks_like_clause("先进先出")
    assert not looks_like_clause("性能")          # 「能」在词中，不是情态动词
    assert not looks_like_clause("人工智能")
    assert not looks_like_clause("高可用架构设计")  # 「可」单独不算「可以」
    # 够长 + 句中出现状/情态词 → 判为小句
    assert looks_like_clause("笔记要定期整理成知识结构")
    assert looks_like_clause("写文章之前先想清楚读者")
    assert looks_like_clause("数据库索引可以加快查询速度")
