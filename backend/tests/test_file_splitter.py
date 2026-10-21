"""大文件切割：切了也不丢知识点。

三条守卫：
  1. 小文件不切；
  2. 无空行、无标题的正文也只在句末落刀；
  3. 每一行都要被至少一片覆盖（overlap 之外不能有缺口）。
"""
from app.services.file_splitter import piece_text, plan_split, validate_plan


def _sentences(n: int) -> str:
    return "\n".join(f"第{i}条知识点说明了某个技术概念。" for i in range(n))


def test_small_file_is_not_split():
    plan = plan_split("第一句。第二句。", target_lines=100, target_chars=1000)
    assert plan["needed"] is False
    assert len(plan["pieces"]) == 1


def test_no_blank_lines_still_cuts_on_sentence_end():
    text = _sentences(1200)
    plan = plan_split(text, target_lines=100, target_chars=100000,
                      max_pieces=50, overlap_lines=2)
    assert plan["needed"] is True
    report = validate_plan(plan, text)
    assert report["ok"], report
    assert all(p["reason"] in ("句子边界", "段落边界", "标题边界", "文末")
               for p in plan["pieces"])


def test_cross_line_sentence_is_not_torn():
    """句子跨两行时，切点不能落在前半句之后"""
    lines = []
    for i in range(400):
        lines.append(f"第{i}条知识点的前半句")
        lines.append("接着后半句结束。")
    text = "\n".join(lines)
    plan = plan_split(text, target_lines=50, target_chars=100000,
                      max_pieces=50, overlap_lines=2)
    report = validate_plan(plan, text)
    assert not report["torn_cuts"], report


def test_every_non_empty_line_is_covered():
    text = _sentences(800)
    plan = plan_split(text, target_lines=80, target_chars=100000,
                      max_pieces=50, overlap_lines=3)
    report = validate_plan(plan, text)
    assert not report["gaps"], report


def test_structural_boundaries_are_preferred():
    parts = []
    for i in range(30):
        parts.append(f"# 章节{i}")
        parts.append("")
        parts.extend(f"第{i}-{j}条正文说明了某个技术概念。" for j in range(20))
    text = "\n".join(parts)
    plan = plan_split(text, target_lines=60, target_chars=100000,
                      max_pieces=50, overlap_lines=2)
    kinds = {p["reason"] for p in plan["pieces"]}
    assert "标题边界" in kinds or "段落边界" in kinds


def test_piece_text_carries_heading_context():
    text = "# 前端\n\n## Vue\n\nVue 是一个渐进式框架。\n"
    plan = plan_split(text, target_lines=100, target_chars=10000)
    body = piece_text(text, plan["pieces"][0])
    assert "# 前端" in body
    assert "Vue 是一个渐进式框架" in body


def test_single_huge_line_does_not_crash():
    text = "很长的句子" * 5000
    plan = plan_split(text, target_lines=10, target_chars=100,
                      max_pieces=5, overlap_lines=1)
    assert plan["pieces"]
    assert validate_plan(plan, text)["ok"] or plan["truncated_by_limit"]
