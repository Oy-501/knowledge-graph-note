"""联网存在性确认的现场演示：随机取一个问题，真实检索一次并输出判定。

跑法：
    py scripts/demo_web_existence.py
    py scripts/demo_web_existence.py --seed 42
    py scripts/demo_web_existence.py --entity "量子纠缠"
"""
import argparse
import random
import sys
from pathlib import Path
from types import SimpleNamespace

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from app.services import web_existence, web_probe  # noqa: E402

POOL = [
    ("量子纠缠", "量子纠缠是量子力学中两个粒子状态相互关联的现象"),
    ("Transformer 注意力机制", "Transformer 使用自注意力机制建模序列依赖"),
    ("光合作用", "光合作用是植物利用光能合成有机物的过程"),
    ("区块链", "区块链是一种分布式账本技术"),
    ("贝叶斯定理", "贝叶斯定理描述条件概率的更新方式"),
    ("知识图谱", "知识图谱用图结构表示实体及其关系"),
    ("扩散模型", "扩散模型通过逐步去噪生成数据"),
    ("TCP 拥塞控制", "TCP 拥塞控制用于避免网络过载"),
    ("CRISPR", "CRISPR 是一种基因编辑技术"),
    ("相对论", "相对论描述时空与引力的关系"),
]


def main() -> int:
    """命令行入口：随机问题联网判定演示。"""
    parser = argparse.ArgumentParser(description="联网存在性确认演示")
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--entity", default="")
    parser.add_argument("--full", action="store_true", help="同时跑完整判定机")
    args = parser.parse_args()

    if args.entity:
        entity, desc = args.entity, ""
    else:
        seed = args.seed if args.seed is not None else random.randrange(1, 10 ** 6)
        random.seed(seed)
        print(f"随机种子：{seed}（用 --seed {seed} 可复现）")
        entity, desc = random.choice(POOL)

    print("=" * 72)
    print(f"问题：{entity}")
    print(f"描述：{desc or '（无）'}")
    print("=" * 72)

    query = f'"{entity.replace(chr(34), " ")}"'
    print(f"检索式：{query}")
    result = web_probe.search_web(query, timeout=8)
    print(f"联网：{'可用' if result.get('online') else '不可用'}"
          f" · provider={result.get('provider') or '-'}"
          f" · 结果 {len(result.get('results') or [])} 条")

    for i, row in enumerate((result.get("results") or [])[:4], 1):
        print(f"\n  [{i}] {row.get('title', '')[:72]}")
        print(f"      {row.get('url', '')[:84]}")
        if row.get("snippet"):
            print(f"      {row['snippet'][:100]}")

    verdict = web_existence.check_existence(entity, desc, result)
    print("\n" + "-" * 72)
    print("存在性判定")
    print(f"  状态      {verdict['status']}")
    print(f"  置信度    {verdict['confidence']}")
    print(f"  精确命中  {verdict['exact_hits']}")
    print(f"  独立来源  {len(verdict['domains'])} 个  {verdict['domains'][:5]}")
    print(f"  描述一致  {verdict['consistency']}")
    print(f"  理由      {verdict['reason']}")

    if args.full:
        try:
            from app.database import SessionLocal
            from app.services import knowledge_verifier as kv

            db = SessionLocal()
            try:
                cand = SimpleNamespace(entity=entity, title=entity, description=desc,
                                       keywords=[], domain="general", node_id=None)
                out = kv.verify_candidate(db, cand, use_web=True,
                                          web_budget={"left": 5})
            finally:
                db.close()
            print("\n完整判定机")
            print(f"  score={out['score']}  decision={out['decision']}"
                  f"  conflict={out['conflict']}  web_status={out['web_status']}")
            for ev in out["evidence"]:
                print(f"  - [{ev['type']}] {ev['detail'][:88]}")
        except Exception as exc:  # noqa: BLE001 - 演示脚本，失败不影响主输出
            print(f"\n完整判定跳过：{exc}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
