"""阈值实验：知识库未命中的候选，在不同评分口径下会不会被采纳。

背景（见 docs/阈值实验.md）：现行权重下，无知识库命中的候选分数上限 0.73，
低于采纳阈值 0.80 —— 这类概念在数学上不可能自动通过。本脚本用真实候选
回放四种口径，并用人工标注衡量各自的精确率。

用法：
    py scripts/recall_experiment.py --sample 30     # 分层抽样 + 输出待标注清单
    py scripts/recall_experiment.py --report        # 读标注算指标
"""
import argparse
import json
import random
import statistics
import sys
from collections import Counter
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
ROOT = BACKEND.parent
WORK = ROOT / "docs" / "threshold_experiment"
SAMPLE_PATH = WORK / "sample.json"
LABEL_PATH = WORK / "labels.json"

sys.path.insert(0, str(BACKEND))

# 各维度满分（取自 knowledge_verifier.py 的权重定义）
MAX_RULE = 0.48      # 0.25 + 0.08 + 0.10 + 0.05
MAX_GRAPH = 0.15     # 0.10 + 0.05
MAX_WEB = 0.15       # confirmed 上限
MAX_KB = 0.55        # 0.30 + 0.15 + 0.10
THRESHOLD = 0.80
LOWERED = 0.70

BANDS = [(0.40, 0.45), (0.45, 0.50), (0.50, 0.55), (0.55, 0.62)]


def _evidence(raw) -> list:
    try:
        ev = json.loads(raw) if isinstance(raw, str) else (raw or [])
        return ev if isinstance(ev, list) else []
    except ValueError:
        return []


def kb_hit(ev: list) -> bool:
    return any(e.get("type") == "kb" and e.get("weight", 0) >= 0.30 for e in ev)


def variants(ev: list, base: float) -> dict:
    """四种口径的分数。

    A 现行      ：原分，阈值 0.80
    B 归一化    ：知识库缺失时按剩余维度满分（0.78）折算到 0~1
    C 降阈值    ：原分，阈值 0.70
    D 归一化+降阈值
    """
    cap = MAX_RULE + MAX_GRAPH + MAX_WEB + (MAX_KB if kb_hit(ev) else 0)
    norm = min(1.0, base / cap) if cap else 0.0
    return {
        "A": round(base, 3),
        "B": round(norm, 3),
        "C": round(base, 3),
        "D": round(norm, 3),
    }


def decide(v: dict) -> dict:
    return {
        "A": v["A"] >= THRESHOLD,
        "B": v["B"] >= THRESHOLD,
        "C": v["C"] >= LOWERED,
        "D": v["D"] >= LOWERED,
    }


def do_sample(limit: int) -> int:
    from app.database import SessionLocal
    from app.models.models import KnowledgeCandidate
    from app.services.web_existence import check_existence
    from app.services import web_probe

    db = SessionLocal()
    rows = []
    try:
        # 压测产生的「测试概念N」不是真实语料，混进来会污染结论
        cands = (db.query(KnowledgeCandidate)
                 .filter(KnowledgeCandidate.verdict_score.isnot(None))
                 .filter(~KnowledgeCandidate.entity.like("测试概念%"))
                 .all())
        real = [c for c in cands if not kb_hit(_evidence(c.verdict_evidence))]

        # 同一份文档被多次上传会产生完全重复的候选，按实体去重，
        # 否则「60 条样本」其实是 19 个概念重复计数，指标会被放大
        seen, dedup = set(), []
        for c in real:
            key = (c.entity or "").strip().lower()
            if not key or key in seen:
                continue
            seen.add(key)
            dedup.append(c)
        real = dedup

        if limit >= len(real):
            picked = real
        else:
            picked = []
            for low, high in BANDS:
                band = [c for c in real if low <= (c.verdict_score or 0) < high]
                random.seed(20261030)
                random.shuffle(band)
                picked.extend(band[:max(1, limit // len(BANDS))])

        for c in picked:
            ev = _evidence(c.verdict_evidence)
            # 联网复核一次，标注时参考（结果只写入样本，不改库）
            try:
                web = web_probe.search_multi(f'"{c.entity}"', limit=6, expect=c.entity)
                exist = check_existence(c.entity, c.description or "", web)
            except Exception:
                exist = {"status": "unavailable", "domains": [], "consistency": 0.0}
            v = variants(ev, c.verdict_score or 0)
            rows.append({
                "id": c.id,
                "entity": c.entity,
                "description": (c.description or "")[:160],
                "stored_score": round(c.verdict_score or 0, 3),
                "scores": v,
                "decisions": decide(v),
                "web_status": exist.get("status"),
                "domain_count": len(exist.get("domains") or []),
                "consistency": exist.get("consistency"),
                "evidence_types": sorted({e.get("type") for e in ev}),
            })
    finally:
        db.close()

    WORK.mkdir(parents=True, exist_ok=True)
    SAMPLE_PATH.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"抽样 {len(rows)} 条 → {SAMPLE_PATH}")
    print(f"{'id':>5} {'分数':>5} {'A/B/C/D':>18} {'联网':>12}  实体")
    for r in rows:
        s = r["scores"]
        print(f"{r['id']:>5} {r['stored_score']:>5.2f} "
              f"{s['A']:.2f}/{s['B']:.2f}/{s['C']:.2f}/{s['D']:.2f} "
              f"{str(r['web_status']):>12}  {r['entity'][:32]}")
    return 0


def do_report() -> int:
    if not SAMPLE_PATH.exists():
        print("先跑 --sample")
        return 1
    samples = json.loads(SAMPLE_PATH.read_text(encoding="utf-8"))
    labels = {}
    if LABEL_PATH.exists():
        labels = json.loads(LABEL_PATH.read_text(encoding="utf-8"))

    missing = [s["id"] for s in samples if str(s["id"]) not in labels]
    if missing:
        print(f"还有 {len(missing)} 条未标注：{missing[:8]}")
        return 1

    truth = {int(k): v for k, v in labels.items() if str(k).isdigit()}
    positives = sum(1 for v in truth.values() if v)
    print(f"标注：{len(truth)} 条，其中真实概念 {positives} 条\n")
    print(f"{'口径':<16}{'采纳数':>6}{'精确率':>9}{'召回率':>8}")

    for key, label in (("A", "A 现行 0.80"), ("B", "B 归一化 0.80"),
                       ("C", "C 原分 0.70"), ("D", "D 归一化 0.70")):
        accepted = [s for s in samples if s["decisions"][key]]
        tp = sum(1 for s in accepted if truth[s["id"]])
        precision = tp / len(accepted) if accepted else 0.0
        recall = tp / positives if positives else 0.0
        print(f"{label:<16}{len(accepted):>6}{precision:>9.0%}{recall:>8.0%}")

    for key in "ABCD":
        picked = [s for s in samples if s["decisions"][key] and not truth[s["id"]]]
        if picked:
            print(f"\n{key} 误收（{len(picked)} 条）：")
            for s in picked[:6]:
                print(f"  - {s['entity'][:40]}（{s['stored_score']:.2f}，{s['web_status']}）")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sample", type=int, default=0)
    parser.add_argument("--report", action="store_true")
    args = parser.parse_args()
    if args.sample:
        return do_sample(args.sample)
    if args.report:
        return do_report()
    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
