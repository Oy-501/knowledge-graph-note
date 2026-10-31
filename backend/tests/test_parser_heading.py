"""Markdown 小节标题作为知识点名的回归测试。

背景：标题只用于领域分类时，实体名会从正文首句抽主语，
出现「no-cache 并不意味着不缓存」「树的节点与磁盘页对齐」这类句子残骸。
"""
from app.services.parser import extract_nodes_from_text


def _entities(text):
    nodes, _ = extract_nodes_from_text(text, 1, 1)
    return [n["entity"] for n in nodes]


def test_heading_is_used_as_entity():
    text = ("### no-cache 与 no-store\n\n"
            "no-cache 并不意味着不缓存，而是允许存储但每次使用前必须回源校验。\n")
    assert _entities(text) == ["no-cache 与 no-store"]


def test_heading_with_english_and_hyphen():
    text = ("### Last-Modified 与 If-Modified-Since\n\n"
            "Last-Modified 用资源的最后修改时间做校验，精度只到秒，因此优先使用 ETag。\n")
    assert _entities(text) == ["Last-Modified 与 If-Modified-Since"]


def test_short_heading_with_summary_body():
    """短标题配摘要式开头（正文抽出的词与标题无关）也要用标题。"""
    text = ("### 哈希文件名与 immutable\n\n"
            "构建产物使用内容哈希命名时，可以配合 immutable 长期缓存。\n")
    assert _entities(text) == ["哈希文件名与 immutable"]


def test_preamble_is_skipped():
    text = ("本文件由联网检索整理，来源包括若干技术博客。\n\n"
            "### B+ 树\n\nB+ 树是一种多路平衡查找树，非叶节点只保存键和指针。\n")
    assert _entities(text) == ["B+ 树"]


def test_long_heading_falls_back_to_body():
    heading = ("这是一个非常长的章节标题用来测试回退逻辑因为我们已经超过了四十个字符的限制"
               "所以应当回退到正文抽取实体而不是直接采用整句标题")
    text = f"### {heading}\n\nB+ 树是一种多路平衡查找树，叶子节点保存数据。\n"
    ents = _entities(text)
    assert ents and ents[0] != heading


def test_plain_text_still_uses_subject():
    """没有标题的纯文本不受影响，仍按正文主语抽取。"""
    text = "ETag 是响应体的内容指纹，未变更时服务端返回 304。\n"
    assert _entities(text) == ["ETag"]
