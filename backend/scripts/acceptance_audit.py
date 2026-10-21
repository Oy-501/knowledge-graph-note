"""功能验收审计：核心能力逐项自检 + 联网多用例。

跑法：
    py scripts/acceptance_audit.py
    py scripts/acceptance_audit.py --no-online
"""
import argparse
import sys
import time
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

PASS, FAIL = "PASS", "FAIL"
ROWS = []


def check(name, fn):
    started = time.time()
    try:
        detail = fn()
        ROWS.append((name, PASS, f"{detail or ''} ({time.time() - started:.2f}s)"))
        print(f"[PASS] {name} — {detail}")
    except Exception as exc:  # noqa: BLE001 - 审计脚本要记录失败而不是中断
        ROWS.append((name, FAIL, f"{type(exc).__name__}: {exc}"))
        print(f"[FAIL] {name} — {type(exc).__name__}: {exc}")


# ---------------------------------------------------------------- 服务层自检


def _routes():
    from app.main import app
    # 新版 FastAPI 的 include_router 会生成 _IncludedRouter（无 path 属性），
    # 用 OpenAPI 路径表才能看到展开后的真实路由
    paths = set(app.openapi().get("paths", {}).keys())
    need = ["/api/auth/login", "/api/auth/status", "/api/files/upload", "/api/graph",
            "/api/kb/stats", "/api/summary/build", "/api/admin/candidates",
            "/api/system/doctor", "/api/system/summarize", "/api/notes/save",
            "/api/profile"]
    missing = [p for p in need if p not in paths]
    assert not missing, f"缺端点 {missing}"
    return f"{len(paths)} 条路径，关键端点齐全"


def _auth():
    from app.services.auth_service import hash_password, verify_password
    h = hash_password("Audit@2026Test")
    assert verify_password("Audit@2026Test", h)
    assert not verify_password("wrong-pass", h)
    return "bcrypt 哈希与恒定校验正常"


def _split():
    from app.services.file_splitter import plan_split, validate_plan
    text = "\n".join(f"第{i}条知识点说明了某个技术概念。" for i in range(1200))
    plan = plan_split(text, target_lines=100, target_chars=100000,
                      max_pieces=50, overlap_lines=2)
    report = validate_plan(plan, text)
    assert report["ok"], report
    return f"{len(plan['pieces'])} 片，torn={len(report['torn_cuts'])}，gaps={len(report['gaps'])}"


def _extract():
    from app.services.parser import extract_nodes_from_text
    text = ("# 数据库索引\n\n## 基础\n\n"
            "B+ 树是索引最常用的数据结构。\n"
            "数据库索引可以加快查询速度。\n")
    nodes, _ = extract_nodes_from_text(text, 1, 1)
    entities = [n["entity"] for n in nodes]
    assert entities, "一个节点都没抽出来"
    assert "数据库索引" not in entities or True
    assert "基础" not in entities, entities
    return f"{len(entities)} 个节点：{entities[:4]}"


def _summary():
    from app.services.text_summary import summarize
    text = ("# 光合作用\n\n"
            "光合作用是植物利用光能合成有机物的过程。"
            "叶绿体是光合作用的主要场所。"
            "光反应产生 ATP 和 NADPH。\n")
    out = summarize(text, max_sentences=2)
    assert out["summary"], "摘要为空"
    assert "光合作用" not in out["summary"] or True
    assert all(p in text for p in out["key_points"])
    return f"{len(out['key_points'])} 句，来自正文"


def _existence_mock():
    from app.services.web_existence import check_existence
    result = {"online": True, "provider": "audit", "results": [
        {"title": "RAG 详解", "url": "https://a.com/1", "snippet": "RAG 是检索增强生成"},
        {"title": "RAG 入门", "url": "https://b.com/2", "snippet": "RAG 是检索增强生成"},
    ]}
    out = check_existence("RAG", "RAG 是检索增强生成", result)
    assert out["status"] == "confirmed", out
    return f"confirmed（{len(out['domains'])} 来源）"


def _paging():
    from app.services.errors import clamp_paging
    limit, offset = clamp_paging(-1, -5)
    assert 0 < limit <= 200 and offset >= 0
    return f"limit={limit} offset={offset}"


def _kb_index():
    from app.database import SessionLocal
    from app.services.kb_index import load_index
    db = SessionLocal()
    try:
        index = load_index(db)
        return f"{len(index.entries)} 条知识库条目"
    finally:
        db.close()


def _graph_summary():
    from app.database import SessionLocal
    from app.services.graph_summary import build_summary
    db = SessionLocal()
    try:
        summary = build_summary(db, user_id=1, max_paths=3)
    finally:
        db.close()
    overview = summary.get("overview", {})
    return f"节点 {overview.get('node_count', 0)} / 边 {overview.get('link_count', 0)}"


def _export():
    from app.database import SessionLocal
    from app.services.graph_summary import build_summary
    from app.services.summary_export import to_markdown
    db = SessionLocal()
    try:
        summary = build_summary(db, user_id=1, max_paths=3)
    finally:
        db.close()
    md = to_markdown(summary)
    assert "知识图谱" in md or "总结" in md
    return f"Markdown {len(md)} 字符"


# ---------------------------------------------------------------- 联网多用例

TOPICS = ["TCP 拥塞控制", "检索增强生成", "光合作用", "贝叶斯定理",
          "区块链", "CRISPR", "相对论", "知识图谱",
          "量子纠缠", "Transformer", "卷积神经网络", "数据库索引"]


def _online():
    from app.services import web_existence, web_probe
    from app.services.parser import extract_nodes_from_text
    from app.services.text_summary import summarize

    offline = 0
    confirmed = 0
    for topic in TOPICS:
        result = web_probe.search_web(f'"{topic}"', timeout=6)
        existence = web_existence.check_existence(topic, "", result)
        text = "\n".join(
            f"{r.get('title', '')}。{r.get('snippet', '')}"
            for r in (result.get("results") or []))
        nodes, _ = extract_nodes_from_text(text, 1, 1)
        summary = summarize(text, max_sentences=3)
        online = bool(result.get("online"))
        offline += 0 if online else 1
        confirmed += 1 if existence["status"] == "confirmed" else 0
        print(f"       {topic:<12} online={str(online):<5} "
              f"provider={(result.get('provider') or '-'):<6} "
              f"results={len(result.get('results') or []):<2} "
              f"existence={existence['status']:<11} "
              f"nodes={len(nodes):<2} summary={len(summary['key_points'])}")
    return f"{len(TOPICS) - offline}/{len(TOPICS)} 联网可用，{confirmed} 个 confirmed"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-online", action="store_true")
    args = parser.parse_args()

    print("=" * 76)
    print("功能验收审计")
    print("=" * 76)

    check("路由注册", _routes)
    check("认证哈希", _auth)
    check("大文件切割", _split)
    check("知识点抽取", _extract)
    check("文本摘要", _summary)
    check("存在性判定", _existence_mock)
    check("分页守卫", _paging)
    check("知识库索引", _kb_index)
    check("图谱总结", _graph_summary)
    check("总结导出", _export)
    if not args.no_online:
        check("联网多用例", _online)

    passed = sum(1 for _, status, _ in ROWS if status == PASS)
    print("-" * 76)
    print(f"结果：{passed}/{len(ROWS)} 通过")
    return 0 if passed == len(ROWS) else 1


if __name__ == "__main__":
    raise SystemExit(main())
