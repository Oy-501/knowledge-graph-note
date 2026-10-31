"""知识点存在性确认：把一次公开检索的结果判成可执行的存在性状态。

与 web_probe.py 的分工：web_probe 负责「抓」，这里负责「判」。
判据刻意保守 —— 搜不到不算不存在，只有多源精确命中才算确认，
只有强否定措辞才算矛盾。
"""
import re
from typing import Dict, List

from app.config import settings
from app.services.web_probe import source_tier

_SPACE = re.compile(r"\s+")
_ASCII = re.compile(r"[a-z]")

# 域名级票权：一个独立域名一票，按来源级别加权。
# 之前按「命中条数」统计级别，同一网站的多篇文章会被当成多个独立来源；
# 改为按域名去重后，多源确认才是真的多源（Knowledge Vault 的源池也是网页粒度）。
# 用整数是为了避免 0.6×3 = 1.7999… 这类浮点比较失误。
DOMAIN_WEIGHT = {"authority": 10, "community": 6, "unknown": 2}
VOTE_SCALE = 10              # 票权 → 展示用的小数（10 分 = 1.0 票）
CONFIRM_SUPPORT = 12         # ≈ 两个社区源，或一个权威源加一个弱源
CONFIRM_SUPPORT_NO_DESC = 18  # 没有描述可对照时要求更高
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


_TERM_SPLIT = re.compile(r"[\s/·,，、()（）]+")


def _partial_hit(term: str, text: str) -> bool:
    """部分命中：拆词后至少两段出现，且覆盖一半以上。

    复合术语（Last-Modified 与 If-Modified-Since）几乎不会整串出现在页面上，
    页面上是拆开讲的。只认整串等于直接放弃这类概念。
    单段术语不走这里，避免「注入」这种泛词命中一堆无关页。
    """
    parts = [p for p in _TERM_SPLIT.split(term or "") if len(_norm(p)) >= 2]
    if len(parts) < 2:
        return False
    hit = sum(1 for p in parts if _norm(p) in text)
    return hit >= 2 and hit / len(parts) >= 0.5


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


def domain_votes(hits: List[Dict]) -> List[Dict]:
    """每个域名一票；同站多页只算一票，级别取该站最高的那篇。"""
    best: Dict[str, Dict] = {}
    for row in hits:
        domain = _domain(row.get("url", ""))
        if not domain:
            continue
        tier = source_tier(row.get("url", ""))
        weight = DOMAIN_WEIGHT.get(tier, DOMAIN_WEIGHT["unknown"])
        current = best.get(domain)
        if current is None:
            best[domain] = {"domain": domain, "tier": tier, "weight": weight, "hits": 1}
        else:
            current["hits"] += 1
            if weight > current["weight"]:
                current["weight"] = weight
                current["tier"] = tier
    return sorted(best.values(), key=lambda item: -item["weight"])


def _attach(result: Dict, votes: List[Dict], support: int = 0) -> Dict:
    """把域名级票挂到结果上；下游判定与真值发现都用这份明细。"""
    tiers = {"authority": 0, "community": 0, "unknown": 0}
    for vote in votes:
        tiers[vote["tier"]] += 1
    result["tiers"] = tiers
    result["votes"] = votes
    result["support"] = round(support / VOTE_SCALE, 2)
    return result


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
        return _attach(_result("unavailable", 0.0, 0, [], 0.0, False,
                               "联网不可用，未做存在性确认（不构成负面证据）"), [], 0)

    term = _norm(entity)
    if len(term) < 2:
        return _attach(_result("unverified", 0.0, 0, [], 0.0, False,
                               "名称过短，无法做可靠的联网确认"), [], 0)

    hits, partial = [], []
    for row in search_result.get("results") or []:
        text = _norm(f"{row.get('title', '')} {row.get('snippet', '')}")
        if _exact_hit(term, text):
            hits.append(row)
        elif _partial_hit(term, text):
            partial.append(row)

    domains = sorted({d for d in (_domain(r.get("url", "")) for r in hits) if d})
    consistency = _description_coverage(description, hits)

    # 域名级计票：一个独立域名一票，按来源级别加权
    votes = domain_votes(hits)
    support = sum(v["weight"] for v in votes)
    tier_note = (f"权威 {sum(1 for v in votes if v['tier'] == 'authority')} / "
                 f"社区 {sum(1 for v in votes if v['tier'] == 'community')} / "
                 f"未知 {sum(1 for v in votes if v['tier'] == 'unknown')}")

    if not hits:
        if not partial:
            return _attach(_result("unverified", 0.0, 0, [], 0.0, False,
                                   "公开检索未精确命中该概念，不构成负面证据，交给人工判断"),
                           [], 0)
        # 只有部分命中：弱证据，票权减半、级别记 unknown，最高只给 probable。
        # 精确命中的确认语义（confirmed）不向部分命中开放。
        weak = domain_votes(partial)
        for vote in weak:
            vote["weight"] = max(1, vote["weight"] // 2)
        support = sum(v["weight"] for v in weak)
        return _attach(
            _result("probable", 0.3, 0,
                    sorted({v["domain"] for v in weak}), 0.0, False,
                    f"{len(weak)} 个域名部分命中（术语未完整出现），"
                    f"{support / VOTE_SCALE:.2f} 票，建议人工核实"),
            weak, support)

    if _contradicted(term, hits):
        return _attach(_result("contradicted", 0.0, len(hits), domains, consistency, True,
                               f"检索结果出现否定该概念的措辞（{len(hits)} 条命中），需人工核实"),
                       votes, support)

    min_domains = max(1, int(settings.VERDICT_WEB_MIN_DOMAINS))
    if description:
        confirmed = (support >= CONFIRM_SUPPORT
                     and consistency >= settings.VERDICT_WEB_DESC_CONSISTENCY)
    else:
        # 没有描述可对照时，要求更多独立来源，避免单站多页被当成多源
        confirmed = support >= CONFIRM_SUPPORT_NO_DESC

    if confirmed:
        status = "confirmed"
        reason = (f"{len(votes)} 个独立域名精确命中（{tier_note}，"
                  f"{support / VOTE_SCALE:.2f} 票），"
                  f"描述与检索摘要一致（相似度 {consistency:.2f}）")
    elif len(domains) >= min_domains or (description and consistency >= 0.5):
        status = "probable"
        reason = (f"{len(votes)} 个独立域名命中（{tier_note}，"
                  f"{support / VOTE_SCALE:.2f} 票），"
                  f"但描述一致性不足（{consistency:.2f}）")
        if support < CONFIRM_SUPPORT:
            reason += "；多源支持不足"
    else:
        status = "unverified"
        reason = (f"仅 {len(votes) or 1} 个来源命中（{support / VOTE_SCALE:.2f} 票），"
                  f"不足以确认存在")

    confidence = min(1.0, 0.35 * min(support / VOTE_SCALE, 3.0) / 3
                     + 0.35 * consistency
                     + 0.30 * min(len(hits), 3) / 3)
    return _attach(
        _result(status, confidence, len(hits), domains, consistency, False, reason),
        votes, support)
