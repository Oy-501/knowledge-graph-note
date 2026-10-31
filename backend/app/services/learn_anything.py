"""Learn Anything 主题资源：把离线抓取的语料接到知识点上。

语料由 scripts/la_import.py 生成（浏览器渲染后提取），本模块只读本地文件，
不联网、不启动浏览器，所以可以安全地挂在详情接口上。
"""
import json
from pathlib import Path
from typing import Dict, List

from app.services.web_probe import source_tier

CORPUS_DIR = Path(__file__).resolve().parents[3] / "domain_corpus" / "learn_anything"

# 主题 → 命中关键词。领域名对不上时用它兜底。
TOPIC_KEYWORDS = {
    "web": ("web", "前端", "html", "css", "javascript", "浏览器", "http", "dom",
            "网页", "react", "vue", "接口", "缓存"),
    "math": ("数学", "math", "代数", "微积分", "几何", "概率", "统计", "线性"),
    "programming": ("编程", "程序", "python", "java", "算法", "数据结构", "并发",
                    "测试", "单元", "重构", "代码"),
}


def _load(topic: str) -> Dict:
    try:
        return json.loads((CORPUS_DIR / f"{topic}.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def available_topics() -> List[str]:
    return sorted(p.stem for p in CORPUS_DIR.glob("*.json") if p.stem != "zh_overrides")


def _score(topic: str, text: str, domain: str) -> int:
    """题目相关度：领域名直接命中记高分，关键词命中各记 1 分。"""
    score = 0
    if domain and domain.lower() == topic:
        score += 5
    low = (text or "").lower()
    for word in TOPIC_KEYWORDS.get(topic, ()):
        if word in low or word in (domain or "").lower():
            score += 1
    return score


def reading_for(entity: str, domain: str = "", limit: int = 5) -> List[Dict]:
    """给知识点挑一条主题下的延伸资源；没有合适主题就返回空。

    宁可返回空也不硬塞：把「数学」的资源挂到「HTTP 缓存」上只会让人困惑。
    """
    topics = available_topics()
    if not topics:
        return []

    best, best_score = "", 0
    for topic in topics:
        score = _score(topic, entity, domain)
        if score > best_score:
            best, best_score = topic, score

    if not best or best_score < 1:
        return []

    data = _load(best)
    items = data.get("items") or []
    out = []
    for item in items[:limit]:
        url = item.get("url") or ""
        if not url:
            continue
        out.append({
            "title": item.get("title") or "",
            "title_zh": item.get("title_zh") or item.get("title") or "",
            "url": url,
            "domain": item.get("domain") or "",
            "tier": source_tier(url),
            "topic": best,
        })
    return out
