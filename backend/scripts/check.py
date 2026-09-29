"""代码体检（防御机制第 1 层：开发期静态防线）

在启动服务之前把「会引发运行期错误」的问题挡掉，一次跑完给出可执行结论：

  1. 语法编译      —— 所有 .py 能否通过 compile（抓缩进/语法错误）
  2. 模块导入      —— 应用能否完整导入（抓循环导入、缺依赖、名字拼错）
  3. 路由冲突      —— 同一「方法 + 路径」被注册两次（后者静默覆盖前者，极难发现）
  4. 表结构漂移    —— 模型列 vs 实际库列（抓「加了列却忘写迁移」→ no such column）
  5. 静默吞异常    —— `except ...: pass` 这类把错误藏起来的写法
  6. 关键配置      —— 默认口令、阈值倒挂、路径可写
  7. 前端工程      —— 关键文件存在、依赖已装、构建产物

用法::

    py backend/scripts/check.py            # 体检当前后端
    py backend/scripts/check.py --json     # 机器可读输出（供 CI / 自动化用）

退出码：0 = 通过（可有警告）；1 = 存在必须修复的错误。
"""
from __future__ import annotations

import re
import argparse
import ast
import json
import os
import py_compile
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

BACKEND = Path(__file__).resolve().parent.parent
PROJECT = BACKEND.parent
sys.path.insert(0, str(BACKEND))

OK, WARN, FAIL = "ok", "warn", "error"
_ICON = {OK: "✓", WARN: "!", FAIL: "✕"}

ROWS: List[Dict[str, Any]] = []


def add(name: str, title: str, status: str, detail: str, hint: str = ""):
    ROWS.append({"name": name, "title": title, "status": status,
                 "detail": detail, "hint": hint, "icon": _ICON.get(status, "?")})


# ------------------------------------------------------------------ 1. 语法


def check_syntax() -> None:
    """用内置 compile() 做语法检查。

    刻意不用 py_compile：它在 Windows 上需要写字节码文件，
    传 os.devnull（nul）会被拒绝，传临时目录又多一次磁盘 I/O。
    compile() 纯内存完成，跨平台一致。
    """
    targets = [p for p in list((BACKEND / "app").rglob("*.py"))
               + list((BACKEND / "scripts").rglob("*.py"))
               if "__pycache__" not in p.parts]
    bad: List[str] = []
    for p in targets:
        try:
            source = p.read_text(encoding="utf-8")
            compile(source, str(p), "exec", dont_inherit=True)
        except SyntaxError as exc:
            bad.append(f"{p.relative_to(BACKEND)}:{exc.lineno} {exc.msg}")
        except Exception as exc:  # noqa: BLE001
            bad.append(f"{p.relative_to(BACKEND)}: {type(exc).__name__}: {exc}")
    if bad:
        add("syntax", "语法编译", FAIL, f"{len(bad)} 个文件编译失败",
            "；".join(bad[:3]) + ("…" if len(bad) > 3 else ""))
    else:
        add("syntax", "语法编译", OK, f"{len(targets)} 个 Python 文件全部通过")


# ------------------------------------------------------------------ 2. 导入


def check_import() -> Tuple[bool, Any]:
    try:
        from app.main import app  # noqa: F401
        add("import", "应用导入", OK, "app.main 可完整导入（无循环导入/缺依赖/拼写错误）")
        return True, app
    except Exception as exc:  # noqa: BLE001
        import traceback
        tb = traceback.format_exc().strip().splitlines()
        add("import", "应用导入", FAIL, f"{type(exc).__name__}: {exc}",
            "最后一行调用栈：" + (tb[-3].strip() if len(tb) >= 3 else ""))
        return False, None


# ------------------------------------------------------------------ 3. 路由


def _flatten_routes(app) -> List[Tuple[str, str]]:
    """收集 (method, path)。

    兼容两种 FastAPI 行为：老版本把 include_router 展开进 app.routes，
    新版本用 _IncludedRouter 包装（保留 original_router）。两者都处理。
    """
    out: List[Tuple[str, str]] = []

    def walk(container, prefix: str = ""):
        for r in getattr(container, "routes", []) or []:
            name = type(r).__name__
            if name == "_IncludedRouter":
                inner = getattr(r, "original_router", None)
                ctx_prefix = prefix
                for attr in ("include_context",):
                    ctx = getattr(r, attr, None)
                    p = getattr(ctx, "prefix", None) if ctx else None
                    if p:
                        ctx_prefix = prefix + p
                if inner is not None:
                    walk(inner, ctx_prefix)
                continue
            path = getattr(r, "path", None)
            methods = getattr(r, "methods", None)
            if path and methods:
                for m in methods:
                    if m in ("HEAD", "OPTIONS"):
                        continue
                    out.append((m, prefix + path))
            elif path:
                walk(r, prefix)

    # 优先用 OpenAPI（最贴近实际对外契约），再补原始路由做重复检测
    out_flat: List[Tuple[str, str]] = []
    for r in app.routes:
        if type(r).__name__ == "_IncludedRouter":
            inner = getattr(r, "original_router", None)
            ctx = getattr(r, "include_context", None)
            pfx = getattr(ctx, "prefix", "") if ctx else ""
            if inner is not None:
                for sub in getattr(inner, "routes", []) or []:
                    path = getattr(sub, "path", None)
                    methods = getattr(sub, "methods", None) or []
                    if path:
                        for m in methods:
                            if m not in ("HEAD", "OPTIONS"):
                                out_flat.append((m, (pfx or "") + path))
        else:
            path = getattr(r, "path", None)
            methods = getattr(r, "methods", None) or []
            for m in methods:
                if m not in ("HEAD", "OPTIONS"):
                    out_flat.append((m, path or ""))
    return out_flat


def check_routes(app) -> None:
    try:
        routes = _flatten_routes(app)
    except Exception as exc:  # noqa: BLE001
        add("routes", "路由注册", WARN, f"无法解析路由表：{exc}")
        return
    if not routes:
        # 新 FastAPI 结构差异时的兜底：改用 OpenAPI 校验
        try:
            paths = app.openapi().get("paths", {})
            total = sum(len([m for m in v if m in ("get", "post", "put", "patch", "delete")])
                        for v in paths.values())
            add("routes", "路由注册", OK if total else WARN,
                f"OpenAPI 暴露 {len(paths)} 条路径 / {total} 个方法")
        except Exception as exc:  # noqa: BLE001
            add("routes", "路由注册", WARN, f"OpenAPI 生成失败：{exc}")
        return

    from collections import Counter
    counter = Counter(routes)
    dups = [(m, p, n) for (m, p), n in counter.items() if n > 1]
    if dups:
        sample = "；".join(f"{m} {p}×{n}" for m, p, n in dups[:4])
        add("routes", "路由注册", FAIL, f"{len(dups)} 组重复路由（后者会静默覆盖前者）",
            sample)
    else:
        methods = Counter(m for m, _ in routes)
        add("routes", "路由注册", OK,
            f"{len(routes)} 个端点，无冲突 · " +
            " ".join(f"{m}:{c}" for m, c in methods.most_common()))


def check_openapi(app) -> None:
    """OpenAPI 能否生成 —— 生成失败会让 /docs 与前端类型推导一起挂掉。"""
    try:
        spec = app.openapi()
        n_paths = len(spec.get("paths", {}))
        n_schemas = len(spec.get("components", {}).get("schemas", {}))
        add("openapi", "接口契约", OK, f"{n_paths} 条路径 / {n_schemas} 个数据模型可生成")
    except Exception as exc:  # noqa: BLE001
        add("openapi", "接口契约", FAIL, f"OpenAPI 生成失败：{type(exc).__name__}: {exc}",
            "通常是某个端点的响应模型定义有误（如返回类型标注不可序列化）。")


# ------------------------------------------------------------------ 4. 表结构


def check_schema() -> None:
    try:
        from app.api.system import _check_schema_drift
        res = _check_schema_drift()
        add("schema", "表结构一致性", res.get("status", OK),
            res.get("detail", ""), res.get("hint", ""))
    except Exception as exc:  # noqa: BLE001
        add("schema", "表结构一致性", WARN, f"跳过（{type(exc).__name__}: {exc}）")


# ------------------------------------------------------------------ 5. 静默吞异常


def check_silent_swallow() -> None:
    """找出 `except ...: pass` / 只有 pass 的 except —— 错误被藏起来的地方。

    这类写法会让真实缺陷在运行期完全无声（例如解析失败但文件被标成 done），
    是本项目已经踩过的坑，所以单独作为一项检查。
    """
    offenders: List[str] = []
    for p in (BACKEND / "app").rglob("*.py"):
        if "__pycache__" in p.parts:
            continue
        try:
            tree = ast.parse(p.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.ExceptHandler):
                continue
            body = [n for n in node.body
                    if not (isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant)
                            and isinstance(n.value.value, str))]  # 去掉 docstring
            if len(body) == 1 and isinstance(body[0], ast.Pass):
                offenders.append(f"{p.relative_to(BACKEND)}:{node.lineno}")
    if offenders:
        add("silent_except", "静默吞异常", WARN,
            f"{len(offenders)} 处 `except: pass`（错误被隐藏，排查时无线索）",
            "；".join(offenders[:5]) + "。建议至少加一行 logger.debug/warning 保留线索。")
    else:
        add("silent_except", "静默吞异常", OK, "未发现无记录的 `except: pass`")


# ------------------------------------------------------------------ 5b. 未绑定引用


def check_undefined_names() -> None:
    """找出「被引用但从未被绑定」的名字。

    为什么需要这一项：导入检查（`import app.main`）只执行模块顶层代码，
    函数体里的名字要等到**被调用**才解析。所以
    「函数里用了 escape_like 却忘了 import」这类错误能顺利通过导入检查，
    直到用户点到那个接口才炸出 NameError —— 这正是本轮改代码时真实踩到的坑。

    实现口径（保守求准，宁可漏报不可误报）：
      1. 收集整个模块里**所有**被绑定的名字：import / def / class / 赋值目标 /
         for 目标 / with as / except as / 形参 / 推导式目标（不限层级）
      2. 收集所有 Load 上下文的名字
      3. 差集 - 内置名 - 模块 dunder = 可疑的未绑定引用

    「只要在模块任何地方绑定过就算数」的宽松口径会漏掉作用域误用，
    但能稳稳抓住「完全没导入」这一类，且几乎不产生噪音。
    """
    import builtins

    builtin_names = set(dir(builtins))
    offenders: List[str] = []

    for p in (BACKEND / "app").rglob("*.py"):
        if "__pycache__" in p.parts:
            continue
        try:
            tree = ast.parse(p.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue

        bound: set = set()
        loaded: List[Tuple[str, int]] = []

        def _bind_target(node) -> None:
            """递归收集赋值/推导式目标里的名字（含解包）"""
            if node is None:
                return
            if isinstance(node, ast.Name):
                bound.add(node.id)
            elif isinstance(node, (ast.Tuple, ast.List)):
                for e in node.elts:
                    _bind_target(e)
            elif isinstance(node, ast.Starred):
                _bind_target(node.value)

        def _bind_args(args) -> None:
            for a in (list(args.posonlyargs) + list(args.args) + list(args.kwonlyargs)):
                bound.add(a.arg)
            if args.vararg:
                bound.add(args.vararg.arg)
            if args.kwarg:
                bound.add(args.kwarg.arg)

        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                for alias in node.names:
                    bound.add((alias.asname or alias.name).split(".")[0])
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                bound.add(node.name)
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    _bind_args(node.args)
            elif isinstance(node, ast.Lambda):
                _bind_args(node.args)
            elif isinstance(node, ast.Assign):
                for t in node.targets:
                    _bind_target(t)
            elif isinstance(node, (ast.AugAssign, ast.AnnAssign)):
                _bind_target(node.target)
            elif isinstance(node, (ast.For, ast.AsyncFor)):
                _bind_target(node.target)
            elif isinstance(node, (ast.With, ast.AsyncWith)):
                for item in node.items:
                    _bind_target(item.optional_vars)
            elif isinstance(node, ast.ExceptHandler):
                if node.name:
                    bound.add(node.name)
            elif isinstance(node, ast.comprehension):
                _bind_target(node.target)
            elif isinstance(node, (ast.Global, ast.Nonlocal)):
                bound.update(node.names)
            elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
                bound.add(node.id)

        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
                name = node.id
                if name.startswith("__") and name.endswith("__"):
                    continue
                loaded.append((name, node.lineno))

        seen: set = set()
        for name, lineno in sorted(set(loaded)):
            if name in bound or name in builtin_names or name in seen:
                continue
            seen.add(name)
            offenders.append(f"{p.relative_to(BACKEND)}:{lineno} {name}")

    if offenders:
        add("undefined_names", "未绑定引用", FAIL,
            f"{len(offenders)} 处引用了从未导入/定义的名字（调用时才报 NameError）",
            "；".join(offenders[:5]) + ("…" if len(offenders) > 5 else ""))
    else:
        add("undefined_names", "未绑定引用", OK, "未发现未绑定即被引用的名字")


# ------------------------------------------------------------------ 5c. 外键清理覆盖


# 外键清理覆盖检查关注的「父表 → 清理函数」配对。
# 新增引用父表的表时，只要不在清理函数里出现，体检就会报错。
FK_PURGE_TARGETS = [
    ("files.id", "app/api/files.py", "_purge_file_nodes"),
]


def check_fk_purge_coverage() -> None:
    """检查「引用了父表的外键，是否都在删除父行时被清理」。

    背景：数据库开启了 `PRAGMA foreign_keys=ON`，删除父行前必须先清子行。
    本项目删除文件时曾在 `_purge_file_nodes` 里漏掉
    `file_knowledge_profiles` / `file_knowledge_links`，
    结果删文件直接报 `FOREIGN KEY constraint failed`，
    而报错点在 `DELETE FROM files`，看不出是哪张子表没清。

    判定方式：解析清理函数体，收集所有 `db.query(Model)` 用到的模型类名，
    再要求「引用该父表的所有模型」都在其中。
    刻意**只认代码、不认文本** —— 第一版用字符串包含判断，
    结果被自己写的文档注释里的表名骗过（注释提到表名即算通过）。
    注释不该影响判定，必须解析 AST 里真正的调用。
    """
    models_path = BACKEND / "app" / "models" / "models.py"
    try:
        tree = ast.parse(models_path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        add("fk_purge", "外键清理覆盖", WARN, f"无法解析模型文件：{exc}")
        return

    problems: List[str] = []
    for parent_ref, api_rel, func_name in FK_PURGE_TARGETS:
        referencing: Dict[str, str] = {}
        class_to_table: Dict[str, str] = {}
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            for sub in node.body:
                if isinstance(sub, ast.Assign) and \
                        getattr(sub.targets[0], "id", "") == "__tablename__" and \
                        isinstance(sub.value, ast.Constant):
                    class_to_table[node.name] = sub.value.value
            for sub in ast.walk(node):
                if isinstance(sub, ast.Call) and getattr(sub.func, "id", "") == "ForeignKey":
                    if parent_ref in [getattr(a, "value", None) for a in sub.args]:
                        referencing[node.name] = parent_ref

        api_file = BACKEND / api_rel
        if not api_file.exists():
            problems.append(f"{api_rel} 不存在")
            continue
        try:
            api_tree = ast.parse(api_file.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            problems.append(f"{api_rel} 解析失败：{exc}")
            continue

        # 找到清理函数，收集其中 db.query(X) 的 X
        purged: set = set()
        for node in ast.walk(api_tree):
            if isinstance(node, ast.FunctionDef) and node.name == func_name:
                for sub in ast.walk(node):
                    if isinstance(sub, ast.Call) and \
                            getattr(sub.func, "attr", "") == "query" and sub.args:
                        arg = sub.args[0]
                        if isinstance(arg, ast.Name):
                            purged.add(arg.id)
                        elif isinstance(arg, ast.Attribute):
                            purged.add(arg.attr)

        for cls in referencing:
            if cls not in purged:
                problems.append(f"{cls}({class_to_table.get(cls, '?')})")

    if problems:
        add("fk_purge", "外键清理覆盖", FAIL,
            f"{len(problems)} 张引用 files 的表未在删除流程中清理：{'、'.join(problems)}",
            "在 app/api/files.py 的 _purge_file_nodes 里补上对应删除语句，"
            "否则删除文件会报 FOREIGN KEY constraint failed")
    else:
        add("fk_purge", "外键清理覆盖", OK,
            f"引用 {FK_PURGE_TARGETS[0][0]} 的表均已在 {FK_PURGE_TARGETS[0][2]} 中清理")


# ------------------------------------------------------------------ 6. 配置


def check_config() -> None:
    try:
        from app.api.system import _check_config, _check_uploads_dir
        res = _check_config()
        add("config", "关键配置", res.get("status", OK),
            res.get("detail", ""), res.get("hint", ""))
        up = _check_uploads_dir()
        add("uploads", "上传目录", up.get("status", OK),
            up.get("detail", ""), up.get("hint", ""))
    except Exception as exc:  # noqa: BLE001
        add("config", "关键配置", WARN, f"跳过（{type(exc).__name__}: {exc}）")


# ------------------------------------------------------------------ 7. 前端


REQUIRED_FE_FILES = [
    "src/main.js", "src/App.vue", "src/api/index.js",
    "src/styles/main.css", "src/store/graphStore.js",
    "src/components/GraphCanvas.vue", "src/components/ErrorBoundary.vue",
    "src/utils/resilience.js", "src/utils/errorReporter.js",
]
REQUIRED_FE_DEPS = ["vue", "pinia", "element-plus", "axios", "d3"]


def check_frontend() -> None:
    fe = PROJECT / "kg-vue3"
    if not fe.is_dir():
        add("frontend", "前端工程", WARN, "未找到 kg-vue3 目录", "如需前端请确认目录名称。")
        return

    missing = [f for f in REQUIRED_FE_FILES if not (fe / f).exists()]
    if missing:
        add("frontend", "前端工程", FAIL,
            f"缺少 {len(missing)} 个关键文件：{'、'.join(missing)}",
            "这些文件被 App.vue / main.js 引用，缺失会导致构建失败。")
    else:
        add("frontend_files", "前端关键文件", OK, f"{len(REQUIRED_FE_FILES)} 个关键文件齐备")

    pkg = fe / "package.json"
    missing_deps: List[str] = []
    if pkg.exists():
        try:
            data = json.loads(pkg.read_text(encoding="utf-8"))
            declared = set(data.get("dependencies", {})) | set(data.get("devDependencies", {}))
            missing_deps = [d for d in REQUIRED_FE_DEPS if d not in declared]
        except Exception as exc:  # noqa: BLE001
            add("frontend_deps", "前端依赖声明", WARN, f"package.json 解析失败：{exc}")
            missing_deps = []
    if missing_deps:
        add("frontend_deps", "前端依赖声明", WARN,
            f"package.json 未声明：{'、'.join(missing_deps)}",
            "若代码里 import 了这些包，请在 kg-vue3 里 npm i 并写入依赖。")
    elif pkg.exists():
        add("frontend_deps", "前端依赖声明", OK, "关键依赖均已在 package.json 声明")

    if not (fe / "node_modules").is_dir():
        add("frontend_modules", "前端依赖安装", FAIL, "node_modules 不存在",
            "在 kg-vue3 目录执行 `npm install`。")
    else:
        add("frontend_modules", "前端依赖安装", OK, "node_modules 已就绪")


def check_frontend_build() -> None:
    """可选：真正跑一次生产构建（慢，默认关闭，--build 打开）。"""
    fe = PROJECT / "kg-vue3"
    if not (fe / "node_modules").is_dir():
        add("frontend_build", "前端构建", WARN, "跳过（依赖未安装）")
        return
    try:
        proc = subprocess.run(
            ["npx", "vite", "build", "--outDir", "dist-check", "--logLevel", "warn"],
            cwd=str(fe), capture_output=True, text=True, timeout=300, shell=True,
        )
        if proc.returncode == 0:
            add("frontend_build", "前端构建", OK, "生产构建通过")
        else:
            tail = (proc.stderr or proc.stdout or "").strip().splitlines()
            add("frontend_build", "前端构建", FAIL,
                "构建失败", "；".join(tail[-6:]))
    except subprocess.TimeoutExpired:
        add("frontend_build", "前端构建", FAIL, "构建超时（>300s）")
    except Exception as exc:  # noqa: BLE001
        add("frontend_build", "前端构建", WARN, f"跳过（{exc}）")


# ------------------------------------------------------------------ 8. 背景层不变量


def _strip_css_comments(src: str) -> str:
    """去掉 CSS 注释再做判断。

    为什么必须先去掉：这类检查曾两次被「注释里提到的字样」骗到
    （fail-open 检查误报、外键清理检查漏报）。注释里出现目标字符串
    既可能造成误报、也可能让人以为检查过了。
    """
    return re.sub(r"/\*.*?\*/", "", src, flags=re.S)


def _strip_js_comments(src: str) -> str:
    """去块注释 + 去「整行就是注释」的行注释（行首锚定，不会误伤字符串里的 //）。"""
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    return re.sub(r"(?m)^\s*//.*$", "", src)


def check_background_layers() -> None:
    """背景层不变量：素材层之上不该再压着「会把它盖住的不透明底」。

    背景有两套体系并存：
      ① 素材槽位（--tex-*，由 .app-tex 三层渲染）—— 现行方案
      ② 旧版单层（--editor-bg / --app-bg / --workbench-bg）——
         只在用户选了渐变 / 纯色 / 自定义图时才有意义

    踩过的坑：没有单层背景时，代码用 `css || 'var(--bg-primary)'` 给
    --editor-bg 兜了个不透明色并写到 <html> 上。内联变量优先级最高，
    于是样式表里 `var(--editor-bg, transparent)` 的 transparent 兜底
    **永远不生效**（var() 只在变量「未定义」时才用兜底）——
    工作台因此多出一块铺满的不透明底，把素材层挡住。
    实测：修复前后工作台 49.6% 的像素（29.4 万个）颜色发生变化。

    所以把三条钉住：变量不得有不透明默认值、不得用 `||` 兜不透明值、
    旧版整页背景层在素材类背景下不得渲染。
    """
    fe = PROJECT / "kg-vue3"
    if not fe.is_dir():
        add("bg_layers", "背景层不变量", WARN, "未找到 kg-vue3 目录")
        return

    LEGACY_VARS = ("--editor-bg", "--app-bg", "--workbench-bg")
    problems: List[str] = []

    # ① 样式表不得给旧版背景变量不透明默认值（有默认值 = 兜底失效）
    css_path = fe / "src" / "styles" / "main.css"
    if css_path.exists():
        css = _strip_css_comments(css_path.read_text(encoding="utf-8"))
        for var in LEGACY_VARS:
            m = re.search(re.escape(var) + r"\s*:\s*([^;{}]+);", css)
            if m and m.group(1).strip().lower() != "transparent":
                problems.append(f"main.css 给 {var} 定义了不透明默认值「{m.group(1).strip()}」")

    # ② store 不得用 `||` 给这些变量兜不透明值
    store = fe / "src" / "store" / "settingsStore.js"
    if store.exists():
        js = _strip_js_comments(store.read_text(encoding="utf-8"))
        for var in LEGACY_VARS:
            if re.search(r"setProperty\(\s*['\"]" + re.escape(var) + r"['\"]\s*,\s*[^;]{0,120}\|\|", js):
                problems.append(f"settingsStore 用 `||` 给 {var} 兜底（空串会被兜成不透明色）")

    # ③ 旧版整页背景层必须排除素材类背景
    app_vue = fe / "src" / "App.vue"
    if app_vue.exists():
        src = _strip_js_comments(app_vue.read_text(encoding="utf-8"))
        m = re.search(r"const globalBg\s*=\s*computed\(", src)
        if not m:
            problems.append("App.vue 里找不到 globalBg 判定，这项检查无法生效")
        else:
            body = src[m.end(): m.end() + 320].replace('"', "'")
            if "type !== 'asset'" not in body:
                problems.append("App.vue 的 globalBg 没排除素材类背景（会多渲染一层铺满视口的纯色）")

    if problems:
        add("bg_layers", "背景层不变量", FAIL, "；".join(problems),
            "素材层之上不能压不透明底：旧版背景变量只在「确实配置了单层背景」时才写，"
            "其余时候必须移除，让 var(--x, transparent) 的兜底接管。")
    else:
        add("bg_layers", "背景层不变量", OK,
            "旧版背景变量无默认值、无兜底写入；整页背景层已排除素材类背景")


# ------------------------------------------------------------------ 9. 安全不变量
#
# 说明：登录门禁接线（auth_wiring）现在是 check_security 里的一个断言块，
# 不是独立函数 —— 早期留过一个同名空壳函数，main() 调它等于什么都没做，
# 已删除。改鉴权相关代码时看 check_security 里标了「登录门禁接线」的那段。


def check_security() -> None:
    """把七条安全原则落成可自动回归的断言。

    设计初衷：安全配置会随着后续改动悄悄退化（比如「临时」把
    PROTECT_WRITES 关掉、把 mermaid 改回 loose、新写一个 v-html 忘了转义）。
    靠人记住是不现实的，必须能在体检里一眼看出来。
    """
    from app.config import settings

    # ---- 写操作保护（最小权限 / 零信任）----
    main_src = (BACKEND / "app" / "main.py").read_text(encoding="utf-8")
    guard_registered = ("write_guard" in main_src and "@app.middleware" in main_src)
    exemption_count = main_src.count("WRITE_GUARD_EXEMPT")

    if not settings.PROTECT_WRITES:
        add("sec_writes", "写操作保护", FAIL,
            "PROTECT_WRITES=false：任意可访问端口者都能删除条目、重建知识库",
            "恢复 backend/.env 的 PROTECT_WRITES=true")
    elif not guard_registered:
        add("sec_writes", "写操作保护", FAIL,
            "未在 main.py 中找到写操作守卫中间件（写端点可能全部裸奔）",
            "确认 write_guard 中间件已注册；新增写端点应默认受保护，豁免需显式登记")
    else:
        add("sec_writes", "写操作保护", OK,
            f"已开启：POST/PUT/PATCH/DELETE 均需管理口令（豁免清单存在={exemption_count > 0}）")

    # ---- 暴露面（攻击面最小化 / 默认安全）----
    exposure = []
    if settings.DEBUG:
        exposure.append("DEBUG=true（接口文档 /docs 对外可见）")
    if str(settings.HOST) not in ("127.0.0.1", "localhost"):
        exposure.append(f"HOST={settings.HOST}（非回环绑定）")
    if settings.ADMIN_TOKEN in ("", "kg-admin", "change-me"):
        exposure.append("ADMIN_TOKEN 为默认值/空")
    if exposure:
        add("sec_exposure", "暴露面收敛", FAIL if len(exposure) > 1 else WARN,
            "；".join(exposure),
            "生产环境建议 DEBUG=false、HOST=127.0.0.1、并设置强口令 ADMIN_TOKEN")
    else:
        add("sec_exposure", "暴露面收敛", OK,
            "DEBUG 关闭（接口文档不可达）· 仅绑回环 · 口令已自定义")

    # ---- 认证实现（失效安全 / 纵深防御）----
    # 用**行为**验证而不是字符串匹配：字符串匹配会被文档注释里的示例代码骗过
    # （本轮就踩到了 —— 新 require_admin 的 docstring 里引用了旧的错误写法）。
    auth_problems = []
    try:
        from app.config import settings as _s
        from app.api.admin import require_admin
        from fastapi import HTTPException as _HTTPException

        original = _s.ADMIN_TOKEN
        try:
            _s.ADMIN_TOKEN = ""      # 模拟「未配置口令」
            try:
                require_admin(x_admin_token=None, request=None)
                auth_problems.append("口令未配置时后台仍然放行（fail-open）")
            except _HTTPException:
                pass                 # 被拒绝 → 符合失效安全
        finally:
            _s.ADMIN_TOKEN = original

        # 口令错误必须被拒绝
        try:
            require_admin(x_admin_token="definitely-wrong-token", request=None)
            auth_problems.append("错误口令被放行")
        except _HTTPException:
            pass
    except Exception as exc:  # noqa: BLE001
        auth_problems.append(f"认证守卫无法验证：{type(exc).__name__}: {exc}")

    security_src = (BACKEND / "app" / "services" / "security.py").read_text(encoding="utf-8")
    admin_src = (BACKEND / "app" / "api" / "admin.py").read_text(encoding="utf-8")
    if "compare_digest" not in security_src:
        auth_problems.append("口令比较未使用恒定时间算法（hmac.compare_digest）")
    if "admin_limiter" not in admin_src:
        auth_problems.append("登录失败未限流（可被在线暴力破解）")

    if auth_problems:
        add("sec_auth", "认证守卫", FAIL, "；".join(auth_problems),
            "口令为空必须拒绝(fail-closed)、比较用 hmac.compare_digest、并限制失败次数")
    else:
        add("sec_auth", "认证守卫", OK,
            "实测：口令未配置→拒绝、口令错误→拒绝 · 恒定时间比较 · 失败限流已启用")

    # ---- 登录门禁接线（认证体系的关键不变量）----
    #
    # 这一段守的是「改了鉴权却把登录自己堵死」这类灾难性回归。
    # 最典型的一种：写守卫拦下了 POST /api/auth/login ——
    # 守卫只认令牌，而令牌正是登录接口要发给你的东西，于是谁也登不进去。
    # 这种 bug 不会报错、不会崩，只会表现为「输入正确的账号密码也进不去」，
    # 排查起来很费时间，所以必须由体检挡住。
    auth_wiring_problems: List[str] = []
    try:
        from app.main import (WRITE_GUARD_EXEMPT, WRITE_GUARD_USER_LEVEL,
                              SAFE_METHODS)
        from app.services import auth_service
        from app.api import auth as auth_api
    except Exception as exc:  # noqa: BLE001
        add("auth_wiring", "登录门禁接线", FAIL,
            f"无法导入认证相关模块：{type(exc).__name__}: {exc}")
    else:
        # ① 匿名可达的登录端点必须在豁免名单里
        must_exempt = {("POST", "/api/auth/login"),
                       ("POST", "/api/auth/register"),
                       ("POST", "/api/auth/bootstrap")}
        missing = sorted(must_exempt - set(WRITE_GUARD_EXEMPT))
        if missing:
            auth_wiring_problems.append(
                "写守卫会拦死登录端点（形成「永远登不进去」的死锁）："
                + "、".join(f"{m} {p}" for m, p in missing))

        # ② 只要求「已登录」的端点：否则注册出的普通账号连退出都做不到
        must_user_level = {("POST", "/api/auth/logout"),
                           ("POST", "/api/auth/password")}
        missing = sorted(must_user_level - set(WRITE_GUARD_USER_LEVEL))
        if missing:
            auth_wiring_problems.append(
                "以下端点在「登录即可」名单里缺席（普通账号将无法登出/改密）："
                + "、".join(p for _, p in missing))

        # ③ 会话头名必须全局一致：两处各写一遍字符串，改一处就会静默失效
        if auth_api.SESSION_HEADER != auth_service.SESSION_HEADER:
            auth_wiring_problems.append(
                f"会话头名不一致：api/auth.py={auth_api.SESSION_HEADER!r} "
                f"vs auth_service.py={auth_service.SESSION_HEADER!r}")

        # ④ 写守卫必须真的去解析会话（用 AST 判断，不看注释里的字样）
        #    原理：找到 write_guard 函数体，确认它调用了会话解析辅助函数。
        try:
            tree = ast.parse((BACKEND / "app" / "main.py").read_text(encoding="utf-8"))
            guard_fn = next(
                (n for n in ast.walk(tree)
                 if isinstance(n, ast.AsyncFunctionDef) and n.name == "write_guard"), None)
            fns = {n.name: n for n in ast.walk(tree)
                   if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}

            def names_used(fn):
                """函数体里出现的全部名字（含调用名与属性基名）"""
                out = set()
                for n in ast.walk(fn):
                    if isinstance(n, ast.Call):
                        out.add(getattr(n.func, "id", "") or getattr(n.func, "attr", ""))
                    if isinstance(n, ast.Name):
                        out.add(n.id)
                    if isinstance(n, ast.Attribute):
                        out.add(n.attr)
                return out

            if "write_guard" not in fns:
                auth_wiring_problems.append("main.py 里找不到 write_guard")
            elif "_session_actor" not in names_used(fns["write_guard"]):
                auth_wiring_problems.append(
                    "write_guard 没有调用 _session_actor（写操作可能仍只认旧口令）")

            # 读令牌头这件事发生在辅助函数里（守卫只负责调用它），
            # 所以常量检查要落在 _session_actor 上 —— 一开始写在 write_guard 上，
            # 是个错误的前提，会被自己误报。
            if "_session_actor" not in fns:
                auth_wiring_problems.append("main.py 里找不到 _session_actor")
            else:
                used = names_used(fns["_session_actor"])
                if "_session_actor" in fns and "SESSION_HEADER" not in used:
                    auth_wiring_problems.append(
                        "_session_actor 未使用 SESSION_HEADER 常量读令牌头"
                        "（硬编码头名会在改名时静默失效）")
        except Exception as exc:  # noqa: BLE001
            auth_wiring_problems.append(f"无法解析 main.py：{type(exc).__name__}")

        # ⑤ 认证路由必须已注册到 app
        if "auth.router" not in (BACKEND / "app" / "main.py").read_text(encoding="utf-8"):
            auth_wiring_problems.append("认证路由 auth.router 没有注册到 app")

    if auth_wiring_problems:
        add("auth_wiring", "登录门禁接线", FAIL,
            "；".join(auth_wiring_problems),
            "登录端点必须免写守卫；登出/改密只要求已登录；会话头名一致；"
            "写守卫必须解析会话；认证路由必须注册")
    else:
        add("auth_wiring", "登录门禁接线", OK,
            "登录端点已豁免写守卫 · 登出/改密为「登录即可」· 会话头名一致 · "
            "写守卫解析会话 · 路由已注册")

    # ---- 前端注入防护（输入永不信任 / 纵深防御）----
    fe = PROJECT / "kg-vue3"
    xss_problems = []
    if fe.is_dir():
        for f in list(fe.glob("src/**/*.vue")) + list(fe.glob("src/**/*.js")):
            try:
                text = f.read_text(encoding="utf-8")
            except Exception:  # noqa: BLE001
                continue
            if "securityLevel: 'loose'" in text:
                xss_problems.append(f"{f.relative_to(PROJECT)} mermaid securityLevel=loose（会放行内联 HTML）")
            if "v-html" in text or "innerHTML" in text:
                # Mermaid 的 strict 模式自带净化，可作为该文件的合法防护手段
                guarded = any(k in text for k in
                              ("escapeHtml", "escapeWithMap", "DOMPurify", "sanitize",
                               "textContent", "securityLevel: 'strict'"))
                if not guarded:
                    xss_problems.append(f"{f.relative_to(PROJECT)} 使用 v-html/innerHTML 但未见转义/净化")
    if xss_problems:
        add("sec_xss", "前端注入防护", FAIL, "；".join(xss_problems[:3]),
            "渲染不可信内容前必须先转义；Mermaid 用 securityLevel: 'strict'")
    else:
        add("sec_xss", "前端注入防护", OK,
            "使用 v-html/innerHTML 的位置均已配套转义/净化 · Mermaid 为 strict")


# ------------------------------------------------------------------ 10. 语义向量接线


def check_vector_wiring() -> None:
    """语义向量的三条不变量 —— β 维（语义相似度）的质量全指望它们。

    ① 降级编码必须真的按「中文按字切」。
       曾经的实现用空白切词：中文没有空格，整句话被切成一个词元，于是
       两个不同的中文句子共享 0 个词元，相似度恒为 0（实测 8 对改写句全 0）。
       这里**实际调用一次 analyze()** 看行为，不做字符串匹配 ——
       检查逻辑本身被自己写的注释骗过两次了。

    ② 向量和引擎指纹必须一起写。
       不同引擎的向量维度不同，混在一起 cosine 恒为 0（「没法比」而不是
       「不相似」）。只写向量不写指纹，就没法识别哪些需要重建。

    ③ 连线标记不能硬编码。
       曾经所有自动推理出来的连线都写死 time_bridge=True，于是
       「时间桥接 553 / 语义桥接 11」这类统计量，量的是「哪段代码写的」，
       不是「依据是什么」。
    """
    problems: List[str] = []

    # ---- ① 降级编码的中文切词（实测，不靠读代码）----
    try:
        from app.services import vector_engine

        probe = "数据库索引可以加快查询速度"
        tokens = vector_engine.analyze(probe)
        if len(tokens) <= 1:
            problems.append(
                f"降级编码把中文整句切成了 {len(tokens)} 个词元"
                f"（按字切应远多于 1，否则任意两个中文句子的相似度都是 0）")
        # 换个说法的两句必须有公共词元，否则 β 维对中文毫无信息量
        other = vector_engine.analyze("为数据表建立索引能提升检索性能")
        if not (set(tokens) & set(other)):
            problems.append("同义的中文改写句之间没有任何公共词元，降级编码无法工作")
    except Exception as exc:  # noqa: BLE001
        problems.append(f"无法调用向量引擎的切词函数：{type(exc).__name__}: {exc}")

    # ---- ② 向量与指纹成对写入（AST）----
    files_with_embedding_write: Dict[str, set] = {}
    for py in sorted((BACKEND / "app").rglob("*.py")):
        try:
            tree = ast.parse(py.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):
            continue
        for fn in [n for n in ast.walk(tree)
                   if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]:
            assigns = set()
            for node in ast.walk(fn):
                if isinstance(node, ast.Assign):
                    for tgt in node.targets:
                        if isinstance(tgt, ast.Attribute):
                            assigns.add(tgt.attr)
            if "embedding" in assigns and "embedding_meta" not in assigns:
                files_with_embedding_write.setdefault(
                    str(py.relative_to(PROJECT)), set()).add(fn.name)
    for path, fns in files_with_embedding_write.items():
        problems.append(
            f"{path} 的 {'、'.join(sorted(fns))} 写了 embedding 却没写 embedding_meta"
            f"（换引擎后无法识别陈旧向量）")

    # ---- ③ 连线标记必须跟着「依据」变，不能写死 ----
    #
    # 这里要的是「标记反映依据」，不是「代码里不许出现 True 这个字面量」。
    # kb_link.py 里 Link(semantic_bridge=True) 是**定义**（那条函数就是产知识库
    # 桥接连线的），属于正常写法；出问题的是推理链路 —— 它对所有连线一律写死
    # time_bridge=True，于是「时间/语义桥接」的统计量变成「哪段代码写的」。
    #
    # 所以分两步：先**实测**标记会不会随依据变（行为验证，最不易误判），
    # 再只在推理链路那两个文件里扫硬编码（那里没有任何正当理由写死）。
    try:
        from app.services.inference import _link_flags

        no_evidence = _link_flags({})
        by_keyword = _link_flags({"sim_text": 0.5})
        by_kb = _link_flags({"sim_corpus": 0.4})

        if not no_evidence.get("time_bridge"):
            problems.append("无任何内容依据时不标 time_bridge（连接线为何相连都说不清）")
        if by_keyword.get("time_bridge") or by_kb.get("time_bridge"):
            problems.append("有内容依据仍被标成 time_bridge（标记与依据脱节）")
        if not by_kb.get("semantic_bridge"):
            problems.append("知识库桥接出分了却没标 semantic_bridge")
        if by_keyword.get("semantic_bridge"):
            problems.append("仅关键词重合被标成 semantic_bridge（semantic/字面被混为一谈）")
    except Exception as exc:  # noqa: BLE001
        problems.append(f"无法验证连线标记逻辑：{type(exc).__name__}: {exc}")

    # 硬编码要同时在两种写法里找，缺一种就会漏报：
    #   ① Link(time_bridge=True)            —— 关键字参数
    #   ② {"time_bridge": True}             —— 先攒成 dict，后面再落库
    # 只查 ① 会漏掉 ②。（这一条正是反向验证抓出来的：把标记写死成 dict 字面量，
    # 检查照样绿灯。）
    _FLAG_KEYS = ("time_bridge", "semantic_bridge")
    for rel in ("app/services/inference.py", "app/api/graph.py"):
        py = PROJECT / "backend" / rel
        if not py.exists():
            continue
        try:
            tree = ast.parse(py.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                for kw in node.keywords:
                    if kw.arg in _FLAG_KEYS and isinstance(kw.value, ast.Constant):
                        problems.append(
                            f"{rel} 里 {kw.arg}={kw.value.value!r} 是硬编码，应按真实依据推导")
            elif isinstance(node, ast.Dict):
                for key, val in zip(node.keys, node.values):
                    if (isinstance(key, ast.Constant) and key.value in _FLAG_KEYS
                            and isinstance(val, ast.Constant)):
                        problems.append(
                            f"{rel} 里 {{\"{key.value}\": {val.value!r}}} 是硬编码，"
                            f"应按真实依据推导")

    # ---- ④ 并发敏感的单次初始化 / 单次构建必须加锁 ----
    #
    # 守的是一次实测出来的事故：模型是延迟加载的，而「先查标志、再加载、
    # 最后置标志」在加载期间完全不设防 —— 加载要十几秒，窗口极大。
    # 24 个并发请求触发了 24 次加载，进程峰值 8.1GB，最慢请求 67 秒。
    # 单用户也会碰到（前端首屏同时发多个请求），但从日志里根本看不出所以然，
    # 所以必须由体检挡住。
    lock_guards = [
        ("app/services/vector_engine.py", "_init_encoder", "_init_lock",
         "模型加载（几百 MB、十几秒）"),
        ("app/services/kb_index.py", "load_index", "_INDEX_LOCK",
         "知识库索引重建（每次约 60ms，且几乎每个 KB 端点都调）"),
    ]
    for rel, func_name, lock_name, what in lock_guards:
        py = PROJECT / "backend" / rel
        if not py.exists():
            continue
        try:
            tree = ast.parse(py.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):
            continue
        fns = {n.name: n for n in ast.walk(tree)
               if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
        fn = fns.get(func_name)
        if fn is None:
            problems.append(f"{rel} 里找不到 {func_name}")
            continue
        guarded = False
        for node in ast.walk(fn):
            if isinstance(node, (ast.With, ast.AsyncWith)):
                for item in node.items:
                    names = {x.id for x in ast.walk(item.context_expr)
                             if isinstance(x, ast.Name)}
                    if lock_name in names:
                        guarded = True
        if not guarded:
            problems.append(
                f"{rel} 的 {func_name} 没持有 {lock_name}"
                f"（{what}会被并发重做，危险且很难从日志看出来）")

    if problems:
        add("vector_wiring", "语义向量接线", FAIL, "；".join(problems[:4]),
            "降级编码要按字切词；embedding 与 embedding_meta 成对写；"
            "连线标记按依据推导；单次初始化/构建必须加锁")
    else:
        add("vector_wiring", "语义向量接线", OK,
            "降级编码中文按字切词有实证 · 向量与引擎指纹成对写入 · "
            "连线标记均由依据推导 · 模型加载与索引构建均有并发锁")


# ------------------------------------------------------------------ 主流程


def main() -> int:
    ap = argparse.ArgumentParser(description="知识图谱项目代码体检")
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    ap.add_argument("--build", action="store_true", help="附带跑一次前端生产构建（较慢）")
    args = ap.parse_args()

    check_syntax()
    ok, app = check_import()
    if ok and app is not None:
        check_routes(app)
        check_openapi(app)
    check_schema()
    check_fk_purge_coverage()
    check_silent_swallow()
    check_undefined_names()
    check_config()
    check_background_layers()
    check_security()
    check_vector_wiring()
    check_frontend()
    if args.build:
        check_frontend_build()

    errors = [r for r in ROWS if r["status"] == FAIL]
    warns = [r for r in ROWS if r["status"] == WARN]
    headline = ("体检通过，可以启动服务" if not errors and not warns
                else (f"{len(errors)} 项错误 / {len(warns)} 项警告" if errors
                      else f"{len(warns)} 项警告"))

    payload = {
        "ok": not errors,
        "headline": headline,
        "summary": {"total": len(ROWS), "errors": len(errors), "warnings": len(warns)},
        "rows": ROWS,
    }

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        width = max(len(r["title"]) for r in ROWS) + 2
        print("=" * 68)
        print("  知识图谱项目 · 代码体检")
        print("=" * 68)
        for r in ROWS:
            print(f"  {r['icon']} {r['title'].ljust(width)}{r['detail']}")
            if r["hint"] and r["status"] != OK:
                print(f"      → {r['hint']}")
        print("-" * 68)
        print(f"  {headline}")
        print("=" * 68)

    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
