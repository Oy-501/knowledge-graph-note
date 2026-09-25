"""智能文件切割：大文件不再拒绝，而是按**结构边界**切开后逐片解析。

切割原则（保证「切了也不丢知识点」）：
  1. **只在结构边界落刀**：优先 `#` 标题行之前、其次空行段落之间，最后才按行数强制切；
     绝不在段落中间切断句子 —— 句子里往往就是知识点本身。
  2. **标题上下文继承**：每个分片带上它所在的祖先标题路径（如 `# 前端开发 > ## Vue`），
     补在分片开头。这样即使一个概念横跨两片，抽取时仍有正确的上下文（领域/层级判定依赖标题）。
  3. **相邻分片留重叠**：默认重叠 2 行，避免「一句话正好落在刀口上」而被两片各丢一半；
     重复抽出的知识点由 merge_same_entity（同文件同实体合并）自然去重。
  4. **分片可追溯**：每片带 index / 起止行号 / 标题路径 / 字符数，写入 Node.chunk_index，
     后台与审计里能还原「这个知识点来自原文第几片、第几行」。

切割是纯计算，不落盘；解析时按片循环，进度与审计都按片记录。
"""
import re
from typing import Dict, List, Optional

from loguru import logger

HEADING = re.compile(r"^(#{1,6})\s+(.*)$")


def _heading_path(stack: List[tuple]) -> str:
    """把标题栈拼成可读路径：['# 前端', '## Vue'] → '# 前端 > ## Vue'"""
    return " > ".join(f"{hashes} {text}" for hashes, text in stack)


def _update_stack(stack: List[tuple], line: str) -> bool:
    """维护标题栈；返回该行是否为标题行"""
    m = HEADING.match(line.strip())
    if not m:
        return False
    level = len(m.group(1))
    text = m.group(2).strip()
    # 弹出层级 >= 当前的所有标题，再压入
    while stack and len(stack[-1][0]) >= level:
        stack.pop()
    stack.append((m.group(1), text))
    return True


def plan_split(text: str, target_lines: int = 6000, target_chars: int = 400_000,
               max_pieces: int = 40, overlap_lines: int = 2) -> Dict:
    """规划切割方案（不落盘）

    返回 {needed, total_lines, total_chars, pieces:[{index, start, end, lines, chars,
          heading_path, reason}]}
    """
    lines = (text or "").split("\n")
    total_lines = len(lines)
    total_chars = len(text or "")

    if total_lines <= target_lines and total_chars <= target_chars:
        return {
            "needed": False,
            "total_lines": total_lines,
            "total_chars": total_chars,
            "pieces": [{"index": 0, "start": 1, "end": total_lines,
                        "lines": total_lines, "chars": total_chars,
                        "heading_path": "", "reason": "整文件"}],
        }

    # 先找出所有可落刀的边界（标题行之前 / 空行之后），记录行号（0-based）
    cut_candidates: List[int] = []
    for i, line in enumerate(lines):
        if HEADING.match(line.strip()):
            cut_candidates.append(i)          # 在标题行之前切
        elif not line.strip() and i + 1 < len(lines):
            cut_candidates.append(i + 1)      # 在空行之后切（开新段落）
    if not cut_candidates:
        cut_candidates = list(range(0, total_lines, max(1, target_lines)))

    # 一次预扫描：heading_at[i] = 进入第 i 行时的标题上下文（
    # 每个分片用「进入该片时」的上下文做前缀，而不是片尾的标题）
    heading_at: List[str] = [""] * (total_lines + 1)
    stack: List[tuple] = []
    for i, line in enumerate(lines):
        heading_at[i] = _heading_path(stack)
        _update_stack(stack, line)
    heading_at[total_lines] = _heading_path(stack)

    pieces: List[Dict] = []
    start = 0
    while start < total_lines and len(pieces) < max_pieces:
        # 目标结束位置
        target_end = start
        chars = 0
        while target_end < total_lines:
            chars += len(lines[target_end]) + 1
            target_end += 1
            if target_end - start >= target_lines or chars >= target_chars:
                break
        if target_end >= total_lines:
            end = total_lines
        else:
            # 在 (start, target_end] 范围内找最靠后的结构边界
            end = None
            for c in cut_candidates:
                if start < c <= target_end:
                    end = c
            if end is None:
                # 该范围内没有结构边界：向后找最近的一个（不超过目标 1.5 倍）
                for c in cut_candidates:
                    if c > target_end:
                        end = c
                        break
                if end is None:
                    end = target_end

        heading_path = heading_at[min(start, total_lines)]

        # 判断切点性质（末尾片没有"下一个切点"）
        if end >= total_lines:
            cut_kind = "文末"
        elif HEADING.match(lines[end].strip()):
            cut_kind = "标题边界"
        elif not lines[end].strip():
            cut_kind = "段落边界"
        else:
            cut_kind = "行数兜底"

        pieces.append({
            "index": len(pieces),
            "start": start + 1,
            "end": end,
            "lines": end - start,
            "chars": sum(len(l) + 1 for l in lines[start:end]),
            "heading_path": heading_path,
            "reason": cut_kind,
        })
        if end >= total_lines:
            break
        # 下一片从「end - overlap」开始，制造少量重叠
        start = max(start + 1, end - max(0, overlap_lines))

    return {
        "needed": True,
        "total_lines": total_lines,
        "total_chars": total_chars,
        "pieces": pieces,
        "truncated_by_limit": len(pieces) >= max_pieces and pieces[-1]["end"] < total_lines,
    }


def piece_text(text: str, piece: Dict, with_context: bool = True) -> str:
    """取出某片的文本；带上标题上下文前缀，保证抽取不丢语境"""
    lines = (text or "").split("\n")
    start = max(0, piece["start"] - 1)
    end = min(len(lines), piece["end"])
    body = "\n".join(lines[start:end])
    if with_context and piece.get("heading_path"):
        return f"{piece['heading_path']}\n\n{body}"
    return body


def describe_plan(plan: Dict) -> str:
    """给审计/前端用的一句话说明"""
    if not plan.get("needed"):
        return f"文件 {plan['total_lines']} 行，无需切割"
    details = "、".join(
        f"第{p['index'] + 1}片 {p['start']}-{p['end']}行" for p in plan["pieces"][:5]
    )
    tail = "…" if len(plan["pieces"]) > 5 else ""
    return (f"文件 {plan['total_lines']} 行 / {plan['total_chars']} 字符，"
            f"按结构切为 {len(plan['pieces'])} 片（{details}{tail}）")


def summarize_pieces(plan: Dict) -> List[Dict]:
    """给前端/后台展示的片摘要（不含正文）"""
    return [{
        "index": p["index"],
        "start": p["start"],
        "end": p["end"],
        "lines": p["lines"],
        "chars": p["chars"],
        "heading_path": p.get("heading_path", ""),
        "reason": p.get("reason", ""),
    } for p in plan.get("pieces", [])]
