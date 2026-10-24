"""变异测试矩阵：逐个破坏受守护逻辑，验证测试真的会失败。"""

import json
import pathlib
import re
import subprocess

ROOT = pathlib.Path(r"C:\Users\yr200\Documents\trae_projects\YR")
BACKEND = ROOT / "backend"
KV = BACKEND / "app" / "services" / "knowledge_verifier.py"
ADMIN = BACKEND / "app" / "api" / "admin.py"
MODEL_JSON = BACKEND / "tests" / "data" / "verdict_model.json"
REAL_JSON = BACKEND / "tests" / "data" / "verdict_real_corpus.json"


def _m9(d):
    """变异 9：把零分用例的期望改成 accept。"""
    for c in d["boundary_cases"]:
        if c["name"] == "零分":
            c["expect"] = "accept"


def _m10(d):
    """变异 10：把真实候选的判定改成 reject。"""
    for c in d["真实候选"]:
        if c["entity"] == "RAG":
            c["生产库判定"]["decision"] = "reject"


MUTATIONS = [
    dict(id="M1", 性质="阈值 0.80 / 冲突否决",
         破坏="决策条件改成 score >= 0.5（连带取消冲突否决）",
         kind="code", file=KV,
         old="        if score >= settings.VERDICT_AUTO_ACCEPT and not self.conflict:",
         new="        if score >= 0.5:",
         target="tests/test_verdict_model.py"),
    dict(id="M2", 性质="有界性（上限）",
         破坏="clamp 去掉上限 min(1.0, ...)",
         kind="code", file=KV,
         old="        score = max(0.0, min(1.0, self.score))",
         new="        score = max(0.0, self.score)",
         target="tests/test_verdict_model.py"),
    dict(id="M3", 性质="有界性（下限）",
         破坏="clamp 去掉下限 max(0.0, ...)",
         kind="code", file=KV,
         old="        score = max(0.0, min(1.0, self.score))",
         new="        score = min(1.0, self.score)",
         target="tests/test_verdict_model.py"),
    dict(id="M4", 性质="可加性 A1",
         破坏="证据只累加一半（Σw 不再等于 score）",
         kind="code", file=KV,
         old="        self.score += weight",
         new="        self.score += weight * 0.5",
         target="tests/test_verdict_model.py"),
    dict(id="M5", 性质="联网中性 A5",
         破坏="联网不可用改成 −0.1 权重（搜不到当成负面证据）",
         kind="code", file=KV,
         old='"type": "web", "weight": 0, "positive": True,\n                    "detail": f"联网校验不可用',
         new='"type": "web", "weight": -0.1, "positive": True,\n                    "detail": f"联网校验不可用',
         target="tests/test_verdict_model.py"),
    dict(id="M6", 性质="人工裁决不被覆盖",
         破坏="重跑判定时不跳过人工裁决（skip_human 恒为 False）",
         kind="code", file=ADMIN,
         old="        skip_human=not payload.force)",
         new="        skip_human=False)",
         target="tests/test_verdict_batch.py"),
    dict(id="M7", 性质="批量入库只重建一次关系",
         破坏="批量入库改回每条都重建（defer_relations=False）",
         kind="code", file=ADMIN,
         old="defer_relations=True)",
         new="defer_relations=False)",
         target="tests/test_verdict_batch.py"),
    dict(id="M8", 性质="重复候选归 merged",
         破坏="去掉 _merge_twins 调用",
         kind="code", file=KV,
         old="    _merge_twins(db, candidate, entry.id)\n    return entry.id",
         new="    return entry.id",
         target="tests/test_verdict_batch.py"),
    dict(id="M9", 性质="测试数据确实驱动用例",
         破坏="数据文件里「零分」的期望改成 accept",
         kind="json", file=MODEL_JSON, mutate=_m9,
         target="tests/test_verdict_model.py"),
    dict(id="M10", 性质="真实语料确实驱动用例",
         破坏="真实语料里 RAG 的历史判定改成 reject",
         kind="json", file=REAL_JSON, mutate=_m10,
         target="tests/test_verdict_real_data.py"),
]


def _run(target):
    """跑一份测试，返回 (转红用例条数, 通过条数, 被抓到的测试函数)

    判据刻意用 **FAILED 行的条数**，不用汇总行的 "N failed"：
    pytest 在 -q 下被 subprocess 捕获时不输出那行统计，
    靠它会把所有破坏误判成「没抓到」（这次真踩到了）。
    """
    r = subprocess.run(["py", "-m", "pytest", target, "--no-header"],
                       cwd=str(BACKEND), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    out = (r.stdout or "") + (r.stderr or "")
    failed = len(re.findall(r"^FAILED ", out, re.M))
    m = re.search(r"(\d+) passed", out)
    passed = int(m.group(1)) if m else None
    funcs = sorted(set(re.findall(r"FAILED (?:tests/[\w./]+)::([\w_]+)", out)))
    return failed, passed, funcs


results = []
for mut in MUTATIONS:
    path = mut["file"]
    orig = path.read_text(encoding="utf-8")
    try:
        if mut["kind"] == "code":
            if mut["old"] not in orig:
                results.append((mut, None, ["锚点未找到"], "跳过"))
                continue
            path.write_text(orig.replace(mut["old"], mut["new"], 1), encoding="utf-8")
        else:
            d = json.loads(orig)
            mut["mutate"](d)
            path.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
        failed, _passed, funcs = _run(mut["target"])
        results.append((mut, failed, funcs, "抓到" if failed else "漏网"))
    finally:
        path.write_text(orig, encoding="utf-8")

lines = []
lines.append("# 变异测试矩阵（测试有效性的证据）\n")
lines.append("对每个被守护的性质各注入**一个真实破坏**，跑对应用例，看抓不抓得到。")
lines.append("抓不到 = 那条用例是空转的。全部注入后已写回原文。\n")
lines.append("| 编号 | 守护的性质 | 注入的破坏 | 结果 | 转红用例数 | 被抓到的用例 |")
lines.append("|---|---|---|---|---|---|")
for mut, failed, funcs, verdict in results:
    if failed is None:
        lines.append(f"| {mut['id']} | {mut['性质']} | {mut['破坏']} | 跳过 | - | {funcs[0]} |")
        continue
    names = "、".join(f"`{f}`" for f in funcs) if funcs else "—"
    lines.append(f"| {mut['id']} | {mut['性质']} | {mut['破坏']} | **{verdict}** | {failed} | {names} |")

caught = sum(1 for _, f, _, v in results if v == "抓到")
total = sum(1 for _, f, _, _ in results if f is not None)
lines.append(f"\n**{caught} / {total} 个破坏被抓到**，"
             f"{total - caught} 个漏网。")
lines.append("\n## 复核方式\n")
lines.append("还原之后重跑三份测试，确认回到全绿（证明上面的「红」确由注入引起，不是环境噪声）：")

lines.append("\n| 测试文件 | 还原后结果 |")
lines.append("|---|---|")
for t in ("tests/test_verdict_model.py", "tests/test_verdict_batch.py",
          "tests/test_verdict_real_data.py"):
    failed, passed, _funcs = _run(t)
    lines.append(f"| `{t}` | {'全绿' if failed == 0 else str(failed) + ' 条仍红'}"
                 f"（{passed if passed is not None else '—'} passed） |")

out = ROOT / "docs" / "arch" / "2026-10-18" / "变异测试矩阵.md"
out.write_text("\n".join(lines) + "\n", encoding="utf-8")

print("\n".join(lines))
print("\n写出：", out)
