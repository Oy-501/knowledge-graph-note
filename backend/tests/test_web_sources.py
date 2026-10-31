"""联网来源的可信度过滤、分级与稳定入口。"""
from app.services.web_existence import check_existence
from app.services.web_probe import (evidence_sources, matches_entity,
                                    reference_links, source_tier,
                                    video_search_links)


def test_source_tier_classification():
    assert source_tier("https://dev.mysql.com/doc/refman/8.0/en/") == "authority"
    assert source_tier("https://zh.wikipedia.org/wiki/B%2B_tree") == "authority"
    assert source_tier("https://blog.csdn.net/x/article/details/1") == "community"
    assert source_tier("https://speedtest.cn/") == "unknown"
    assert source_tier("") == "unknown"


def _fake_results(domains):
    return {
        "online": True,
        "results": [
            {"title": f"B+ 树 定义 {i}",
             "snippet": "B+ 树 是 一种 平衡 多路 查找 树 ， 常用 于 数据库 索引",
             "url": f"https://{d}/post/{i}"}
            for i, d in enumerate(domains)
        ],
    }


DESC = "B+ 树是一种平衡多路查找树，常用于数据库索引与范围查询"


def test_unknown_only_sources_cannot_confirm():
    """全是未知站（聚合、转载）时最高只到 probable。"""
    res = check_existence("B+ 树", DESC, _fake_results(["a1.com", "b2.com", "c3.com"]))
    assert res["status"] != "confirmed"
    assert res["tiers"]["unknown"] == 3


def test_authority_sources_can_confirm():
    res = check_existence("B+ 树", DESC, _fake_results(["dev.mysql.com", "wikipedia.org"]))
    assert res["tiers"]["authority"] == 2
    assert res["status"] == "confirmed"


def test_evidence_sources_only_keeps_relevant():
    """来源列表只保留与知识点相关、且带 URL 的条目。"""
    evidence = [
        {"type": "web-sample", "detail": "B+树 看这一篇就够了", "url": "https://a.com/1", "source": "bing"},
        {"type": "web-sample", "detail": "海纳各领域知识，新一代百科全书", "url": "https://b.com/2", "source": "sogou"},
        {"type": "web", "detail": "命中 4 个来源", "url": "https://c.com/3", "source": "bing"},
        {"type": "rule", "detail": "标题形态正常", "url": ""},
    ]
    out = evidence_sources("B+ 树", evidence)
    assert [x["url"] for x in out] == ["https://a.com/1"]


def test_unrelated_results_are_filtered():
    """搜索源被限流时会返回首页推荐，这类结果必须被过滤掉。"""
    assert matches_entity("B+ 树", {"title": "B+树 看这一篇就够了"})
    assert not matches_entity("B+ 树", {"title": "海纳各领域知识，新一代百科全书"})
    assert not matches_entity("B+ 树", {"title": "手机微信传输助手的文件在哪个文件夹"})


def test_contrast_title_matches_either_side():
    item = {"title": "HTTP 缓存：no-store 与 no-cache 的区别"}
    assert matches_entity("no-cache 与 no-store", item)


def test_reference_links_are_always_available():
    links = reference_links("B+ 树")
    assert any("baike.baidu.com" in l["url"] for l in links)
    assert any("wikipedia.org" in l["url"] for l in links)
    assert all("B+ 树" in l["title"] for l in links)
    assert reference_links("") == []


def test_video_search_links_cover_players():
    links = video_search_links("B+ 树")
    assert {l["site"] for l in links} == {"bilibili", "youtube", "douyin"}
    assert all("B%2B" in l["url"] or "%E6%A0%91" in l["url"] for l in links)


# ---- Bing Search API（可选 key 化源）----
def test_bing_api_absent_returns_none(monkeypatch):
    from app.config import settings
    from app.services import web_probe
    monkeypatch.setattr(settings, "BING_SEARCH_API_KEY", "")
    assert web_probe._search_bing_api("B+ 树", 5, 3) is None


def test_bing_api_parses_webpages(monkeypatch):
    import json
    import urllib.request
    from app.config import settings
    from app.services import web_probe

    class _Resp:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return json.dumps({"webPages": {"value": [
                {"name": "B+ 树 - 维基百科", "url": "https://zh.wikipedia.org/x",
                 "snippet": "B+ 树是一种平衡多路查找树"},
                {"name": "无链接页", "url": "", "snippet": "应被过滤"},
            ]}}).encode("utf-8")

    monkeypatch.setattr(settings, "BING_SEARCH_API_KEY", "test-key")
    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **kw: _Resp())
    out = web_probe._search_bing_api("B+ 树", 5, 3)
    assert len(out) == 1
    assert out[0]["url"].startswith("https://zh.wikipedia.org")
