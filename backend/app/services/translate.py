"""英译中：MyMemory 免费接口 + 本地缓存。

没有 API Key 的兜底方案。匿名额度有限，所以结果落盘缓存，
同一句话只翻一次；任何失败都返回原文，不阻断主流程。

免费接口会把技术名词当普通词硬译（web.dev → 测长仪顶杆），
所以术语先遮成占位符、品牌名直接不译、译文跑偏就回退原文。
"""
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import List

from loguru import logger

CACHE_PATH = Path(__file__).resolve().parents[2] / ".translate_cache.json"
OVERRIDES_PATH = (Path(__file__).resolve().parents[3]
                  / "domain_corpus" / "learn_anything" / "zh_overrides.json")
API = "https://api.mymemory.translated.net/get"


def _overrides() -> dict:
    """人工校订优先：免费机翻对技术标题不可靠，校订表是质量基线。"""
    try:
        return json.loads(OVERRIDES_PATH.read_text(encoding="utf-8")).get("items") or {}
    except (OSError, ValueError):
        return {}


def _is_chinese(text: str) -> bool:
    """中文字符占比够高就不再翻译。"""
    if not text:
        return False
    chinese = sum(1 for ch in text if "\u4e00" <= ch <= "\u9fff")
    return chinese / max(len(text), 1) > 0.25


def _load_cache() -> dict:
    try:
        return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _save_cache(cache: dict) -> None:
    try:
        CACHE_PATH.write_text(json.dumps(cache, ensure_ascii=False, indent=0),
                              encoding="utf-8")
    except OSError as exc:
        logger.debug(f"翻译缓存写入失败：{exc}")


def translate(text: str, source: str = "en", target: str = "zh-CN") -> str:
    """翻译单条；失败或已是中文时返回原文。

    通道顺序：本地 MarianMT 模型 → MyMemory → 原文。
    本地模型优先，因为在线通道要么不可达、要么返回值不可信。
    """
    text = (text or "").strip()
    if not text or _is_chinese(text):
        return text

    key = f"local::{source}->{target}:{text}"
    cache = _load_cache()
    if key in cache:
        return cache[key]

    if source == "en" and target.startswith("zh"):
        from app.services import translation_engine
        local = translation_engine.translate(text)
        if local:
            cache[key] = local
            _save_cache(cache)
            return local

    url = f"{API}?" + urllib.parse.urlencode({
        "q": text[:480], "langpair": f"{source}|{target}",
    })
    try:
        with urllib.request.urlopen(url, timeout=8) as resp:
            data = json.load(resp)
        out = ((data.get("responseData") or {}).get("translatedText") or "").strip()
        if data.get("responseStatus") != 200 or not out:
            return text
        cache[key] = out
        _save_cache(cache)
        return out
    except (urllib.error.URLError, ValueError, OSError) as exc:
        logger.debug(f"翻译失败（保留原文）：{exc}")
        return text


def translate_many(items: List[dict], field: str = "title") -> List[dict]:
    """批量翻译某个字段，结果写在 `{field}_zh`。"""
    out = []
    for item in items:
        row = dict(item)
        row[f"{field}_zh"] = translate_title(item.get(field, ""), item.get("domain", ""))
        out.append(row)
    return out


_BRAND = re.compile(r"^[a-z0-9-]+(\.[a-z0-9-]+)+$", re.I)   # 必须带点，才算域名形态
_EN_WORD = re.compile(r"[A-Za-z][A-Za-z0-9.+-]{1,}")


def _stray_english(source: str, out: str) -> list:
    """译文里出现原文没有的英文词，基本可以断定命中了无关的翻译记忆。

    实例：'Hands-on with Portals...' 被译成 'Diskeeper 2008 实际操作'。
    """
    src = source.lower()
    return [w for w in _EN_WORD.findall(out) if w.lower() not in src]


def translate_title(text: str, domain: str = "") -> str:
    """标题翻译：品牌名不译，译文可疑就回退原文。

    免费接口没有质量保证，因此用三条闸门过滤：品牌/域名类标题不译、
    长度比例异常回退、译文夹带原文没有的英文词回退。
    """
    text = (text or "").strip()
    if not text or _is_chinese(text):
        return text

    fixed = _overrides().get(text)
    if fixed:
        return fixed

    # 标题本身就是域名/品牌（web.dev 曾被译成「测长仪顶杆」）
    brand = (domain or "").split("/")[0].replace("www.", "").lower()
    flat = text.lower().replace(" ", "")
    if brand and (flat == brand or _BRAND.match(flat)):
        return text

    out = translate(text)
    if not out or out == text:
        return text
    ratio = len(out) / max(len(text), 1)
    if ratio < 0.2 or ratio > 3.0:
        return text
    if _stray_english(text, out):
        return text
    return out
