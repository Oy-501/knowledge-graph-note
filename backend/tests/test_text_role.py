"""标题/正文判别与抽取式摘要。

核心性质：
  1. 标题（Markdown、编号、短行小标题）不能进入抽取与摘要；
  2. 短行判标题要有条件（下一行更长），否则列表式正文会被整段丢掉；
  3. 摘要句必须全部来自原文，可逐句回溯。
"""
from app.services.text_role import line_role
from app.services.text_summary import summarize


# ---------------------------------------------------------------- 行角色


def test_markdown_heading():
    assert line_role("# 知识整理") == "heading"
    assert line_role("## 前端工程") == "heading"


def test_numbered_heading():
    assert line_role("一、基础概念辨析") == "heading"
    assert line_role("（2）实现") == "heading"
    assert line_role("3. Tools 工具模块") == "heading"


def test_short_line_followed_by_body_is_heading():
    assert line_role("知识整理", "笔记要定期整理成知识结构，否则只是资料堆积。") == "heading"


def test_body_sentence_is_not_heading():
    text = "笔记要定期整理成知识结构，否则只是资料堆积。"
    assert line_role(text, "") == "body"


def test_definition_sentence_is_body():
    assert line_role("知识图谱是一种用图结构表示实体关系的技术。", "") == "body"


def test_short_standalone_phrase_is_heading():
    assert line_role("写作", "") == "heading"


def test_consecutive_short_lines_are_body():
    """列表式短行：下一行不比它长时按正文处理，避免整段丢失"""
    assert line_role("支持多种格式", "支持增量更新") == "body"


def test_empty_is_noise():
    assert line_role("   ") == "noise"


# ---------------------------------------------------------------- 摘要


def test_summary_excludes_headings():
    text = """# 知识整理

## 核心原则

笔记要定期整理成知识结构，否则只是资料堆积。整理的目标是让知识可检索。
读者决定了文章的起点。
"""
    out = summarize(text, max_sentences=3)
    assert out["summary"]
    assert "知识整理" not in out["summary"]
    assert "核心原则" not in out["summary"]
    for sent in out["key_points"]:
        assert sent in text


def test_summary_is_faithful_to_source():
    text = ("光合作用是植物利用光能合成有机物的过程。"
            "叶绿体是光合作用的主要场所。"
            "光反应产生ATP和NADPH。")
    out = summarize(text, max_sentences=2)
    assert out["key_points"]
    assert all(p in text for p in out["key_points"])
    assert 0 < len(out["summary"]) <= 600


def test_empty_text():
    out = summarize("")
    assert out["summary"] == ""
    assert out["key_points"] == []
    assert out["sentence_count"] == 0


def test_max_sentences_respected():
    text = "。".join([f"第{i}个句子介绍了一个重要的技术概念" for i in range(10)]) + "。"
    out = summarize(text, max_sentences=3)
    assert len(out["key_points"]) <= 3


def test_summarize_endpoint(client, admin_headers):
    """接口层：标题不进入摘要，摘要来自正文"""
    r = client.post("/api/system/summarize", json={
        "text": "# 数据库索引\n\n数据库索引可以加快查询速度。B+ 树是索引最常用的数据结构。",
        "max_sentences": 2,
    }, headers=admin_headers)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["ok"] is True
    assert data["summary"]
    assert "数据库索引" in data["summary"]
    assert "# " not in data["summary"]
