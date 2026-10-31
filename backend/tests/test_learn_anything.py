"""Learn Anything 语料匹配与翻译闸门。"""
from app.services import learn_anything as la
from app.services.translate import translate_title


def test_reading_returns_items_for_matching_domain():
    items = la.reading_for("HTTP 缓存", "web", limit=3)
    assert items
    assert len(items) <= 3
    assert all(i["url"].startswith("http") for i in items)
    assert all(i["title_zh"] for i in items)


def test_unrelated_entity_gets_nothing():
    """宁可不给，也不把 Web 资源挂到无关概念上。"""
    assert la.reading_for("费马大定理", "", limit=3) == []


def test_unknown_domain_is_safe():
    """没有对应主题的领域直接返回空，不抛异常。"""
    assert la.reading_for("费马大定理", "chemistry", limit=3) == []


def test_brand_title_is_not_translated():
    """纯域名类标题不送去机翻（web.dev 曾被译成「测长仪顶杆」）。"""
    assert translate_title("someblog.dev", "someblog.dev") == "someblog.dev"


def test_chinese_input_passes_through():
    assert translate_title("缓存控制", "") == "缓存控制"


def test_overrides_have_priority():
    assert translate_title("What, exactly, is the DOM?",
                           "bitsofco.de") == "DOM 到底是什么？"
