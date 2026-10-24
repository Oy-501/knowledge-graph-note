"""功能边界回归：极值输入、非法参数、退化路径。

与 scripts/boundary_matrix.py 对应：脚本用于输出矩阵，本文件用于随全量回归。
"""
import pytest

from app.services.auth_service import _validate_credentials
from app.services.errors import AppError, clamp_paging, escape_like
from app.services.file_splitter import plan_split, validate_plan
from app.services.parser import extract_nodes_from_text
from app.services.text_role import line_role
from app.services.text_summary import summarize
from app.services.vector_engine import cosine_similarity
from app.services.web_existence import check_existence


# ---------------------------------------------------------------- 分页


@pytest.mark.parametrize("args,expect", [
    ((0,), (30, 0)),
    ((-1,), (30, 0)),
    ((201,), (200, 0)),
    ((1,), (1, 0)),
    (("abc",), (30, 0)),
    ((None, None), (30, 0)),
    ((10, -5), (10, 0)),
])
def test_paging_boundaries(args, expect):
    assert clamp_paging(*args) == expect


# ---------------------------------------------------------------- LIKE 转义


def test_like_escape_specials():
    assert escape_like("%") == "\\%"
    assert escape_like("_") == "\\_"
    assert "\\%" in escape_like("a%b_c")
    assert "\\\\" in escape_like("\\")


# ---------------------------------------------------------------- 行角色


@pytest.mark.parametrize("line,nxt,expect", [
    ("", "", "noise"),
    ("   ", "", "noise"),
    ("# 标题", "", "heading"),
    ("#", "", "heading"),
    ("一、概念", "", "heading"),
    ("3. 工具", "", "heading"),
    ("基础", "这是一段更长的正文说明。", "heading"),
    ("支持多种格式", "支持增量更新", "body"),
    ("这是一句完整的话。", "", "body"),
    ("这是一个超过二十四字但内容仍然像标题的短句", "这是一段明显更长的正文内容。", "body"),
])
def test_line_role_boundaries(line, nxt, expect):
    assert line_role(line, nxt) == expect


# ---------------------------------------------------------------- 摘要


def test_summary_negative_max_sentences_is_empty():
    """负数切片会反转语义（[:-1] 取到除最后一条外全部），必须归零"""
    out = summarize("第一句。第二句。第三句。", max_sentences=-1)
    assert out["key_points"] == []


def test_summary_zero_and_tiny_limits():
    assert summarize("第一句。第二句。", max_sentences=0)["key_points"] == []
    out = summarize("第一句。第二句。", max_sentences=5, max_chars=1)
    assert len(out["key_points"]) <= 1


def test_summary_pure_headers_is_empty():
    assert summarize("# 标题\n\n## 子标题\n", 5)["key_points"] == []


# ---------------------------------------------------------------- 切割


def test_split_empty_text_returns_one_piece():
    assert len(plan_split("")["pieces"]) == 1


def test_split_max_pieces_zero_does_not_crash():
    text = "\n".join(f"第{i}句。" for i in range(100))
    plan = plan_split(text, 10, 100000, max_pieces=0)
    assert len(plan["pieces"]) >= 1


def test_split_huge_overlap_does_not_explode():
    text = "\n".join(f"第{i}句。" for i in range(200))
    plan = plan_split(text, 50, 100000, max_pieces=10, overlap_lines=1000)
    assert len(plan["pieces"]) <= 10
    assert all(p["lines"] > 0 for p in plan["pieces"])


def test_split_no_punctuation_never_gaps():
    text = "\n".join(f"第{i}行没有标点" for i in range(300))
    plan = plan_split(text, 50, 100000, max_pieces=20)
    report = validate_plan(plan, text)
    assert not report["gaps"]
    assert not report["empty_pieces"]


# ---------------------------------------------------------------- 存在性


def test_existence_degenerate_inputs():
    assert check_existence("", "", {"online": True, "results": []})["status"] == "unverified"
    assert check_existence("RAG", "", {"online": False, "results": []})["status"] == "unavailable"


def test_existence_english_substring_is_not_a_hit():
    result = {"online": True, "provider": "t", "results": [
        {"title": "Storage", "url": "https://a.com", "snippet": "storage layout"}]}
    assert check_existence("RAG", "", result)["status"] == "unverified"


# ---------------------------------------------------------------- 认证


@pytest.mark.parametrize("username,password,ok", [
    ("a", "123456", False),
    ("ab", "123456", True),
    ("a" * 32, "123456", True),
    ("a" * 33, "123456", False),
    ("abc", "12345", False),
    ("abc", "a" * 72, True),
    ("abc", "a" * 73, False),
])
def test_credential_boundaries(username, password, ok):
    if ok:
        _validate_credentials(username, password)
    else:
        with pytest.raises(AppError):
            _validate_credentials(username, password)


# ---------------------------------------------------------------- 抽取


@pytest.mark.parametrize("text", ["", "# 标题\n\n## 子标题\n", "。。！！\n\n，；、\n"])
def test_extract_degenerate_texts(text):
    nodes, _ = extract_nodes_from_text(text, 1, 1)
    assert nodes == []


def test_extract_does_not_fall_back_to_heading():
    nodes, _ = extract_nodes_from_text(
        "# 知识整理\n\n笔记要定期整理成知识结构，否则只是资料堆积。\n", 1, 1)
    assert "知识整理" not in [n["entity"] for n in nodes]


# ---------------------------------------------------------------- 向量


def test_cosine_degenerate_inputs():
    assert cosine_similarity([0, 0], [1, 0]) == 0.0
    assert cosine_similarity([1, 0], [1, 0, 0]) == 0.0
    assert cosine_similarity([], []) == 0.0
