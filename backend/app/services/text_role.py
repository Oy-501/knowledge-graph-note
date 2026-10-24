"""文本行角色判定：标题 / 正文 / 噪音。

标题（章节名、列表小标题、文件名）不是知识内容，只作上下文。
只有 body 行进入抽取与摘要；heading 只更新当前章节名。

短行判标题是刻意的保守选择：宁可少抽一条，也不把章节名当成知识点。
"""
import re

_MD_HEADING = re.compile(r"^\s{0,3}#{1,6}\s*")
_NUM_HEADING = re.compile(r"^[（(]?[一二三四五六七八九十百千\d]{1,3}[)）、.．]\s*\S")
_SENT_END = re.compile(r"[。！？；!?;]$")
_COMMA = re.compile(r"[，,]")
_DEFINITIONAL = re.compile(r"(是|指的是|指|属于|用于|包括|包含|分为|通过|基于|采用|实现)")
_VERB_START = re.compile(
    r"^(分为|负责|增加|加入|注入|记录|执行|保存|放到|放在|用于|包括|包含|例如|"
    r"通过|采用|基于|作为|实现|提供|表示|说明|解决|支持|遵循|减少|提升|降低|"
    r"避免|防止|保证|确保|需要|可以|不要|能够|使得)")

_HEADING_MAX = 24


def line_role(line: str, next_line: str = "") -> str:
    """返回 heading | body | noise。

    判定顺序：空行 → 显式标题 → 编号标题 → 短行无句末标点（且下一行更长）→ 正文。
    """
    text = (line or "").strip()
    if not text:
        return "noise"
    if _MD_HEADING.match(text):
        return "heading"
    if _NUM_HEADING.match(text):
        return "heading"

    nxt = (next_line or "").strip()
    if (len(text) <= _HEADING_MAX
            and not _SENT_END.search(text)
            and not _COMMA.search(text)
            and not _DEFINITIONAL.search(text)
            and not _VERB_START.match(text)):
        if nxt and len(nxt) > len(text):
            return "heading"
        if not nxt and len(text) <= 12:
            return "heading"

    return "body"


def is_heading(line: str, next_line: str = "") -> bool:
    """判断该行是否为标题。"""
    return line_role(line, next_line) == "heading"
