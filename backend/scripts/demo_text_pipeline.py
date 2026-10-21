"""联网抓真实网页，验证「标题/正文判别 + 抽取式摘要」。

跑法：
    py scripts/demo_text_pipeline.py
    py scripts/demo_text_pipeline.py --query "光合作用"
"""
import argparse
import html
import re
import sys
import urllib.request
from collections import Counter
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from app.services import web_probe  # noqa: E402
from app.services.text_role import line_role  # noqa: E402
from app.services.text_summary import summarize  # noqa: E402

_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")


def fetch_page(url: str, timeout: float = 8.0) -> str:
    req = urllib.request.Request(url, headers={
        "User-Agent": _UA,
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    })
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read(800_000)
    for enc in ("utf-8", "gbk", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def extract_blocks(page: str):
    """返回 (页面标题, [(tag, text), ...])，只保留 h1-h3 与 p。"""
    title_m = re.search(r"(?is)<title[^>]*>(.*?)</title>", page)
    title = html.unescape(re.sub(r"\s+", " ", title_m.group(1))).strip() if title_m else ""

    page = re.sub(r"(?is)<(script|style|noscript|svg)[^>]*>.*?</\1>", " ", page)
    blocks = []
    for m in re.finditer(r"(?is)<(h[1-3]|p)\b[^>]*>(.*?)</\1>", page):
        tag, inner = m.group(1).lower(), m.group(2)
        text = html.unescape(re.sub(r"(?is)<[^>]+>", "", inner))
        text = re.sub(r"\s+", " ", text).strip()
        if len(text) >= 4:
            blocks.append((tag, text))
    return title, blocks


def main() -> int:
    parser = argparse.ArgumentParser(description="联网验证文本判别与摘要")
    parser.add_argument("--query", default="TCP 拥塞控制")
    args = parser.parse_args()

    print("=" * 74)
    print(f"主题：{args.query}")
    print("=" * 74)

    search = web_probe.search_web(f'"{args.query}"', timeout=8)
    urls = [r.get("url") for r in (search.get("results") or []) if r.get("url")]
    # 百科/维基优先，博客站多反爬
    urls.sort(key=lambda u: 0 if ("wikipedia" in u or "baike.baidu" in u) else 1)

    page, used_url = "", ""
    for url in urls[:5]:
        try:
            page = fetch_page(url)
            if page and "<p" in page:
                used_url = url
                break
        except Exception as exc:  # noqa: BLE001 - 演示脚本，抓不到就换下一个
            print(f"  抓取失败 {url[:60]}：{str(exc)[:60]}")
    if not used_url:
        print("没有可抓取的页面，改用搜索结果摘要做降级演示")
        text = "\n".join(r.get("snippet", "") for r in (search.get("results") or []))
        title = ""
        blocks = [("p", t) for t in text.split("\n") if t]
    else:
        title, blocks = extract_blocks(page)

    lines = [t for _, t in blocks]
    text = "\n".join(lines)
    roles = Counter()
    for i, line in enumerate(lines):
        nxt = lines[i + 1] if i + 1 < len(lines) else ""
        roles[line_role(line, nxt)] += 1

    print(f"来源：{used_url or '（降级：搜索结果摘要）'}")
    print(f"页面标题：{title[:80]}")
    print(f"正文块：{len(blocks)} 个 · 字符 {len(text)}")
    print(f"行角色：heading={roles['heading']} body={roles['body']} noise={roles['noise']}")

    out = summarize(text, max_sentences=6, max_chars=800)
    print("\n摘要：")
    print(out["summary"] or "（无）")
    print("\n关键词：", "、".join(out["keywords"][:8]))

    heading_texts = [t for tag, t in blocks if tag.startswith("h")]
    faithful = all(p in text for p in out["key_points"])
    heading_leak = [h for h in heading_texts if h and h in out["summary"]]

    print("\n验证：")
    print(f"  摘要句全部来自正文：{'通过' if faithful else '失败'}")
    print(f"  标题混入摘要：{'无' if not heading_leak else heading_leak[:3]}")
    print(f"  正文句数 {out['sentence_count']} · 摘要句数 {len(out['key_points'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
