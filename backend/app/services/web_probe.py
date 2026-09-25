"""联网校验：抓取公开搜索结果页做交叉验证（零配置、可降级）

设计取舍（用户已确认）：
  - 不依赖任何 API Key，直接抓公开搜索页的标题 + 摘要；
  - 网络不通 / 被拦 / 解析失败时**不报错**，返回 online=False，判定侧标注「未联网」并只靠本地证据；
  - 带内存缓存与并发预算，避免整批判定时把时间耗在网络上。
"""
import html
import re
import time
import urllib.parse
import urllib.request
from typing import Dict, List, Optional

from loguru import logger

_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")

# 查询 → (时间戳, 结果)
_CACHE: Dict[str, tuple] = {}
_TAG = re.compile(r"<[^>]+>")


def _strip_tags(fragment: str) -> str:
    text = _TAG.sub(" ", fragment or "")
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def _fetch(url: str, timeout: float) -> Optional[str]:
    req = urllib.request.Request(url, headers={
        "User-Agent": _UA,
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Accept": "text/html,application/xhtml+xml",
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read(600_000)
    except Exception as exc:
        logger.debug(f"联网检索失败（{url[:60]}）：{exc}")
        return None
    for enc in ("utf-8", "gbk", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


# ---------------------------------------------------------------- 解析
# 各搜索引擎的 DOM 结构经常改版，这里用「标题块 + 邻近文本」的通用提取，
# 而不是写死站点选择器；提取不到时再退化为全文关键词命中判断。

_BLOCK = re.compile(r"<h[123][^>]*>(.*?)</h[123]>(.{0,800}?)(?=<h[123]|</body>|$)",
                    re.S | re.I)
_HREF = re.compile(r'href="(https?://[^"]+)"', re.I)
_ANCHOR_FALLBACK = re.compile(r'<a[^>]+href="(https?://[^"]+)"[^>]*>(.{4,120}?)</a>', re.S | re.I)


def _parse_generic(page: str, limit: int) -> List[Dict]:
    """通用结果提取：<h2>/<h3> 块 + 其后文本作为摘要"""
    out, seen = [], set()
    for m in _BLOCK.finditer(page):
        title_html, tail_html = m.group(1), m.group(2)
        title = _strip_tags(title_html)
        if len(title) < 2 or title in seen:
            continue
        hm = _HREF.search(title_html) or _HREF.search(tail_html)
        seen.add(title)
        out.append({
            "title": title[:120],
            "url": hm.group(1) if hm else "",
            "snippet": _strip_tags(tail_html)[:240],
        })
        if len(out) >= limit:
            break

    if not out:  # 退路：取所有锚文本
        for m in _ANCHOR_FALLBACK.finditer(page):
            title = _strip_tags(m.group(2))
            if len(title) < 4 or title in seen:
                continue
            seen.add(title)
            out.append({"title": title[:120], "url": m.group(1), "snippet": ""})
            if len(out) >= limit:
                break
    return out


def _parse_fulltext(page: str, limit: int) -> List[Dict]:
    """最后兜底：把整页文本当作一条结果（supports() 仍能做关键词命中判断）"""
    text = _strip_tags(page)
    return [{"title": text[:200], "url": "", "snippet": text[:600]}] if text else []


_PROVIDERS = [
    ("bing", "https://cn.bing.com/search?q={q}&ensearch=0", _parse_generic),
    ("sogou", "https://www.sogou.com/web?query={q}", _parse_generic),
    ("so", "https://www.so.com/s?q={q}", _parse_generic),
    ("baidu", "https://www.baidu.com/s?wd={q}", _parse_generic),
    ("duckduckgo", "https://duckduckgo.com/html/?q={q}", _parse_generic),
]


def search_web(query: str, timeout: float = 6.0, limit: int = 6,
               cache_ttl: int = 900) -> Dict:
    """检索公开搜索页；全部失败时返回 online=False（调用方据此标注"未联网"）"""
    q = (query or "").strip()[:120]
    if not q:
        return {"online": False, "provider": "", "results": [], "error": "空查询"}

    cached = _CACHE.get(q)
    if cached and time.time() - cached[0] < cache_ttl:
        return {**cached[1], "cached": True}

    errors = []
    for name, tpl, parser in _PROVIDERS:
        page = _fetch(tpl.format(q=urllib.parse.quote(q)), timeout)
        if not page:
            errors.append(f"{name}: 无法访问")
            continue
        try:
            results = [r for r in parser(page, limit) if r.get("title")]
            if not results:
                results = _parse_fulltext(page, limit)   # 布局改版时的兜底
        except Exception as exc:
            errors.append(f"{name}: 解析失败 {exc}")
            continue
        if results:
            payload = {"online": True, "provider": name, "results": results,
                       "error": "", "cached": False}
            _CACHE[q] = (time.time(), payload)
            return payload
        errors.append(f"{name}: 无结果")

    payload = {"online": False, "provider": "", "results": [],
               "error": "；".join(errors)[:300], "cached": False}
    _CACHE[q] = (time.time(), payload)   # 失败也缓存，避免整批判定反复重试
    return payload


def clear_cache():
    _CACHE.clear()


def supports(entity: str, results: List[Dict]) -> Dict:
    """判断检索结果是否"支持"该知识点存在（标题/摘要里是否出现该词及其共现词）"""
    term = (entity or "").strip()
    if not term or not results:
        return {"hits": 0, "strong": 0, "samples": []}
    hits, samples = 0, []
    for r in results:
        text = f"{r.get('title', '')} {r.get('snippet', '')}"
        if term.lower() in text.lower():
            hits += 1
            if len(samples) < 3:
                samples.append({"title": r["title"][:80], "url": r.get("url", ""),
                                "snippet": (r.get("snippet") or "")[:160]})
    return {"hits": hits, "strong": min(hits, 3), "samples": samples}
