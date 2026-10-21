"""抽取式文本摘要：选代表句，不依赖大模型。

流程：按行判角色（只取正文）→ 分句 → 词频与位置打分 → 选 topN → 按原序拼接。
摘要句全部来自原文，可逐句回溯。
"""
import re
from collections import Counter
from typing import Dict, List

from app.services.text_role import line_role

_SENT = re.compile(r"[^。！？；!?;\n]+[。！？；!?;]?")
_WORD = re.compile(r"[a-z][a-z0-9\-]{1,}")
_CJK = re.compile(r"[\u4e00-\u9fff]+")


def split_sentences(text: str) -> List[str]:
    return [s.strip() for s in _SENT.findall(text or "") if s.strip()]


def _tokens(text: str) -> List[str]:
    low = (text or "").lower()
    out = _WORD.findall(low)
    for seg in _CJK.findall(low):
        if len(seg) >= 2:
            out += [seg[i:i + 2] for i in range(len(seg) - 1)]
    return out


def _body_sentences(text: str) -> List[str]:
    lines = (text or "").split("\n")
    out: List[str] = []
    for i, line in enumerate(lines):
        nxt = lines[i + 1] if i + 1 < len(lines) else ""
        if line_role(line, nxt) != "body":
            continue
        out += split_sentences(line)
    return out


def summarize(text: str, max_sentences: int = 5, max_chars: int = 600) -> Dict:
    """返回 summary / key_points / keywords / sentence_count / source_chars。"""
    body = _body_sentences(text)
    if not body:
        return {"summary": "", "key_points": [], "keywords": [],
                "sentence_count": 0, "source_chars": len(text or "")}

    tf = Counter(t for s in body for t in _tokens(s))
    head = max(1, len(body) // 5)
    scored = []
    for idx, sent in enumerate(body):
        toks = _tokens(sent)
        if not toks:
            continue
        score = sum(tf[t] for t in toks) / (len(toks) ** 0.5)
        if idx < head:
            score *= 1.3   # 首段通常是定义/结论
        scored.append((score, idx, sent))

    top = sorted(scored, key=lambda x: x[0], reverse=True)[:max_sentences]
    top.sort(key=lambda x: x[1])

    picked: List[str] = []
    used = 0
    for _, _, sent in top:
        if picked and used + len(sent) > max_chars:
            break
        picked.append(sent)
        used += len(sent)

    return {
        "summary": "".join(picked),
        "key_points": picked,
        "keywords": [w for w, _ in tf.most_common(8)],
        "sentence_count": len(body),
        "source_chars": len(text or ""),
    }
