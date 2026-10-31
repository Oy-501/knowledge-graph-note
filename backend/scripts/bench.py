"""性能基准：联网搜索与知识点归纳。

用法：
    py scripts/bench.py                 # 全部
    py scripts/bench.py search          # 联网：search_web / search_multi / search_videos
    py scripts/bench.py verdict         # 判定：单条知识点（含/不含联网）
    py scripts/bench.py extract         # 抽取：文本 → 知识点
    py scripts/bench.py --repeat 5      # 每项重复次数（默认 3）

数字口径：
    cold = 第一次（无缓存）；warm = 后续的中位数（命中进程内缓存）。
"""
import argparse
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database import SessionLocal                      # noqa: E402
from app.models.models import KnowledgeCandidate            # noqa: E402
from app.services import web_probe                          # noqa: E402
from app.services.kb_index import load_index                # noqa: E402
from app.services.knowledge_verifier import verify_candidate  # noqa: E402
from app.services.parser import extract_nodes_from_text     # noqa: E402

ENTITIES = ["B+ 树", "JWT 无状态认证", "Cache-Control max-age", "聚簇索引与回表"]

SAMPLE = "".join(
    f"### {name}\n\n{name} 是一种用于验证解析链路的虚拟知识点，"
    f"包含定义、适用场景与常见误区三部分内容。\n\n"
    for name in [f"测试概念{i}" for i in range(40)]
)


def _timed(fn, repeat: int):
    times, ok = [], 0
    for _ in range(repeat):
        start = time.perf_counter()
        try:
            fn()
            ok += 1
        except Exception:
            pass
        times.append(time.perf_counter() - start)
    return times, ok


def run_search(repeat: int):
    rows = []
    for entity in ENTITIES:
        query = f'"{entity}"'
        cases = [
            ("search_web 单源", lambda: web_probe.search_web(query, limit=5)),
            ("search_multi 双源", lambda: web_probe.search_multi(query, limit=6, expect=entity)),
            ("search_videos B站", lambda: web_probe.search_videos(entity, limit=3)),
        ]
        for name, fn in cases:
            times, ok = _timed(fn, repeat)
            warm = statistics.median(times[1:]) if len(times) > 1 else times[0]
            rows.append((name, entity, times[0], warm, ok))
    return rows


def run_verdict(limit: int):
    db = SessionLocal()
    try:
        kb = load_index(db)
        cands = (db.query(KnowledgeCandidate)
                 .filter(KnowledgeCandidate.status == "open")
                 .order_by(KnowledgeCandidate.id.desc()).limit(limit).all())
        result = {"n": len(cands)}
        for use_web in (False, True):
            times = []
            for c in cands:
                start = time.perf_counter()
                verify_candidate(db, c, kb=kb, use_web=use_web)
                times.append(time.perf_counter() - start)
            result[use_web] = times
        return result
    finally:
        db.close()


def run_extract(repeat: int):
    times, ok = _timed(lambda: extract_nodes_from_text(SAMPLE, 1, 1), repeat)
    return times, ok, len(SAMPLE)


def _p(vals, pct):
    if not vals:
        return 0.0
    ordered = sorted(vals)
    idx = min(len(ordered) - 1, int(len(ordered) * pct))
    return ordered[idx]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("part", nargs="?", default="all",
                        choices=["all", "search", "verdict", "extract"])
    parser.add_argument("--repeat", type=int, default=3)
    parser.add_argument("--limit", type=int, default=6, help="判定测试的候选条数")
    args = parser.parse_args()

    if args.part in ("all", "search"):
        print("\n## 联网搜索")
        print("| 调用 | 知识点 | 首次(冷) | 中位(热) | 成功 |")
        print("|---|---|---|---|---|")
        for name, entity, cold, warm, ok in run_search(args.repeat):
            print(f"| {name} | {entity} | {cold:.2f}s | {warm:.2f}s | {ok}/{args.repeat} |")

    if args.part in ("all", "verdict"):
        print("\n## 知识点判定（单条）")
        data = run_verdict(args.limit)
        n = data["n"]
        print(f"候选 {n} 条")
        print("| 模式 | 单条中位 | p95 | 总耗时 |")
        print("|---|---|---|---|")
        for key, label in ((False, "仅本地证据"), (True, "含联网校验")):
            vals = data[key]
            if not vals:
                continue
            print(f"| {label} | {statistics.median(vals)*1000:.0f}ms | "
                  f"{_p(vals, 0.95)*1000:.0f}ms | {sum(vals):.2f}s |")

    if args.part in ("all", "extract"):
        print("\n## 知识点抽取")
        times, ok, length = run_extract(args.repeat)
        nodes, _ = extract_nodes_from_text(SAMPLE, 1, 1)
        print(f"样本 {length} 字 / {len(nodes)} 个知识点")
        print(f"中位 {statistics.median(times)*1000:.0f}ms，"
              f"每 1000 字约 {statistics.median(times)/max(length/1000, 0.001)*1000:.1f}ms，"
              f"成功 {ok}/{args.repeat}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
