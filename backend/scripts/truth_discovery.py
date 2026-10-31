"""真值发现原型：用源间一致性估计权重，替代手写常量。

文献依据：
  Li et al. (2016) A Survey on Truth Discovery —— 源可靠性与真值互估，
  不是计数投票；Dong et al. (2009) 指出源间存在依赖时多数投票失效。

与现行逻辑的差别：
  现行  score = Σ 固定权重（0.25/0.30/0.15/0.08），知识库缺席时该项记 −0.05，
        导致「没有知识库命中」的概念分数上限 0.73，永远够不到 0.80。
  本原型  每个源只有「支持 / 反对 / 未表态」三种态度，未表态不拉分；
        源权重由它与其他源的一致程度迭代得出。

用法：
  py scripts/truth_discovery.py --rounds 8
"""
import argparse
import json
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
ROOT = BACKEND.parent
SAMPLE = ROOT / "docs" / "threshold_experiment" / "sample.json"
LABELS = ROOT / "docs" / "threshold_experiment" / "labels.json"

sys.path.insert(0, str(BACKEND))

SOURCES = ("rule", "kb", "graph", "web")


def votes(evidence: list) -> dict:
    """证据 → 每个源的态度。多条同源证据按符号累加后再取号。

    知识库「未收录」的 −0.05 是弃权，不是反对：它没有否定这条知识，
    只是没有表态。编码成 −1 会让知识库被误判成不可靠源（实测权重从
    41% 掉到 34%），这是语义错位。
    """
    raw = {s: 0 for s in SOURCES}
    for e in evidence:
        kind = (e.get("type") or "")
        key = "web" if kind.startswith("web") else kind
        if key not in raw:
            continue
        weight = e.get("weight") or 0
        if key == "kb" and -0.1 < weight < 0:
            continue          # 未命中 → 弃权
        raw[key] += 1 if weight > 0 else (-1 if weight < 0 else 0)
    return {s: (1 if v > 0 else (-1 if v < 0 else 0)) for s, v in raw.items()}


def dependence(matrix: dict, sources: list) -> dict:
    """源间一致率。两个源几乎总是同向时，它们提供的是同一份信息。

    这是 Dong et al. (2009) 指出的源依赖：把相关源当独立源重复计分，
    会虚高真值。这里只做诊断，不改权重，避免在小样本上过度修正。
    """
    out = {}
    ids = list(matrix)
    for i, a in enumerate(sources):
        for b in sources[i + 1:]:
            both = [(matrix[r].get(a, 0), matrix[r].get(b, 0)) for r in ids
                    if matrix[r].get(a, 0) and matrix[r].get(b, 0)]
            if len(both) < 3:
                continue
            same = sum(1 for x, y in both if x == y)
            out[f"{a}-{b}"] = (same / len(both), len(both))
    return out


def votes_domain_level(evidence: list) -> dict:
    """域名级源：rule/kb/graph 各一票，联网按域名拆成多票。

    这是「扩充独立源」的落地形态——一次检索命中 4 个站点，
    对真值发现来说就是 4 个独立源，而不是 1 个 web 源。
    """
    out = {}
    for e in evidence:
        kind = e.get("type") or ""
        if kind == "web-votes":
            for v in (e.get("votes") or []):
                out[f"web:{v.get('domain') or '?'}"] = 1
            continue
        if kind not in ("rule", "kb", "graph"):
            continue
        weight = e.get("weight") or 0
        if kind == "kb" and -0.1 < weight < 0:
            continue
        out[kind] = 1 if weight > 0 else (-1 if weight < 0 else 0)
    return out


def run(matrix: dict, rounds: int) -> tuple:
    """迭代：真值 = 加权投票；权重 = 与当前真值的一致度。源集合自动从数据里取。"""
    sources = sorted({s for votes_map in matrix.values() for s in votes_map})
    weight = {s: 1.0 for s in sources}
    truth = {rid: 0.0 for rid in matrix}

    for _ in range(rounds):
        for rid, votes_map in matrix.items():
            num = sum(weight[s] * votes_map.get(s, 0) for s in sources)
            den = sum(weight[s] for s in sources if votes_map.get(s, 0) != 0)
            truth[rid] = num / den if den else 0.0

        updated = {}
        for s in sources:
            diffs = [abs(truth[rid] - votes_map[s]) for rid, votes_map in matrix.items()
                     if votes_map.get(s, 0) != 0]
            # 一致度映射到 0.5~1.0，避免某源被一次判错直接归零
            updated[s] = 1 - (sum(diffs) / len(diffs)) / 2 if diffs else 0.5
        weight = updated

    return weight, truth


def evaluate(truth: dict, labels: dict, threshold: float) -> tuple:
    accepted = [rid for rid, score in truth.items() if (score + 1) / 2 >= threshold]
    positives = [rid for rid, lab in labels.items() if lab]
    tp = sum(1 for rid in accepted if labels[rid])
    precision = tp / len(accepted) if accepted else 0.0
    recall = tp / len(positives) if positives else 0.0
    return len(accepted), precision, recall


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rounds", type=int, default=8)
    parser.add_argument("--domain-level", action="store_true",
                        help="联网按域名拆成多个源（扩充独立源）")
    args = parser.parse_args()
    votes_fn = votes_domain_level if args.domain_level else votes

    samples = json.loads(SAMPLE.read_text(encoding="utf-8"))
    labels_raw = json.loads(LABELS.read_text(encoding="utf-8"))
    labels = {int(k): v for k, v in labels_raw.items() if str(k).isdigit()}

    from app.database import SessionLocal
    from app.models.models import KnowledgeCandidate

    db = SessionLocal()
    matrix, meta = {}, {}
    try:
        for s in samples:
            cand = db.get(KnowledgeCandidate, s["id"])
            if not cand:
                continue
            ev = cand.verdict_evidence
            ev = json.loads(ev) if isinstance(ev, str) else (ev or [])
            matrix[s["id"]] = votes_fn(ev)
            meta[s["id"]] = (cand.entity, s["stored_score"], votes_fn(ev))
    finally:
        db.close()

    weight, truth = run(matrix, args.rounds)

    sources_used = sorted({s for votes_map in matrix.values() for s in votes_map})
    active = sum(sum(1 for v in votes_map.values() if v != 0) for votes_map in matrix.values())
    print(f"样本 {len(matrix)} 条，迭代 {args.rounds} 轮，"
          f"源 {len(sources_used)} 个，平均表态源数 {active / max(len(matrix), 1):.2f}\n")

    fixed = {"rule": 0.48, "kb": 0.55, "graph": 0.15, "web": 0.15}
    total_fixed = sum(fixed.values())
    print("权重对照（手写 vs 迭代）：")
    for s in sources_used:
        base = fixed.get(s.split(":")[0], 0.15)
        shown = f"手写占比 {base/total_fixed:>6.1%}" if not s.startswith("web:") else "  （拆自联网）"
        print(f"  {s:<24} {shown}   迭代权重 {weight[s]:.3f}")

    print("\n源依赖（一致率接近 100% 说明两个源给的是同一份信息）：")
    dep = dependence(matrix, sources_used)
    if not dep:
        print("  样本不足以估计（共同投票少于 3 条）")
    for pair, (rate, n) in sorted(dep.items(), key=lambda kv: -kv[1][0])[:6]:
        print(f"  {pair:<28} 一致率 {rate:>4.0%}（{n} 条共同投票）"
              + ("  ← 视为同源" if rate >= 0.9 else ""))

    print(f"\n{'阈值':<8}{'采纳':>6}{'精确率':>9}{'召回率':>8}")
    for th in (0.50, 0.55, 0.60, 0.65):
        n, p, r = evaluate(truth, labels, th)
        print(f"{th:<8}{n:>6}{p:>9.0%}{r:>8.0%}")

    print("\n逐条（真值 → 归一化 0~1）：")
    for rid, (entity, stored, votes_map) in sorted(meta.items(), key=lambda kv: -truth[kv[0]]):
        norm = (truth[rid] + 1) / 2
        mark = "真" if labels.get(rid) else "假"
        brief = " ".join(f"{k}{v:+d}" for k, v in sorted(votes_map.items()) if v != 0)
        print(f"  {norm:.2f} [{mark}] 原分{stored:.2f}  {brief[:46]:<46} {entity[:26]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
