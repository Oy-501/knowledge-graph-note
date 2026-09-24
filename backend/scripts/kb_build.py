"""知识库构建 CLI

用法（在 backend 目录下执行）：
  py scripts/kb_build.py                    # 关系推导 + 全量锚定/画像/关联
  py scripts/kb_build.py --relations-only   # 只推导知识库关系边
  py scripts/kb_build.py --check            # 只体检：统计 + 抽样验证
  py scripts/kb_build.py --understand path/to/kb.csv   # 理解一份知识库文档并入库
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal, init_db
from app.seed import ensure_default_user, seed_knowledge_base
from app.services.kb_index import build_relations_from_entries, load_index
from app.services import kb_link


def report_compact(report: dict) -> dict:
    return {
        "format": report["format"], "summary": report["summary"],
        "new_entries": [e["entity"] for e in report["new_entries"]],
        "merged_entries": [m["entity"] for m in report["merged_entries"]],
        "conflicts": [{"entity": c["entity"], "resolution": c["resolution"]} for c in report["conflicts"]],
        "relations_added": len(report["relations_added"]),
        "relations_derived": report.get("relations_derived", 0),
        "rejected": report["rejected"], "stats": report["stats"],
    }


def sync_corpus(db) -> dict:
    from app.models.models import KnowledgeBase
    from app.seed import load_all_corpora
    from app.services.kb_index import load_index, normalize_key
    index = load_index(db)
    before = db.query(KnowledgeBase).count()
    added = []
    for entry in load_all_corpora():
        key = normalize_key(entry["entity"])
        if not key or key in index.alias_map:
            continue
        db.add(KnowledgeBase(**entry))
        added.append(entry["entity"])
        index.alias_map[key] = entry["entity"]
    db.commit()
    rel = build_relations_from_entries(db)
    return {"corpus_entries_found": before + len(added), "added": len(added),
            "added_samples": added[:20], "kb_total": db.query(KnowledgeBase).count(),
            "relations_total": rel["total"]}


def main():
    parser = argparse.ArgumentParser(description="知识库层构建工具")
    parser.add_argument("--relations-only", action="store_true", help="只推导知识库关系边")
    parser.add_argument("--check", action="store_true", help="只体检知识库与关联情况")
    parser.add_argument("--understand", type=str, default="", help="理解并导入一份知识库文档")
    parser.add_argument("--threshold", type=float, default=0.15, help="文件知识相似度阈值")
    parser.add_argument("--node-threshold", type=float, default=0.15, help="节点知识关联阈值")
    parser.add_argument("--sample", type=str, default="", help="对一段文本做知识锚定抽样")
    parser.add_argument("--sync-corpus", action="store_true", help="把语料里新增的条目增量补进知识库")
    args = parser.parse_args()

    init_db()
    db = SessionLocal()
    try:
        ensure_default_user(db)
        seed_knowledge_base(db)
        if args.sync_corpus:
            result = sync_corpus(db)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return
        if args.understand:
            from app.services.kb_import import understand_kb_document
            with open(args.understand, "r", encoding="utf-8") as f:
                content = f.read()
            report = understand_kb_document(db, name=os.path.basename(args.understand), content=content)
            print(json.dumps(report_compact(report), ensure_ascii=False, indent=2))
            return
        rel = build_relations_from_entries(db)
        print(f"[知识库关系] 新增 {rel['created']} 条，总计 {rel['total']} 条")
        if args.relations_only:
            return
        if args.sample:
            index = load_index(db)
            hits = index.scan(args.sample)
            print(json.dumps({"hits": len(hits), "matched": sorted({h["entity"] for h in hits}),
                              "detail": hits[:20]}, ensure_ascii=False, indent=2))
            return
        if args.check:
            stats = kb_link.kb_rebuild_all(db, user_id=1, threshold=args.threshold, node_threshold=args.node_threshold)
            print(json.dumps(stats, ensure_ascii=False, indent=2))
            return
        result = kb_link.kb_rebuild_all(db, user_id=1, threshold=args.threshold, node_threshold=args.node_threshold)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    finally:
        db.close()


if __name__ == "__main__":
    main()
