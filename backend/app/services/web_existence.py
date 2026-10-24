"""知识点存在性确认：把一次公开检索的结果判成可执行的存在性状态。

与 web_probe.py 的分工：web_probe 负责「抓」，这里负责「判」。
判据刻意保守 —— 搜不到不算不存在，只有多源精确命中才算确认，
只有强否定措辞才算矛盾。
"""
import re
from typing import Dict, List

from app.config import settings

_SPACE = re.compile(r"\s+")
_ASCII = re.compile(r"[a-z]")
# 只收强否定措辞。「不是 / 并非 / 错误」会误伤定义句与技术词，刻意不收。
_STRONG_NEG = r"(不存在|并不存在|并无此|纯属虚构|属于谣言|是谣言|不实信息|误传)"


def _norm(text: str) -> str:
    """去空白并转小写，用于精确匹配。"""
    return _SPACE.sub("", (text or "").lower())


def _domain(url: str) -> str:
    """从 URL 提取域名。"""
    m = re.match(r"^https?://([^/]+)", (url or "").lower())
    if not m:
        return ""
    host = m.group(1).split(":")[0]
    return host[4:] if host.startswith("www.") else host


def _exact_hit(term: str, text: str) -> bool:
    """精确命中：英文按词边界，中文按子串（中文没有空格可依）。"""
    if not term or not text:
        return False
    if _ASCII.search(term):
        pattern = r"(?<![a-z0-9])" + re.escape(term) + r"(?![a-z0-9])"
        return bool(re.search(pattern, text))
    return term in text


def _bigrams(text: str) -> set:
    """生成字符二元组。"""
    clean = _norm(text)
    if len(clean) < 2:
        return {clean} if clean else set()
    return {clean[i:i + 2] for i in range(len(clean) - 1)}


def _description_coverage(description: str, hits: List[Dict]) -> float:
    """描述里的二元组，有多少出现在命中摘要中（取最好的那一条）。"""
    want = _bigrams(description)
    if not want:
        return 0.0
    best = 0.0
    for row in hits:
        got = _bigrams(f"{row.get('title', '')} {row.get('snippet', '')}")
        if got:
            best = max(best, len(want & got) / len(want))
    return best


def _contradicted(term: str, hits: List[Dict]) -> bool:
    """强否定措辞紧邻实体才算矛盾，避免把定义句判成否定。"""
    for row in hits:
        text = _norm(f"{row.get('title', '')} {row.get('snippet', '')}")
        if re.search(re.escape(term) + r".{0,4}" + _STRONG_NEG, text):
            return True
        if re.search(_STRONG_NEG + r".{0,4}" + re.escape(term), text):
            return True
    return False


def _result(status: str, confidence: float, exact_hits: int, domains: List[str],
            consistency: float, contradicted: bool, reason: str) -> Dict:
    """组装存在性判定结果。"""
    return {
        "status": status,
        "confidence": round(confidence, 3),
        "exact_hits": exact_hits,
        "domains": domains,
        "consistency": round(consistency, 3),
        "contradicted": contradicted,
        "reason": reason,
    }


def check_existence(entity: str, description: str, search_result: Dict) -> Dict:
    """判定知识点是否真实存在。

    status:
      unavailable  联网不可用，中性
      unverified   联网成功但没有足够精确命中，中性
      probable     有多源命中，但描述一致性不足
      confirmed    多源精确命中，且描述与检索摘要一致
      contradicted 出现强否定证据
    """
    if not search_result or not search_result.get("online"):
        return _result("unavailable", 0.0, 0, [], 0.0, False,
                       "联网不可用，未做存在性确认（不构成负面证据）")

    term = _norm(entity)
    if len(term) < 2:
        return _result("unverified", 0.0, 0, [], 0.0, False,
                       "名称过短，无法做可靠的联网确认")

    hits = []
    for row in search_result.get("results") or []:
        text = _norm(f"{row.get('title', '')} {row.get('snippet', '')}")
        if _exact_hit(term, text):
            hits.append(row)

    domains = sorted({d for d in (_domain(r.get("url", "")) for r in hits) if d})
    consistency = _description_coverage(description, hits)

    if not hits:
        return _result("unverified", 0.0, 0, [], 0.0, False,
                       "公开检索未精确命中该概念，不构成负面证据，交给人工判断")

    if _contradicted(term, hits):
        return _result("contradicted", 0.0, len(hits), domains, consistency, True,
                       f"检索结果出现否定该概念的措辞（{len(hits)} 条命中），需人工核实")

    min_domains = max(1, int(settings.VERDICT_WEB_MIN_DOMAINS))
    if description:
        confirmed = (len(domains) >= min_domains
                     and consistency >= settings.VERDICT_WEB_DESC_CONSISTENCY)
    else:
        # 没有描述可对照时，要求更多独立来源，避免单站多页被当成多源
        confirmed = len(domains) >= max(3, min_domains)

    if confirmed:
        status = "confirmed"
        reason = (f"{len(domains)} 个独立来源精确命中，描述与检索摘要一致"
                  f"（相似度 {consistency:.2f}）")
    elif len(domains) >= min_domains or (description and consistency >= 0.5):
        status = "probable"
        reason = f"{len(domains)} 个独立来源命中，但描述一致性不足（{consistency:.2f}）"
    else:
        status = "unverified"
        reason = f"仅 {len(domains) or 1} 个来源命中，不足以确认存在"

    confidence = min(1.0, 0.35 * min(len(domains), 3) / 3
                     + 0.35 * consistency
                     + 0.30 * min(len(hits), 3) / 3)
    return _result(status, confidence, len(hits), domains, consistency, False, reason)
