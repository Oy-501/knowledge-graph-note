"""图谱总结 CLI

用法（在 backend 目录下执行）：
  py scripts/graph_summary.py                         # 生成总结，打印概览与 AI 摘要
  py scripts/graph_summary.py --ai                    # 只打印 AI 可读摘要（可重定向成文件）
  py scripts/graph_summary.py --mermaid               # 只打印 Mermaid 流程图源码
  py scripts/graph_summary.py --export md docx pptx   # 导出到 backend/exports/
  py scripts/graph_summary.py --demo                  # 用 test_data/kb_demo 的对照文档搭临时演示库再导出
                                                      # （写入 backend/summary_demo.db，不动正式库）
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def run_demo():
    """用演示语料搭一个临时库（不动正式库），便于查看完整效果"""
    demo_db = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                           "summary_demo.db")
    os.environ["SQLITE_PATH"] = demo_db
    os.environ["DB_MODE"] = "sqlite"
    for mod in [m for m in list(sys.modules) if m.startswith("app.")]:
        del sys.modules[mod]


def main():
    parser = argparse.ArgumentParser(description="知识图谱总结与导出")
    parser.add_argument("--export", nargs="*", default=[],
                        choices=["md", "docx", "pptx", "mermaid", "digest", "json"],
                        help="导出格式（可多选）")
    parser.add_argument("--group-by", default="level", choices=["level", "domain"],
                        help="流程图分组方式")
    parser.add_argument("--title", default="知识图谱总结", help="导出文件标题")
    parser.add_argument("--max-paths", type=int, default=6, help="学习主线条数")
    parser.add_argument("--ai", action="store_true", help="只打印 AI 可读摘要")
    parser.add_argument("--mermaid", action="store_true", help="只打印 Mermaid 流程图")
    parser.add_argument("--demo", action="store_true", help="用演示语料搭临时库后再总结")
    args = parser.parse_args()

    if args.demo:
        run_demo()

    from app.database import SessionLocal, init_db
    from app.seed import ensure_default_user, seed_knowledge_base
    from app.services.kb_index import build_relations_from_entries
    from app.services.graph_summary import attach_raw_links, build_summary, to_ai_digest, to_mermaid
    from app.services import summary_export as exporter

    init_db()
    db = SessionLocal()
    try:
        ensure_default_user(db)
        seed_knowledge_base(db)
        build_relations_from_entries(db)

        if args.demo:
            _load_demo_docs(db)

        summary = build_summary(db, user_id=1, max_paths=args.max_paths)
        attach_raw_links(summary, db, user_id=1)
        mermaid = to_mermaid(summary, group_by=args.group_by)

        if args.ai:
            print(to_ai_digest(summary))
            return
        if args.mermaid:
            print(mermaid)
            return

        ov = summary.get("overview", {})
        print(json.dumps({
            "overview": ov,
            "levels": summary.get("levels"),
            "paths": len(summary.get("paths", [])),
            "clusters": len(summary.get("clusters", [])),
            "hubs": [h["title"] for h in summary.get("hubs", [])[:6]],
            "suggestions": summary.get("suggestions"),
        }, ensure_ascii=False, indent=2))

        for fmt in (args.export or ["md"]):
            if fmt == "docx":
                path = exporter.to_docx(summary, mermaid, title=args.title)
            elif fmt == "pptx":
                path = exporter.to_pptx(summary, mermaid, title=args.title)
            elif fmt in ("mermaid", "mmd"):
                path = exporter.export_path("知识图谱流程图", "mmd")
                with open(path, "w", encoding="utf-8") as f:
                    f.write(mermaid)
            elif fmt == "digest":
                path = exporter.to_ai_digest_file(summary)
            elif fmt == "json":
                path = exporter.export_path("知识图谱总结", "json")
                with open(path, "w", encoding="utf-8") as f:
                    json.dump({k: v for k, v in summary.items()
                               if k not in ("_raw_links", "node_index")},
                              f, ensure_ascii=False, indent=2)
            else:
                path = exporter.export_path("知识图谱总结", "md")
                with open(path, "w", encoding="utf-8") as f:
                    f.write(exporter.to_markdown(summary, mermaid, title=args.title))
            print(f"[导出] {fmt} → {path}")
    finally:
        db.close()


def _load_demo_docs(db):
    """把 test_data/kb_demo 下的对照文档灌进（临时）库并走完整解析流程"""
    from app.models.models import File
    from app.services.parser import parse_and_extract

    demo_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__)))), "test_data", "kb_demo")
    if not os.path.isdir(demo_dir):
        print(f"[警告] 演示语料目录不存在：{demo_dir}")
        return
    for name in sorted(os.listdir(demo_dir)):
        if not name.endswith(".txt"):
            continue
        path = os.path.join(demo_dir, name)
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        exists = db.query(File).filter_by(user_id=1, name=name).first()
        if exists:
            continue
        row = File(user_id=1, name=name, content=content, status="parsing")
        db.add(row)
        db.commit()
        db.refresh(row)
        parse_and_extract(row.id, 1)
        print(f"[载入] {name}")


if __name__ == "__main__":
    main()
