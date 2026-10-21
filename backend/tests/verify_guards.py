"""反向验证：确认这套测试真的能抓到回归

一套全绿的测试可能什么都没守住 —— 只要用例断言得不够具体，破坏代码它照样绿。
本脚本逐个**故意破坏**被守护的逻辑，确认对应用例真的失败，然后还原。

这不是一次性的临时探针，而是测试套件的一部分：**以后每隔一段时间、或大改动之后，
都应该跑一次**，避免测试悄悄退化成「永远绿灯」。

跑法（在 backend/ 目录下）：
    py tests/verify_guards.py

退出码：0 = 每个破坏都被抓到（测试有效）；1 = 有用例是「假绿」，需要加强断言。
"""
import pathlib
import re
import subprocess
import sys

BACKEND = pathlib.Path(__file__).resolve().parents[1]
NL = chr(10)

# (说明, 相对 backend/ 的文件, 原串, 破坏成, 应当失败的用例文件)
MUTATIONS = [
    (
        "去掉分页的负数保护（SQLite 里 LIMIT -1 = 不限行数）",
        "app/services/errors.py",
        "    if lim <= 0:" + NL + "        lim = default_limit",
        "    if False:" + NL + "        lim = default_limit",
        "tests/test_paging.py",
    ),
    (
        "中文改回按空白切词（整句变 1 个词元，相似度恒为 0）",
        "app/services/vector_engine.py",
        "    if not text:" + NL + "        return []" + NL + "    tokens: List[str] = []",
        "    return text.split()" + NL + "    if not text:" + NL + "        return []"
        + NL + "    tokens: List[str] = []",
        "tests/test_vector_engine.py",
    ),
    (
        "连线标记写死 time_bridge=True（统计量变成「哪段代码写的」）",
        "app/services/inference.py",
        '                    "auto_generated": True,' + NL + "                    **flags,",
        '                    "auto_generated": True,' + NL
        + '                    "time_bridge": True,',
        "tests/test_inference.py",
    ),
    (
        "缓存指纹退化成计数级（改一条已有条目不会失效）",
        "app/services/kb_index.py",
        "    kb = db.execute(_KB_SCAN).all()" + NL + "    rel = db.execute(_REL_SCAN).all()",
        "    kb = db.execute(_KB_SCAN).all()[:0]" + NL
        + "    rel = db.execute(_REL_SCAN).all()",
        "tests/test_kb_index.py",
    ),
    (
        "删文件时漏清子表（外键约束会失败，报错点在 DELETE FROM files）",
        "app/api/files.py",
        "    db.query(KnowledgeCandidate).filter_by(file_id=file_id)"
        ".delete(synchronize_session=False)",
        "    pass  # 故意漏清",
        "tests/test_files_purge.py",
    ),
    (
        "把登录端点移出写守卫豁免名单（形成「永远登不进去」死锁）",
        "app/main.py",
        '("POST", "/api/auth/login"),',
        '("POST", "/api/auth/login-DISABLED"),',
        "tests/test_auth_guard.py",
    ),
    (
        "request_id 白名单放进 `/`（路径穿越字符不再被剔除）",
        "app/services/security.py",
        '_RID_SAFE = re.compile(r"[^A-Za-z0-9._:\\-]")',
        '_RID_SAFE = re.compile(r"[^A-Za-z0-9._:/\\-]")',
        "tests/test_api_contract.py",
    ),
    (
        "自检不再上报损坏向量（β 维恒为 0 却显示一切正常）",
        "app/api/system.py",
        '    if health["broken"]:' + NL + "        problems.append(",
        "    if False:" + NL + "        problems.append(",
        "tests/test_system_doctor.py",
    ),
    (
        "导出写死 6 条主线（页面上选的主线数对导出不生效）",
        "app/api/summary.py",
        '    """导出总结：Markdown / Word / PPTX / Mermaid / AI 摘要 / JSON"""' + NL
        + "    summary, mermaid = _build(db, user_id, group_by, max_paths)",
        '    """导出总结：Markdown / Word / PPTX / Mermaid / AI 摘要 / JSON"""' + NL
        + "    summary, mermaid = _build(db, user_id, group_by, 6)",
        "tests/test_summary_export.py",
    ),
    (
        "同名节点不去重（枢纽榜与样例出现「索引、索引」）",
        "app/services/graph_summary.py",
        "    seen, out = set(), []" + NL + "    for n in nodes:" + NL
        + "        title = n.title or n.entity" + NL + "        if title in seen:",
        "    seen, out = set(), []" + NL + "    for n in nodes:" + NL
        + "        title = n.title or n.entity" + NL + "        if False:",
        "tests/test_summary_export.py",
    ),
    (
        "PPT 空节不再给说明（导出出现只剩标题的白板页）",
        "app/services/summary_export.py",
        "        add_rect(s, 0.6, 1.7, 12.1, 1.5, C_WHITE, line=C_BG)" + NL
        + "        add_text(s, 0.95, 1.95, 11.4, 1.1, why, size=13, color=C_MUTED," + NL
        + "                 line_spacing=1.5)",
        "        pass  # 故意不画",
        "tests/test_summary_export.py",
    ),
    (
        "导出目录改回自己推 dirname（测试产物会挤掉用户自己的导出）",
        "app/services/summary_export.py",
        "    return settings.resolved_export_dir",
        # 刻意指向系统临时目录而不是仓库目录：这条破坏会让导出落到错误的地方，
        # 指到仓库里就会在 `backend/app/services/` 下建一个产物目录，
        # 修改被还原、目录却留下了。
        '    return os.path.join(os.environ.get("TEMP", "/tmp"), "kg-mutation-exports")',
        "tests/test_summary_export.py",
    ),
    (
        "关掉「整句残骸」判定（一句话会被当成知识点）",
        "app/services/parser.py",
        "    return len(name) >= _CLAUSE_MIN_LEN and bool(_CLAUSE_MARK.search(name[2:]))",
        "    return False",
        "tests/test_parser.py",
    ),
    (
        "总结不再过滤噪音标题（残骸会出现在枢纽榜与学习主线里）",
        "app/services/graph_summary.py",
        "        # 疑似噪音的标题不能被摆成「核心枢纽」—— 读者会以为那是重点知识" + NL
        + "        if _looks_noisy(title):",
        "        # 疑似噪音的标题不能被摆成「核心枢纽」—— 读者会以为那是重点知识" + NL
        + "        if False:",
        "tests/test_summary_export.py",
    ),
    (
        "后台守卫退回「一律 401」（已登录但权限不够，却把人指向重新登录）",
        "app/api/admin.py",
        "    if session_state == \"other\":",
        "    if False:",
        "tests/test_auth_guard.py",
    ),
    (
        "引擎指纹丢掉模型名（换模型后旧向量不会被判为陈旧）",
        "app/services/vector_engine.py",
        '        return f"st|{settings.VECTOR_MODEL}|{_engine_dim}|{ALGO_VERSION}"',
        '        return f"st|{_engine_dim}|{ALGO_VERSION}"',
        "tests/test_vector_model.py",
    ),
    # ---- 以下三条只打中 `test_functional_journeys`：破坏之后
    #      **状态码仍然是 200**，只有去断言中间产物才看得见。
    #      这正是功能测试这一层存在的理由（模块级用例各自都还是绿的）。
    (
        "上传返回 200 却跳过解析（「成功」了但一个知识点都没抽出来）",
        "app/api/files.py",
        "        background_tasks.add_task(parse_and_extract, file_record.id, user_id)",
        "        pass  # 故意不解析",
        "tests/test_functional_journeys.py",
    ),
    (
        "删文件时不清除节点（图谱里留下悬空知识点）",
        "app/api/files.py",
        "    node_ids = [n.id for n in db.query(Node).filter_by(file_id=file_id).all()]",
        "    node_ids = []",
        "tests/test_functional_journeys.py",
    ),
    (
        "检索丢掉文档节点一路（刚上传的内容搜不到）",
        "app/api/knowledge.py",
        "    node_results = db.query(Node).filter(" + NL
        + "        Node.entity.ilike(f\"%{escape_like(keyword)}%\", escape='\\\\')," + NL
        + "        Node.status == \"active\"" + NL
        + "    ).limit(limit).all()",
        "    node_results = []",
        "tests/test_functional_journeys.py",
    ),
    (
        "写守卫不再认登录会话（会话能登录，但做不了任何写操作）",
        "app/main.py",
        '    if (actor and actor["role"] == "admin") \\' + NL
        + '            or verify_admin_token(request.headers.get("X-Admin-Token")):',
        '    if verify_admin_token(request.headers.get("X-Admin-Token")):',
        "tests/test_functional_journeys.py",
    ),
    # ---- 忘记密码：这三条错得很安静（功能看着正常，安全性已经没了）----
    (
        "恢复码明文入库（库被拖走即可换掉任何人的密码）",
        "app/services/auth_service.py",
        "    user.recovery_hash = hash_password(normalize_recovery_code(code))",
        "    user.recovery_hash = normalize_recovery_code(code)",
        "tests/test_auth_recovery.py",
    ),
    (
        "重置后不轮换恢复码（用过的码可以反复重置）",
        "app/services/auth_service.py",
        "    new_code = issue_recovery_code(db, user)",
        "    new_code = recovery_code",
        "tests/test_auth_recovery.py",
    ),
    (
        "重置后不吊销旧会话（改完密码，别处的登录还在）",
        "app/services/auth_service.py",
        "    new_code = issue_recovery_code(db, user)" + NL
        + "    revoke_user_sessions(db, user.id)",
        "    new_code = issue_recovery_code(db, user)" + NL
        + "    pass  # 故意不吊销",
        "tests/test_auth_recovery.py",
    ),
    (
        "个人空间（背景/资料）重新被要求管理员权限",
        "app/main.py",
        '    ("PUT", "/api/profile"),' + NL,
        '',
        "tests/test_auth_guard.py",
    ),
]


def run_tests(target: str) -> tuple:
    # 刻意**不传 `-q`**：`pytest.ini` 的 addopts 里已经有 `-q`，再加一个就成了 `-qq`，
    # 而 pytest 在 `-qq` 下**不打印结尾的统计行**（只留 "FAILED …" 短摘要）。
    # 曾经传了 `-q`，结果是下面那段「取汇总行」的代码永远取不到东西、静默回退到最后一行 ——
    # 看着像在工作，其实读到的是别的行；换个失败形态（收集期报错、钩子告警）
    # 最后一行就可能是 `-- Docs: …`，读起来像是用例挂了。
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", target, "--tb=no", "-p", "no:cacheprovider"],
        cwd=BACKEND, capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    out = (proc.stdout or "") + (proc.stderr or "")
    lines = [ln.strip() for ln in out.strip().splitlines() if ln.strip()]
    stdout_lines = [ln.strip() for ln in (proc.stdout or "").splitlines() if ln.strip()]

    # 统计行只在 **stdout** 里找。stderr 是环境噪声（安全删除钩子告警等），
    # 混在一起会被误当成本次结果。
    # 要求前面带数字，才不会把 "FAILED tests/…" 这种短摘要当成统计行。
    count = next(
        (ln for ln in reversed(stdout_lines)
         if re.search(r"\b\d+ (?:passed|failed|error)\b", ln)
         or re.search(r"\bno tests ran\b", ln)),
        None,
    )
    # 顺带把第一个失败用例名带上：只说「3 failed」不知道是哪条，还得回去翻。
    first_failed = next((ln for ln in lines if ln.startswith("FAILED ")), None)

    if count and first_failed:
        detail = f"{count}｜首个失败：{first_failed[len('FAILED '):]}"
    else:
        detail = count or first_failed or (lines[-1] if lines else "")
    return proc.returncode, detail


def main() -> int:
    print("=" * 74)
    print("  反向验证：测试到底守没守住")
    print("=" * 74)

    code, line = run_tests("tests")
    print(f"  破坏前基线：{'通过' if code == 0 else '未通过'} —— {line}")
    if code != 0:
        print("  基线不是全绿，先修好再来做反向验证")
        return 2

    print()
    missed = []
    for desc, rel, old, new, target in MUTATIONS:
        path = BACKEND / rel
        src = path.read_text(encoding="utf-8")
        if old not in src:
            print(f"  [跳过] {desc}")
            print(f"         锚点在 {rel} 里找不到，说明代码已改，需同步更新本脚本")
            missed.append(desc)
            continue

        # 备份就是内存里的 src，**不落盘**。
        # 曾经写成「先 shutil.copy 出 .mutation-bak，再 shutil.move 还原」，两个问题：
        #   · move 在目标已存在时走的是「复制 + unlink(备份)」，而本机安全删除钩子会拦 unlink
        #     → 异常抛在 finally 里。一个专门用来「先破坏再还原」的脚本，在还原这步炸掉；
        #   · 备份文件还删不掉，跑一轮就在源码目录留下十几个 .mutation-bak。
        # 写回原文是幂等的、一定成功的，也完全不需要临时文件。
        try:
            path.write_text(src.replace(old, new, 1), encoding="utf-8")
            code, line = run_tests(target)
            caught = code != 0
            print(f"  [{'已抓住' if caught else '**漏报**'}] {desc}")
            print(f"           {target} → {line}")
            if not caught:
                missed.append(desc)
        finally:
            path.write_text(src, encoding="utf-8")

    code, line = run_tests("tests")
    print()
    print(f"  还原后：{'通过' if code == 0 else '未通过'} —— {line}")

    print()
    if missed:
        print(f"  有 {len(missed)} 项没被抓住，这些断言需要加强：")
        for m in missed:
            print(f"    - {m}")
        return 1
    if code != 0:
        # 不能在这里说「恢复全绿」——上面那行已经说明它不是。
        # 允许的唯一失败是环境噪声，但必须显式提示去核对，不能自己替它圆场。
        print(f"  全部 {len(MUTATIONS)} 项破坏都被抓到，但**还原后的基线不是全绿**。")
        print("  先确认是改动没还原干净，还是环境问题（例如安全删除钩子拦了 "
              "pytest 的临时目录清理）—— 基线不绿时，上面的「已抓住」都不算数。")
        return 1
    print(f"  全部 {len(MUTATIONS)} 项破坏都被抓到，且还原后恢复全绿。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
