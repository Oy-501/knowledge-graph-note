"""系统自检与前端错误回收（防御机制：可观测 + 早发现）

- ``GET  /api/system/doctor``        全量体检：环境/配置/数据库/schema 漂移/知识库/依赖/磁盘
- ``GET  /api/system/health-deep``   精简健康（给探活脚本用）
- ``POST /api/system/client-error``  前端崩溃回收入口 → 落操作审计，后台可查

设计原则：**每一项检查都独立 try**，任一失败只标记该行为 error/warn，
绝不让体检本身因为环境问题而 500 —— 否则这道防线本身就不可信。
"""
from __future__ import annotations

import os
import platform
import re
import shutil
import time
from typing import Any, Callable, Dict, List

from fastapi import APIRouter, Depends, Request
from loguru import logger
from pydantic import BaseModel, Field
from sqlalchemy import inspect
from sqlalchemy.orm import Session

from app.config import settings
from app.database import Base, engine, get_db
from app.services.errors import safe_detail
from app.services.security import verify_admin_token

router = APIRouter()

# backend/app/api/system.py → backend/ → 项目根
BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PROJECT_DIR = os.path.dirname(BACKEND_DIR)

OK, WARN, FAIL = "ok", "warn", "error"
_ICON = {OK: "✓", WARN: "!", FAIL: "✕"}


# ------------------------------------------------------------------ 单项检查封装


def _check(name: str, title: str, fn: Callable[[], Dict[str, Any]]) -> Dict[str, Any]:
    """跑一项检查。fn 返回 {status, detail, hint}；异常一律转成 error 行。"""
    t0 = time.perf_counter()
    try:
        res = fn() or {}
        row = {
            "name": name,
            "title": title,
            "status": res.get("status", OK),
            "detail": res.get("detail", ""),
            "hint": res.get("hint", ""),
        }
    except Exception as exc:  # noqa: BLE001 — 体检自身必须稳
        row = {
            "name": name,
            "title": title,
            "status": FAIL,
            "detail": f"检查项本身执行失败：{type(exc).__name__}: {exc}",
            "hint": "这通常意味着依赖缺失或环境异常，请先修复该项再继续。",
        }
    row["icon"] = _ICON.get(row["status"], "?")
    row["ms"] = round((time.perf_counter() - t0) * 1000, 1)
    return row


# ------------------------------------------------------------------ 各项检查实现


def _check_runtime() -> Dict[str, Any]:
    return {
        "status": OK,
        "detail": f"Python {platform.python_version()} · {platform.system()} {platform.release()} · "
                  f"{platform.machine()}",
    }


def _check_packages() -> Dict[str, Any]:
    """导出与推理的软依赖是否就绪（缺了不影响核心，但功能会降级）。"""
    optional = {
        "pptx": "PPTX 导出",
        "docx": "Word 导出",
        "sentence_transformers": "本地语义向量",
    }
    missing: List[str] = []
    for mod, label in optional.items():
        try:
            __import__(mod)
        except Exception:  # noqa: BLE001
            missing.append(f"{label}({mod})")
    required = {"fastapi": "FastAPI", "sqlalchemy": "SQLAlchemy", "loguru": "loguru"}
    broken = []
    for mod, label in required.items():
        try:
            __import__(mod)
        except Exception:  # noqa: BLE001
            broken.append(label)

    if broken:
        return {"status": FAIL, "detail": f"缺少必需依赖：{'、'.join(broken)}",
                "hint": "运行 `pip install -r backend/requirements.txt` 后重启。"}
    if missing:
        return {"status": WARN, "detail": f"可选依赖缺失：{'、'.join(missing)}（对应功能不可用）",
                "hint": "需要导出/本地向量时再安装即可，不影响其余功能。"}
    return {"status": OK, "detail": "必需与可选依赖均可用"}


def _check_config() -> Dict[str, Any]:
    """配置体检：默认口令、写保护、监听地址、阈值区间。"""
    issues, hints = [], []
    severe = False

    if settings.ADMIN_TOKEN in ("", "kg-admin", "change-me"):
        # 默认口令直接违反「默认安全」：出厂状态即可被猜中。
        # 这里按 error 级别上报（而非 warn），避免被当成可选优化长期忽略。
        issues.append("后台口令仍是默认值或为空（出厂即可被猜中）")
        hints.append("务必改 backend/.env 的 ADMIN_TOKEN 为强口令（12 位以上、非字典词）")
        severe = True

    if not getattr(settings, "PROTECT_WRITES", True):
        issues.append("写操作保护（PROTECT_WRITES）已关闭：任意可访问端口者都能删除/重建数据")
        hints.append("除非确认只在完全可信的本机单人使用，建议恢复 PROTECT_WRITES=true")
        severe = True

    if str(settings.HOST) not in ("127.0.0.1", "localhost"):
        issues.append(f"HOST={settings.HOST} 绑定到非回环地址，可能暴露到局域网")
        hints.append("如非需要外部访问，请改 HOST=127.0.0.1")

    for name, val, lo, hi in (
        ("VERDICT_AUTO_ACCEPT", settings.VERDICT_AUTO_ACCEPT, 0.5, 1.0),
        ("VERDICT_REJECT_BELOW", settings.VERDICT_REJECT_BELOW, 0.0, 0.5),
        ("LINK_TIME_BUDGET_S", settings.LINK_TIME_BUDGET_S, 1.0, 600.0),
        ("MAX_UPLOAD_MB_HARD", settings.MAX_UPLOAD_MB_HARD, 1, 4096),
    ):
        if not (lo <= val <= hi):
            issues.append(f"{name}={val} 超出合理区间 {lo}~{hi}")
            hints.append(f"请在 backend/.env 调整 {name}")

    if settings.VERDICT_REJECT_BELOW >= settings.VERDICT_AUTO_ACCEPT:
        issues.append("判定阈值倒挂：REJECT_BELOW 不应 ≥ AUTO_ACCEPT")
        hints.append("驳回阈值必须低于自动采纳阈值，否则全部进人工队列")

    if issues:
        return {"status": FAIL if severe else WARN,
                "detail": "；".join(issues), "hint": "；".join(hints)}
    return {"status": OK, "detail": f"后台口令已自定义 · 写保护已开启 · 判定阈值 "
                                    f"{settings.VERDICT_REJECT_BELOW}~{settings.VERDICT_AUTO_ACCEPT} · "
                                    f"DB 模式 {settings.DB_MODE}"}


def _check_uploads_dir() -> Dict[str, Any]:
    """检查上传目录可用性。

    刻意**不写探针文件再删除**：本机装有 fail-closed 的安全删除钩子，
    任何 os.remove 都可能被拦下（连删除自己刚创建的临时文件也会），
    于是「体检」自己变成报错项。改用无副作用的 os.access 判断。
    """
    root = settings.resolved_upload_dir
    os.makedirs(root, exist_ok=True)

    if not os.access(root, os.W_OK):
        return {"status": FAIL, "detail": f"目录不可写：{root}",
                "hint": "请检查目录权限，或在 backend/.env 改 UPLOAD_DIR 到可写路径。"}

    files = [f for f in os.listdir(root) if not f.startswith(".")]
    size_mb = sum(os.path.getsize(os.path.join(root, f)) for f in files
                  if os.path.isfile(os.path.join(root, f))) / 1024 / 1024

    # 与静态挂载路径一致性：不一致会导致「上传成功但访问 404」
    served = os.path.abspath(settings.resolved_upload_dir)
    if os.path.abspath(root) != served:
        return {"status": FAIL, "detail": f"写入目录与静态服务目录不一致：{root} vs {served}",
                "hint": "两者都应取自 settings.resolved_upload_dir。"}
    return {"status": OK,
            "detail": f"可读写 · {len(files)} 个文件 · {size_mb:.2f}MB · {root}"}


def _check_database(db: Session) -> Dict[str, Any]:
    from sqlalchemy import text as sql_text
    db.execute(sql_text("SELECT 1"))
    dialect = engine.dialect.name
    detail = f"可连接 · {dialect}"
    if dialect == "sqlite":
        path = settings.resolved_database_url.replace("sqlite:///", "", 1)
        p = path if os.path.isabs(path) else os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))), path.lstrip("./"))
        if os.path.exists(p):
            detail += f" · {os.path.getsize(p) / 1024 / 1024:.2f}MB · {p}"
    return {"status": OK, "detail": detail}


def _check_schema_drift() -> Dict[str, Any]:
    """模型 vs 实际库的列漂移 —— 能自动抓到「加了模型列却忘写迁移」这类错误。

    create_all 不会修改已存在的表，所以这类遗漏在运行期表现为
    `no such column`，非常难查。这里提前暴露。
    """
    insp = inspect(engine)
    existing = set(insp.get_table_names())
    missing_tables, missing_cols = [], []
    for table_name, table in Base.metadata.tables.items():
        if table_name not in existing:
            missing_tables.append(table_name)
            continue
        actual = {c["name"] for c in insp.get_columns(table_name)}
        for col in table.columns:
            if col.name not in actual:
                missing_cols.append(f"{table_name}.{col.name}")

    if missing_tables:
        return {"status": FAIL,
                "detail": f"缺表：{'、'.join(missing_tables[:6])}",
                "hint": "重启后端会由 create_all 自动建表。"}
    if missing_cols:
        return {"status": FAIL,
                "detail": f"缺列（{len(missing_cols)} 个）：{'、'.join(missing_cols[:8])}",
                "hint": "在 app/database.py 的 _COLUMN_MIGRATIONS 补 ALTER 语句后重启；"
                        "否则调用相关接口会报 no such column。"}
    total = sum(len(t.columns) for t in Base.metadata.tables.values())
    return {"status": OK,
            "detail": f"{len(Base.metadata.tables)} 张表 / {total} 列，与模型完全一致"}


def _check_knowledge_base(db: Session) -> Dict[str, Any]:
    from app.models.models import KnowledgeBase, KbRelation
    entries = db.query(KnowledgeBase).count()
    relations = db.query(KbRelation).count()
    if entries == 0:
        return {"status": FAIL, "detail": "知识库为空",
                "hint": "运行 `知识库.bat`（或 `py backend/scripts/kb_build.py`）重建。"}
    if relations == 0:
        return {"status": WARN, "detail": f"知识点 {entries} 条，但关系边为 0（关联会退化为无语义依据）",
                "hint": "运行 `py backend/scripts/kb_build.py --relations-only` 重建关系边。"}
    # 索引能否真正构建（这是图谱关联的前置条件）
    from app.services.kb_index import load_index
    idx = load_index(db)
    stats = idx.stats() if hasattr(idx, "stats") else {}
    return {"status": OK,
            "detail": f"知识点 {entries} · 关系边 {relations} · 可锚定实体 "
                      f"{stats.get('entities', entries)} · 别名 {stats.get('aliases', '—')}"}


def _check_data_files(db: Session) -> Dict[str, Any]:
    """数据一致性抽查：节点指向的文件是否还在、连线是否悬空。"""
    from app.models.models import File, Link, Node
    file_ids = {f.id for f in db.query(File.id).all()}
    node_rows = db.query(Node.id, Node.file_id).all()
    orphan_nodes = sum(1 for _, fid in node_rows if fid not in file_ids)
    node_ids = {nid for nid, _ in node_rows}
    link_rows = db.query(Link.source_id, Link.target_id).all()
    dangling = sum(1 for s, t in link_rows if s not in node_ids or t not in node_ids)

    problems = []
    if orphan_nodes:
        problems.append(f"{orphan_nodes} 个节点的所属文件已不存在")
    if dangling:
        problems.append(f"{dangling} 条连线指向已删除的节点")
    if problems:
        return {"status": WARN, "detail": "；".join(problems),
                "hint": "建议删除并重传相关文件，或在「知识库」页重建知识关联以清理残留。"}
    return {"status": OK,
            "detail": f"节点 {len(node_ids)} · 连线 {len(link_rows)}，无悬空引用"}


def _check_export_dir() -> Dict[str, Any]:
    # 直接复用导出服务里的目录常量，避免「体检看 A 目录、实际导出到 B 目录」
    from app.services.summary_export import EXPORT_DIR
    os.makedirs(EXPORT_DIR, exist_ok=True)
    files = os.listdir(EXPORT_DIR)
    size_mb = sum(os.path.getsize(os.path.join(EXPORT_DIR, f)) for f in files
                  if os.path.isfile(os.path.join(EXPORT_DIR, f))) / 1024 / 1024
    return {"status": OK if size_mb < 500 else WARN,
            "detail": f"可写 · {len(files)} 个产物 · {size_mb:.1f}MB",
            "hint": "产物超过 500MB 会变慢，可清理旧文件（系统自动保留最近 30 个）。"}


def _check_disk() -> Dict[str, Any]:
    usage = shutil.disk_usage(os.path.abspath("."))
    free_gb = usage.free / 1024 ** 3
    pct = usage.used / usage.total * 100
    status = OK if free_gb > 2 else (WARN if free_gb > 0.5 else FAIL)
    return {"status": status, "detail": f"剩余 {free_gb:.1f}GB（已用 {pct:.0f}%）",
            "hint": "空间不足会导致解析与导出失败，请清理。" if status != OK else ""}


def _check_frontend() -> Dict[str, Any]:
    fe = os.path.join(PROJECT_DIR, "kg-vue3")
    if not os.path.isdir(fe):
        return {"status": WARN, "detail": f"未找到前端目录：{fe}",
                "hint": "若前端不在 kg-vue3 目录，可忽略本项（后端可独立运行）。"}
    has_dist = os.path.isdir(os.path.join(fe, "dist"))
    has_modules = os.path.isdir(os.path.join(fe, "node_modules"))
    if not has_modules:
        return {"status": WARN, "detail": "前端依赖未安装",
                "hint": "在 kg-vue3 目录执行 `npm install`。"}
    return {"status": OK,
            "detail": f"目录正常 · 依赖已装 · 构建产物{'存在' if has_dist else '未生成（开发模式无需）'}"}


# ------------------------------------------------------------------ 端点

# 绝对路径（Windows 盘符 / POSIX），用于未授权访问时的脱敏
_ABS_PATH_RE = re.compile(r"(?:[A-Za-z]:[\\/][^\s\"'，；、]*|/(?:home|Users|root|var|opt)/[^\s\"'，；、]*)")


def _redact(text: str) -> str:
    """未授权访问时隐藏路径等环境细节（减少信息泄露 / 指纹信息）"""
    if not text:
        return text
    return _ABS_PATH_RE.sub("<路径已隐藏>", str(text))


@router.get("/doctor")
def doctor(request: Request, db: Session = Depends(get_db)):
    """一键体检：把「会出错的角落」逐项确认一遍。

    返回整体 ok 与逐项结果；前端可渲染成清单，明确告诉用户哪一项需要处理。

    **零信任**：本接口不因「来自本机」就信任调用方。未携带有效管理口令时，
    只返回状态与脱敏后的概要 —— 绝对路径（数据库位置、上传目录、导出目录）
    属于环境信息，泄露出去等于给攻击者提供定位与后续利用的线索。
    带口令调用（后台「系统自检」页签会自动携带）可获得完整细节与处理建议。
    """
    from app.services.audit import recent_stats

    checks = [
        _check("runtime", "运行环境", _check_runtime),
        _check("packages", "依赖完整性", _check_packages),
        _check("config", "关键配置", _check_config),
        _check("database", "数据库连接", lambda: _check_database(db)),
        _check("schema", "表结构一致性", _check_schema_drift),
        _check("knowledge_base", "知识库与索引", lambda: _check_knowledge_base(db)),
        _check("data_integrity", "数据一致性", lambda: _check_data_files(db)),
        _check("uploads", "上传目录", _check_uploads_dir),
        _check("exports", "导出目录", _check_export_dir),
        _check("disk", "磁盘空间", _check_disk),
        _check("frontend", "前端工程", _check_frontend),
    ]

    try:
        authorized = verify_admin_token(request.headers.get("X-Admin-Token"))
    except Exception:  # noqa: BLE001
        authorized = False

    if not authorized:
        # 未授权：隐藏绝对路径与平台指纹（这类信息等于帮攻击者做定位与选型）
        _NEUTRAL = {
            "runtime": "运行环境正常",
            "database": "数据库可连接",
            "disk": "磁盘可用",
        }
        for c in checks:
            c["detail"] = _NEUTRAL.get(c["name"], _redact(c.get("detail", "")))
            c["hint"] = ""      # 建议里可能含路径/命令，未授权时不返回
        checks = [{"name": c["name"], "title": c["title"], "status": c["status"],
                   "detail": c["detail"], "hint": "", "icon": c["icon"], "ms": c["ms"]}
                  for c in checks]

    failed = [c for c in checks if c["status"] == FAIL]
    warned = [c for c in checks if c["status"] == WARN]
    try:
        stats = recent_stats(db, days=7) if authorized else {}
    except Exception:  # noqa: BLE001
        stats = {}

    return {
        "ok": not failed,
        "authorized": authorized,
        "summary": {
            "total": len(checks),
            "passed": len(checks) - len(failed) - len(warned),
            "warnings": len(warned),
            "errors": len(failed),
            "headline": ("一切正常，可以放心使用" if not failed and not warned
                         else (f"{len(failed)} 项需要处理、{len(warned)} 项建议优化"
                               if failed else f"{len(warned)} 项建议优化")),
        },
        "checks": checks,
        "recent_activity": stats,
        "checked_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }


@router.get("/health-deep")
def health_deep(db: Session = Depends(get_db)):
    """精简探活：只关心「能不能干活」。"""
    out: Dict[str, Any] = {"status": "ok", "checks": {}}
    for key, fn in (
        ("database", lambda: _check_database(db)),
        ("schema", _check_schema_drift),
        ("knowledge_base", lambda: _check_knowledge_base(db)),
    ):
        try:
            res = fn()
            out["checks"][key] = {"status": res.get("status"), "detail": res.get("detail", "")}
            if res.get("status") == FAIL:
                out["status"] = "degraded"
        except Exception as exc:  # noqa: BLE001
            out["checks"][key] = {"status": "error", "detail": str(exc)[:200]}
            out["status"] = "degraded"
    return out


# ------------------------------------------------------------------ 前端错误回收


class ClientErrorIn(BaseModel):
    message: str = Field(default="", max_length=2000)
    stack: str = Field(default="", max_length=4000)
    source: str = Field(default="vue", max_length=64)   # vue | promise | api | manual
    route: str = Field(default="", max_length=200)
    component: str = Field(default="", max_length=200)
    info: str = Field(default="", max_length=500)
    user_agent: str = Field(default="", max_length=400)
    occurred_at: str = Field(default="", max_length=40)


@router.post("/client-error")
def report_client_error(payload: ClientErrorIn, request: Request,
                        db: Session = Depends(get_db)):
    """前端崩溃回收入口。

    前端 `app.config.errorHandler` / `unhandledrejection` 会把现场发到这里，
    写入操作审计 —— 这样「前端白屏了」不再是只在浏览器控制台里的秘密，
    后台管理能直接看到故障清单与复现路径。
    """
    from app.services.audit import log_event
    from app.services.security import client_error_limiter, client_key

    rid = getattr(request.state, "request_id", "")

    # 本接口免口令（报错时用户可能还没输过口令），因此必须限流：
    # 否则任何人都能持续写入审计表（默认上限 2 万行），
    # 既撑大数据库，也会把真正有用的审计记录挤掉。
    key = client_key(request)
    allowed, retry_after = client_error_limiter.check(key)
    if not allowed:
        return {"ok": False, "throttled": True, "retry_after": retry_after, "request_id": rid}
    client_error_limiter.hit(key)

    summary = f"[前端{payload.source}] {payload.message[:180] or '未知错误'}"
    log_event(
        db, "client_error", actor="client",
        target_type="frontend", target_name=payload.component or payload.route or "unknown",
        summary=summary, status="error",
        detail=safe_detail({
            "request_id": rid,
            "source": payload.source,
            "route": payload.route,
            "component": payload.component,
            "info": payload.info,
            "message": payload.message,
            "stack": payload.stack,
            "user_agent": payload.user_agent,
            "occurred_at": payload.occurred_at,
        }, limit=1500),
    )
    logger.warning(f"[{rid}] 前端错误上报：{summary}")
    return {"ok": True, "request_id": rid}
