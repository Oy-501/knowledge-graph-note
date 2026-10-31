"""B 站搜索页的 SSR 数据解析（离线用例，不联网）。"""
from app.services.web_probe import parse_bilibili_videos

HTML = (
    'x,bvid:"BV1bs421u7pY",title:"数据结构合集 - B+树",desc:Z,pic:"a.jpg",'
    'y,bvid:"BV1wsnB6AErS",title:"\\u003Cem class=\\"keyword\\">B+树\\u003C/em\\u003E 真题",'
)


def test_parse_videos_from_ssr_state():
    videos = parse_bilibili_videos(HTML)
    assert len(videos) == 2
    assert videos[0]["url"] == "https://www.bilibili.com/video/BV1bs421u7pY"
    assert videos[0]["site"] == "bilibili"
    assert videos[0]["title"] == "数据结构合集 - B+树"


def test_highlight_markup_is_stripped():
    videos = parse_bilibili_videos(HTML)
    assert "<em" not in videos[1]["title"]
    assert "B+树" in videos[1]["title"]


def test_duplicates_are_dropped():
    assert len(parse_bilibili_videos(HTML + HTML)) == 2


def test_empty_html():
    assert parse_bilibili_videos("") == []
