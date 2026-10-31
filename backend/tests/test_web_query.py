"""联网检索词构造：对比型标题需要拆开查。"""
from app.services.web_probe import split_entity_terms


def test_split_english_contrast_title():
    assert split_entity_terms("Last-Modified 与 If-Modified-Since") == [
        "Last-Modified", "If-Modified-Since"]


def test_split_no_cache_and_no_store():
    assert split_entity_terms("no-cache 与 no-store") == ["no-cache", "no-store"]


def test_chinese_compound_is_not_split():
    """「聚簇索引与回表」没有空格，按整句检索，不能被切成「聚簇索引」「回表」"""
    assert split_entity_terms("聚簇索引与回表") == []


def test_plain_entity():
    assert split_entity_terms("B+ 树") == []
    assert split_entity_terms("") == []
