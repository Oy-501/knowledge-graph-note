"""语义向量重建 CLI

换了向量引擎（装上 sentence-transformers、换模型、改编码算法）之后必须跑一次，
否则存量向量还是旧引擎产出的：不同引擎的向量维度不同，放在一起比较时
cosine 恒为 0（是「没法比」不是「不相似」），β 维会被静默跳过。

用法（在 backend 目录下执行）：
  py scripts/reembed.py                # 用当前引擎重建全部节点向量
  py scripts/reembed.py --dry-run      # 只看现状与将要发生什么，不写库
  py scripts/reembed.py --tfidf        # 强制走降级编码（用来验证降级路径）
  py scripts/reembed.py --user 1       # 只重建某个用户的节点
  py scripts/reembed.py --db path.db   # 指定 SQLite 库（不污染正式库时用）
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _banner(title: str) -> None:
    print("=" * 68)
    print(title)
    print("=" * 68)


def main() -> int:
    parser = argparse.ArgumentParser(description="重建节点语义向量")
    parser.add_argument("--dry-run", action="store_true", help="只显示现状，不写库")
    parser.add_argument("--tfidf", action="store_true", help="强制使用降级编码")
    parser.add_argument("--user", type=int, default=None, help="只重建该用户的节点")
    parser.add_argument("--db", default=None, help="SQLite 库路径（覆盖 SQLITE_PATH）")
    parser.add_argument("--json", action="store_true", help="以 JSON 输出")
    args = parser.parse_args()

    if args.db:
        os.environ["SQLITE_PATH"] = os.path.abspath(args.db)
        os.environ["DB_MODE"] = "sqlite"
    if args.tfidf:
        os.environ["VECTOR_BACKEND"] = "tfidf"

    from app.database import SessionLocal, init_db
    from app.services import vector_engine

    init_db()
    db = SessionLocal()
    try:
        before = vector_engine.get_engine_info()
        health_before = vector_engine.embedding_health(db)

        if not args.json:
            _banner("重建前")
            print(f"引擎      : {before['signature']}")
            print(f"状态      : {'降级（字面重合）' if before['degraded'] else '真模型'}"
                  f"{' · ' + before['reason'] if before['reason'] else ''}")
            print(f"向量      : {health_before['with_embedding']}/{health_before['total']} 条，"
                  f"缺失 {health_before['empty']}，陈旧 {health_before['stale']}")
            print(f"现存维度  : {health_before['dims'] or '无'}")

        if args.dry_run:
            if not args.json:
                _banner("dry-run：未写入任何数据")
            else:
                print(json.dumps({"before": before, "health_before": health_before,
                                  "dry_run": True}, ensure_ascii=False, indent=2))
            return 0

        # force=True：允许本次重新尝试加载模型（进程内缓存可能停留在降级状态）
        ok = vector_engine.prepare(force=True)
        if args.tfidf:
            ok = False

        result = vector_engine.rebuild_embeddings(db, user_id=args.user)
        health_after = vector_engine.embedding_health(db)

        if args.json:
            print(json.dumps({
                "model_loaded": ok,
                "before": before,
                "health_before": health_before,
                "rebuild": result,
                "health_after": health_after,
            }, ensure_ascii=False, indent=2))
            return 0 if ok or args.tfidf else 1

        _banner("重建后")
        print(f"引擎      : {result['signature']}")
        print(f"更新      : {result['updated']}/{result['total']} 条")
        print(f"旧指纹    : {result['previous_signatures'] or '（原本没有指纹，说明都是旧版本产生的）'}")
        print(f"现存维度  : {health_after['dims'] or '无'}")
        print(f"仍陈旧    : {health_after['stale']}")

        if not ok:
            print()
            print("!" * 68)
            print("注意：当前仍是降级编码，重建后只认字面重合。")
            print(f"原因：{before['reason'] or '未安装 sentence-transformers'}")
            print("安装后重跑本脚本，β 维才能真正理解「换了说法的同一件事」。")
            print("!" * 68)
        return 0 if (ok or args.tfidf) else 1
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
