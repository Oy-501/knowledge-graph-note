"""联网校验：抓取公开搜索结果页做交叉验证（零配置、可降级）

设计取舍（用户已确认）：
  - 不依赖任何 API Key，直接抓公开搜索页的标题 + 摘要；
  - 网络不通 / 被拦 / 解析失败时**不报错**，返回 online=False，判定侧标注「未联网」并只靠本地证据；
  - 带内存缓存与并发预算，避免整批判定时把时间耗在网络上。
"""
import html
import json
import re
import time
import urllib.parse
import urllib.request
from typing import Dict, List, Optional

from loguru import logger

from app.config import settings

_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")

# 查询 → (时间戳, 结果)
_CACHE: Dict[str, tuple] = {}
_TAG = re.compile(r"<[^>]+>")


def _strip_tags(fragment: str) -> str:
    """去掉 HTML 标签并压缩空白。"""
    text = _TAG.sub(" ", fragment or "")
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def _fetch(url: str, timeout: float) -> Optional[str]:
    """带 UA 抓取网页内容。"""
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
    """最后兜底：把整页文本当作一条结果（下游精确匹配仍可命中）"""
    text = _strip_tags(page)
    return [{"title": text[:200], "url": "", "snippet": text[:600]}] if text else []


# Bing 的结果在 <li class="b_algo"> 里；通用解析会先抓到页首导航，
# 真实结果被截断（实测：CNKI / 万方等站点名占满了配额）。
_BING_BLOCK = re.compile(
    r'<li[^>]*class="[^"]*b_algo[^"]*"[^>]*>(.*?)'
    r'(?=<li[^>]*class="[^"]*b_algo|<div[^>]*class="b_pag|</ol>)',
    re.S | re.I)


def _parse_bing(page: str, limit: int) -> List[Dict]:
    """Bing 专用解析：只取 b_algo 结果块，标题 + 摘要 + 真实 URL。"""
    out, seen = [], set()
    for m in _BING_BLOCK.finditer(page):
        block = m.group(1)
        hm = re.search(r'<h2[^>]*>\s*<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>',
                       block, re.S | re.I)
        if not hm:
            continue
        url = html.unescape(hm.group(1))
        title = _strip_tags(hm.group(2))
        if not title or title in seen:
            continue
        pm = re.search(r'<p[^>]*>(.*?)</p>', block, re.S | re.I)
        seen.add(title)
        out.append({
            "title": title[:120],
            "url": url,
            "snippet": (_strip_tags(pm.group(1)) if pm else "")[:240],
        })
        if len(out) >= limit:
            break
    return out


# 顺序按实测可用性排：sogou 返回空页、duckduckgo 常超时，放最后。
# 这两个不删：布局或网络变化后可能恢复，健康度机制会自动放行。
_PROVIDERS = [
    ("bing", "https://cn.bing.com/search?q={q}&ensearch=0", _parse_bing),
    ("so", "https://www.so.com/s?q={q}", _parse_generic),
    ("baidu", "https://www.baidu.com/s?wd={q}", _parse_generic),
    ("sogou", "https://www.sogou.com/web?query={q}", _parse_generic),
    ("duckduckgo", "https://duckduckgo.com/html/?q={q}", _parse_generic),
]

# 源健康度：连续失败的源进冷却，避免每次都白等一个挂掉的源超时
_PROVIDER_STATE: Dict[str, Dict] = {}
PROVIDER_COOLDOWN = 300.0      # 冷却 5 分钟
FAIL_COOLDOWN_AFTER = 3        # 连续失败几次开始冷却
FAIL_CACHE_TTL = 60            # 失败的查询只锁 1 分钟（原来 15 分钟，一次抖动锁死整批）


def _provider_ready(name: str) -> bool:
    state = _PROVIDER_STATE.get(name)
    return not state or time.time() >= state.get("until", 0.0)


def _mark_fail(name: str, reason: str) -> None:
    state = _PROVIDER_STATE.setdefault(name, {"fails": 0, "until": 0.0})
    state["fails"] = state.get("fails", 0) + 1
    if state["fails"] >= FAIL_COOLDOWN_AFTER:
        state["until"] = time.time() + PROVIDER_COOLDOWN
        state["fails"] = 0
        logger.info(f"搜索源 {name} 连续失败，冷却 {int(PROVIDER_COOLDOWN)}s（{reason}）")


def _mark_ok(name: str) -> None:
    state = _PROVIDER_STATE.setdefault(name, {"fails": 0, "until": 0.0})
    state["fails"] = 0
    state["until"] = 0.0


def _cache_get(key: str):
    hit = _CACHE.get(key)
    if not hit:
        return None
    ts, payload, ttl = hit
    return payload if time.time() - ts < ttl else None


def _cache_put(key: str, payload: Dict, ttl: float) -> None:
    _CACHE[key] = (time.time(), payload, ttl)
    if len(_CACHE) > 600:                 # 简单上限，防止长时间运行后无限增长
        for stale in list(_CACHE)[:200]:
            _CACHE.pop(stale, None)


def _search_bing_api(query: str, limit: int, timeout: float) -> Optional[List[Dict]]:
    """Bing Web Search API（Azure 免费层）。返回与 HTML 源同构的结果。

    这是本机网络环境下唯一可达的 key 化搜索 API：实测 Google/Brave/SerpAPI/
    SearXNG 均 000，只有 api.bing.microsoft.com 通（无 key 时 401）。
    返回 None 表示未配置或调用失败，由调用方退回 HTML 抓取。
    """
    key = (settings.BING_SEARCH_API_KEY or "").strip()
    if not key:
        return None
    url = ("https://api.bing.microsoft.com/v7.0/search?"
           f"q={urllib.parse.quote(query)}&count={limit}&mkt=zh-CN")
    try:
        req = urllib.request.Request(url, headers={
            "Ocp-Apim-Subscription-Key": key,
            "User-Agent": _UA,
        })
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8", "ignore"))
    except Exception as exc:
        logger.warning(f"Bing Search API 失败（退回 HTML 源）：{type(exc).__name__}: {exc}")
        return None

    out = []
    for page in (data.get("webPages") or {}).get("value") or []:
        out.append({
            "title": page.get("name") or "",
            "url": page.get("url") or "",
            "snippet": page.get("snippet") or "",
        })
    return [r for r in out if r["title"] and r["url"]] or None


def search_web(query: str, timeout: float = 6.0, limit: int = 6,
               cache_ttl: int = 900) -> Dict:
    """检索公开搜索页；全部失败时返回 online=False（调用方据此标注"未联网"）"""
    q = (query or "").strip()[:120]
    if not q:
        return {"online": False, "provider": "", "results": [], "error": "空查询"}

    cached = _cache_get(q)
    if cached:
        return {**cached, "cached": True}

    errors = []
    for name, tpl, parser in _PROVIDERS:
        if not _provider_ready(name):
            errors.append(f"{name}: 冷却中")
            continue
        page = _fetch(tpl.format(q=urllib.parse.quote(q)), timeout)
        if not page:
            _mark_fail(name, "无法访问")
            errors.append(f"{name}: 无法访问")
            continue
        try:
            results = [r for r in parser(page, limit) if r.get("title")]
            if not results:
                results = _parse_fulltext(page, limit)   # 布局改版时的兜底
        except Exception as exc:
            _mark_fail(name, "解析失败")
            errors.append(f"{name}: 解析失败 {exc}")
            continue
        if results:
            _mark_ok(name)
            payload = {"online": True, "provider": name, "results": results,
                       "error": "", "cached": False}
            _cache_put(q, payload, cache_ttl)
            return payload
        _mark_fail(name, "无结果")
        errors.append(f"{name}: 无结果")

    payload = {"online": False, "provider": "", "results": [],
               "error": "；".join(errors)[:300], "cached": False}
    # 失败只锁很短时间：整批判定里同一条查询失败一次，不该连累后续 15 分钟
    _cache_put(q, payload, FAIL_CACHE_TTL)
    return payload


def clear_cache():
    """清空检索结果缓存。"""
    _CACHE.clear()


# 对比型标题的连接词：两侧带空格时才拆（中文「参与」「和平」不能被误切）
_TERM_SPLIT = re.compile(r"\s+(?:与|和|及|以及|、|vs\.?|VS\.?)\s+")


def split_entity_terms(entity: str) -> List[str]:
    """把「A 与 B」拆成独立检索词。

    整句加引号检索会退化成泛词或英文单词的词典解释
    （`Last-Modified 与 If-Modified-Since` 会命中 last 的释义）。
    """
    parts = [p.strip() for p in _TERM_SPLIT.split(entity or "")]
    parts = [p for p in parts if len(p) >= 2]
    return parts[:2] if len(parts) >= 2 else []


def search_concept(entity: str, domain: str = "", timeout: float = 6.0,
                   limit: int = 6, cache_ttl: int = 900) -> Dict:
    """按概念检索：单概念直查，对比型标题分别查再按 URL 合并。"""
    suffix = ""
    if domain and domain not in ("general", "通用"):
        suffix = f" {domain}"

    terms = split_entity_terms(entity)
    if len(terms) <= 1:
        return search_multi(f'"{entity}"{suffix}', timeout=timeout,
                            limit=limit, cache_ttl=cache_ttl, expect=entity)

    merged = {"online": False, "provider": "", "results": [], "error": ""}
    for term in terms:
        res = search_multi(f'"{term}"{suffix}', timeout=timeout,
                           limit=limit, cache_ttl=cache_ttl, expect=term)
        if res.get("online"):
            merged["online"] = True
            merged["provider"] = merged["provider"] or res.get("provider", "")
            merged["results"].extend(res.get("results") or [])

    seen, uniq = set(), []
    for item in merged["results"]:
        url = item.get("url") or ""
        if url and url in seen:
            continue
        if url:
            seen.add(url)
        uniq.append(item)
    merged["results"] = uniq[:limit]
    if not merged["online"]:
        merged["error"] = "拆分后的两个概念均未检索到结果"
    return merged


VIDEO_SITES = ("bilibili.com", "youtube.com", "v.qq.com", "ixigua.com", "douyin.com")


def _flat(text: str) -> str:
    return re.sub(r"[\s\W_]+", "", (text or "").lower())


_TERM_SPLIT = re.compile(r"[\s/·,，、()（）]+")


def _term_hit(term: str, text: str) -> bool:
    """单个词是否命中：英文按整词，中文短词整词、长词看首尾四字。

    原实现把整句截前 6 个字（「jwt无状态认证」→「jwt无状态认」），
    中文长术语因此几乎永远匹配不上，连带把搜索结果全过滤掉。
    """
    low = (term or "").strip().lower()
    if not low:
        return False
    for part in _TERM_SPLIT.split(low):
        if not part:
            continue
        if part.isascii():
            # 归一后再比：文本里 cache-control 会被压成 cachecontrol
            flat_part = _flat(part)
            if len(flat_part) >= 3 and flat_part in text:
                return True
            continue
        flat = _flat(part)
        if not flat:
            continue
        if len(flat) <= 6:
            if flat in text:
                return True
        elif flat[:4] in text or flat[-4:] in text:
            return True
    return False


def matches_entity(entity: str, item: Dict) -> bool:
    """标题或摘要里是否出现 entity 的核心词。

    搜索引擎被限流或忽略 query 时会返回首页推荐（百科词条、热点新闻），
    这类结果和知识点毫无关系，混进证据链会误导人工判断。
    """
    text = _flat(f"{item.get('title', '')} {item.get('snippet', '')}")
    if not text:
        return False
    terms = split_entity_terms(entity) or [entity]
    return any(_term_hit(term, text) for term in terms)


def search_multi(query: str, limit: int = 8, max_providers: int = 3,
                 timeout: float = 6.0, cache_ttl: int = 900,
                 expect: str = "") -> Dict:
    """并发查询多个搜索源并合并去重，拿到更多站点级来源。

    单个源的结果高度同质，合并多个源能覆盖到不同站点；并发避免耗时翻倍。
    expect 给出关键词时，会过滤掉搜索引擎的兜底推荐。
    """
    key = f"multi::{query}"
    cached = _cache_get(key)
    if cached:
        return {**cached, "cached": True}

    # 配置了 Bing API 时优先走它：结构化结果、稳定，不依赖 HTML 解析，
    # 也不受 bing 对英文词返回词典兜底的影响。
    api_results = _search_bing_api(query, limit, timeout)
    if api_results:
        filtered = [r for r in api_results if not expect or matches_entity(expect, r)]
        if filtered:
            payload = {"online": True, "provider": "bing-api",
                       "results": filtered[:limit], "error": "", "cached": False}
            _cache_put(key, payload, cache_ttl)
            return payload

    from concurrent.futures import ThreadPoolExecutor

    def run(item):
        name, tpl, parser = item
        if not _provider_ready(name):
            return []
        page = _fetch(tpl.format(q=urllib.parse.quote(query)), timeout)
        if not page:
            _mark_fail(name, "无法访问")
            return []
        try:
            rows = [(name, r) for r in parser(page, limit) if r.get("title")]
        except Exception:
            _mark_fail(name, "解析失败")
            return []
        if rows:
            _mark_ok(name)
        else:
            _mark_fail(name, "无结果")
        return rows

    # 冷却中的源直接跳过，把名额让给可用的源
    ready = [p for p in _PROVIDERS if _provider_ready(p[0])]
    picked = (ready or _PROVIDERS)[:max(1, max_providers)]
    with ThreadPoolExecutor(max_workers=len(picked)) as pool:
        chunks = list(pool.map(run, picked))

    seen, results = set(), []
    for chunk in chunks:
        for name, item in chunk:
            url = item.get("url") or ""
            if not url or url in seen:
                continue
            if expect and not matches_entity(expect, item):
                continue
            seen.add(url)
            results.append({**item, "provider": name})

    payload = {
        "online": bool(results),
        "provider": ",".join(sorted({r["provider"] for r in results})),
        "results": results[:limit],
        "error": "" if results else "多个搜索源均无结果",
        "cached": False,
    }
    _cache_put(key, payload, cache_ttl if results else FAIL_CACHE_TTL)

    # 精确短语 + 严格过滤常把结果筛光（复合术语尤其明显）。
    # 回退到宽松查询再试一次；噪音由下游 check_existence 的精确命中再筛。
    if expect and not results:
        loose = search_multi(query.replace('"', ""), limit=limit,
                             max_providers=max_providers, timeout=timeout,
                             cache_ttl=cache_ttl, expect="")
        if loose.get("results"):
            loose["fallback"] = "loose-query"
            return loose
    return payload


_BILI_STATE = re.compile(r'bvid:"(BV[0-9A-Za-z]+)",title:"((?:[^"\\]|\\.)*)"')


def _unescape_js(text: str) -> str:
    """还原 JS 字符串里的 \\uXXXX 转义，再去掉搜索结果的高亮标签。"""
    fixed = re.sub(r"\\u([0-9a-fA-F]{4})", lambda m: chr(int(m.group(1), 16)), text or "")
    return re.sub(r"<[^>]+>", "", fixed).strip()


def parse_bilibili_videos(html: str) -> List[Dict]:
    """从 B 站搜索页的 SSR 数据里提取视频条目。

    页面把状态序列化在 `__pinia` 里，不是标准 JSON，但 bvid/title 成对出现，
    正则够用：比走通用搜索页可靠得多（通用搜索经常返回图文或无关推荐）。
    """
    out, seen = [], set()
    for bvid, raw_title in _BILI_STATE.findall(html or ""):
        if bvid in seen:
            continue
        title = _unescape_js(raw_title)
        if not title:
            continue
        seen.add(bvid)
        out.append({
            "title": title[:120],
            "url": f"https://www.bilibili.com/video/{bvid}",
            "site": "bilibili",
            "snippet": "",
        })
    return out


def search_videos(entity: str, limit: int = 3, timeout: float = 6.0,
                  cache_ttl: int = 1800) -> List[Dict]:
    """找知识点的视频讲解。

    优先解析 B 站搜索页的 SSR 数据（能拿到真实视频条目）；
    YouTube 搜索页需要 JS 渲染，只保留站内搜索直达（见 video_search_links）。
    """
    safe = (entity or "").replace('"', " ").strip()
    if not safe:
        return []

    cache_key = f"video::{safe}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    out, seen = [], set()
    html = _fetch(f"https://search.bilibili.com/all?keyword={urllib.parse.quote(safe)}",
                  timeout)
    for item in parse_bilibili_videos(html or ""):
        if item["url"] in seen:
            continue
        if not matches_entity(safe, {"title": item["title"]}):
            continue
        seen.add(item["url"])
        out.append(item)
        if len(out) >= limit:
            break

    _cache_put(cache_key, out, cache_ttl)
    return out


# 来源分级：官方文档 / 标准组织 > 技术社区 > 未知。
# 只用来判断「多源命中够不够硬」，不改变单条证据的方向。
SOURCE_TIERS = {
    "authority": (
        "wikipedia.org", "baike.baidu.com", "developer.mozilla.org",
        "python.org", "postgresql.org", "dev.mysql.com", "spring.io",
        "kubernetes.io", "vuejs.org", "react.dev", "nodejs.org",
        "w3.org", "ietf.org", "rfc-editor.org", "datatracker.ietf.org",
        "learn.microsoft.com", "docs.microsoft.com", "redis.io",
        "nginx.org", "docs.docker.com", "golang.org", "rust-lang.org",
        "openjdk.org", "docs.oracle.com", "tomcat.apache.org",
    ),
    "community": (
        "stackoverflow.com", "segmentfault.com", "zhihu.com", "juejin.cn",
        "csdn.net", "cnblogs.com", "github.com", "medium.com", "dev.to",
        "infoq.cn", "51cto.com", "jianshu.com", "oschina.net", "runoob.com",
    ),
}


def source_tier(url: str) -> str:
    """按域名给来源分级：authority / community / unknown。"""
    try:
        host = (urllib.parse.urlparse(url or "").hostname or "").lower()
    except ValueError:
        return "unknown"
    if host.startswith("www."):
        host = host[4:]
    if not host:
        return "unknown"
    for tier, domains in SOURCE_TIERS.items():
        if any(host == d or host.endswith("." + d) for d in domains):
            return tier
    return "unknown"


def evidence_sources(entity: str, evidence: List[Dict], limit: int = 5) -> List[Dict]:
    """从判定证据里提取可点击的来源。

    读取时再过滤一次：历史证据可能是搜索源限流时抓到的无关页，
    直接展示会让人点进垃圾页面。
    """
    out = []
    for ev in (evidence or []):
        if ev.get("type") != "web-sample":
            continue
        url = (ev.get("url") or "").strip()
        if not url:
            continue
        if not matches_entity(entity, {"title": ev.get("detail") or ""}):
            continue
        out.append({
            "title": (ev.get("detail") or "")[:100],
            "url": url,
            "provider": ev.get("source") or "",
            "tier": source_tier(url),
        })
    return out[:limit]


def reference_links(entity: str) -> List[Dict]:
    """百科/搜索直达链接。

    抓取搜索结果受反爬限流影响（同一 IP 连续请求会被喂无关推荐），
    但直达链接永远可用：百科条目页、站内搜索页都是稳定的落点。
    """
    name = (entity or "").strip()
    if not name:
        return []
    q = urllib.parse.quote(name)
    return [
        {"site": "baidu_baike", "title": f"百度百科：{name}",
         "url": f"https://baike.baidu.com/item/{q}"},
        {"site": "wikipedia", "title": f"维基百科：{name}",
         "url": f"https://zh.wikipedia.org/wiki/{q}"},
        {"site": "bing", "title": f"必应搜索「{name}」",
         "url": f"https://cn.bing.com/search?q={q}"},
    ]


def video_search_links(entity: str) -> List[Dict]:
    """视频站内搜索直达链接。

    各站的搜索结果页多为前端渲染，抓不到条目；这里直接给带关键词的
    站内搜索入口，保证「看视频讲解」这条路一定走得通。
    """
    name = (entity or "").strip()
    if not name:
        return []
    q = urllib.parse.quote(name)
    return [
        {"site": "bilibili", "title": f"在 B 站搜索「{name}」",
         "url": f"https://search.bilibili.com/all?keyword={q}", "type": "search"},
        {"site": "youtube", "title": f"在 YouTube 搜索「{name}」",
         "url": f"https://www.youtube.com/results?search_query={q}", "type": "search"},
        {"site": "douyin", "title": f"在抖音搜索「{name}」",
         "url": f"https://www.douyin.com/search/{q}", "type": "search"},
    ]


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
