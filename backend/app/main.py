"""FastAPI 应用入口

防御机制（运行期兜底）落点：
  1. request_id 中间件 —— 每个请求一个可追溯 ID，同时出现在响应头/响应体/日志/审计
  2. 全局异常处理器 —— AppError / HTTPException / ValidationError / 兜底 Exception，
     任何情况都返回结构化 JSON，绝不出现裸 500 或空响应
  3. 5xx 落审计 —— 后台「操作审计」能看到服务端错误现场，报错不再只活在控制台
  4. 慢请求告警 —— 超过阈值的请求写日志，便于提前发现性能退化
"""
import sys
import os
import time
import uuid

# 确保 backend 目录在 Python 路径中
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
from loguru import logger
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.config import settings
from app.database import init_db, get_db
from app.seed import ensure_default_user, seed_knowledge_base
from app.services.kb_index import build_relations_from_entries
from app.services.errors import AppError, describe_exception, error_payload, safe_detail
from app.services.security import sanitize_request_id, verify_admin_token
from app.api import files, knowledge, graph, notes, kb, summary, admin, profile, system, auth

# 慢请求阈值（毫秒）：超过即在日志中标记，便于尽早发现性能退化
SLOW_REQUEST_MS = 3000

# 安全方法（不改变服务端状态）：写操作守卫只管其余方法
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}

# 写操作守卫的豁免清单。
# 每条例外都写明理由 —— 否则「忘了加保护」和「有意豁免」就区分不出来了。
WRITE_GUARD_EXEMPT = {
    # 前端崩溃上报通道：报错时用户可能还没输入过口令，若要求口令会出现
    # 「页面崩了 → 错误报不上去」的死角。改为免口令但严格限流。
    ("POST", "/api/system/client-error"),

    # ---- 登录类接口：登录页要能在「尚未登录」时被使用 ----
    # 不豁免的话 POST /api/auth/login 会被本守卫拦成 401（守卫只认令牌，
    # 而令牌正是登录接口要发给你的东西）—— 死锁，永远登不进去。
    # 这三条各自有守卫，不是无条件敞开：
    #   login      → 失败限流（同一「用户名|IP」5 分钟 10 次）
    #   register   → settings.REGISTRATION_OPEN 开关
    #   bootstrap  → 仅当全库没有任何用户写过密码哈希时才放行，之后永久 403
    ("POST", "/api/auth/login"),
    ("POST", "/api/auth/register"),
    ("POST", "/api/auth/bootstrap"),
}

# 「登录即可，不要求管理员」的写端点。
#
# 默认规则是「写操作需要**管理员**会话」，这两条是明确的例外：
# 普通用户也必须能退出登录、能改自己的密码，否则注册出来的账号是残废的。
# 它们自身仍有校验（logout 只吊销自己带的那个令牌；password 必须验原密码）。
WRITE_GUARD_USER_LEVEL = {
    ("POST", "/api/auth/logout"),
    ("POST", "/api/auth/password"),
}

# 后台自身已有更强的校验（恒定时间比较 + 失败限流），避免重复判定
WRITE_GUARD_PREFIX_EXEMPT = ("/api/admin/",)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    logger.info(f"Starting Knowledge Graph API... (DB: {settings.resolved_database_url.split('://')[0]})")
    init_db()

    # 幂等引导：默认用户 + 种子知识库（L0）+ 知识库关系边（本体）
    db = next(get_db())
    try:
        ensure_default_user(db)
        seed_result = seed_knowledge_base(db)
        logger.info(f"Seed knowledge base: {seed_result}")
        rel_result = build_relations_from_entries(db)
        logger.info(f"KB relations: {rel_result}")
    finally:
        db.close()

    logger.info("Database initialized.")
    yield
    logger.info("Shutting down...")


app = FastAPI(
    title="Knowledge Graph API",
    description="知识图谱笔记系统后端服务",
    version="1.0.0",
    lifespan=lifespan,
    # 攻击面最小化：交互式文档（/docs、/redoc）与 OpenAPI 描述会把
    # 全部接口、参数结构、模型定义无条件暴露出来，等于给攻击者一份地图。
    # 生产（DEBUG=False）默认关闭；需要调试时在 .env 设 DEBUG=true 再开。
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url="/redoc" if settings.DEBUG else None,
    openapi_url="/openapi.json" if settings.DEBUG else None,
)

# ============================================================ 中间件注册顺序（重要）
#
# Starlette 的 add_middleware 是「后注册者在外层」：
#   user_middleware[0] 最外层，执行顺序为 最后注册 → … → 最先注册
# 因此必须在**所有其他中间件注册完毕之后**再注册 CORS，让 CORS 处于最外层。
#
# 为什么这条顺序是关键：CORS 只给「经过它的响应」补 Access-Control-Allow-Origin。
# 如果 CORS 在内层，那么由外层中间件**短路生成**的响应（写操作被拒的 401、
# 兜底的 500）不会带上 CORS 头 —— 浏览器会直接判定为跨域失败，
# 前端只能看到 "Failed to fetch / 无法连接后端服务"，
# 而我们精心构造的错误信息（含 hint 与 request_id）用户一个字都看不到。
# 这个坑真实踩到过：接口用 curl 测完全正常，浏览器里却全是「连不上后端」。

# ============================================================ 写操作守卫

def _session_actor(request: Request):
    """从 `X-Session-Token` 解析出登录者，返回 `{id, username, role}` 或 None。

    中间件里拿不到 FastAPI 的依赖注入（Depends），所以这里自己开一个库会话、
    自己解析。三个要点：

    - **fail-closed**：任何异常、任何解析不出来的情况一律返回 None（当作未登录），
      绝不因为「读不出身份」就放行。
    - **不抛异常**：守卫里抛异常会让每个写请求都变成 500，
      把「拒绝」和「后端坏了」搅在一起，用户和日志都分不清。
    - **返回普通字典而不是 ORM 对象**：库里会话在 `finally` 会被 close，
      游离实例的属性访问时机不受控；顺手把需要的三个字段取出来最稳。
    """
    from app.database import SessionLocal
    from app.models.models import User
    from app.services import auth_service

    # 头名用常量而不是字符串字面量：这个头名在两个文件里各出现一次，
    # 改一处忘一处会让会话鉴权**静默失效**（不是报错，是「登录了也写不进去」）。
    # 体检的「登录门禁接线」会检查这里必须引用常量。
    token = request.headers.get(auth_service.SESSION_HEADER)
    if not token:
        return None

    db = SessionLocal()
    try:
        session = auth_service.resolve_session(db, token)
        if session is None:
            return None
        user = db.query(User).filter_by(id=session.user_id).first()
        if user is None or user.is_disabled:
            return None
        actor = {"id": user.id, "username": user.username, "role": user.role or "user"}
        # 让下游（current_user_id、审计）能读到本次身份
        try:
            request.state.user_id = actor["id"]
            request.state.username = actor["username"]
        except Exception:  # noqa: BLE001 — 上下文写不进去不影响鉴权结论
            logger.debug("写入 request.state 身份失败，忽略")
        return actor
    except Exception as exc:  # noqa: BLE001 — 鉴权任何异常都按未登录处理
        logger.warning(f"中间件解析会话失败（按未登录处理）：{exc}")
        try:
            db.rollback()
        except Exception:  # noqa: BLE001
            logger.debug("会话解析异常后的回滚也失败，忽略")
        return None
    finally:
        db.close()


@app.middleware("http")
async def write_guard(request: Request, call_next):
    """零信任 / 最小权限：所有改状态的操作都必须**登录为管理员**。

    为什么做成中间件而不是逐个端点加依赖：
    逐个加必然出现遗漏（本项目此前 30 多个写端点全部无保护，其中包含
    `DELETE /api/kb/entries/{id}` 与 `POST /api/kb/rebuild`），
    而中间件是一处集中判定 —— 新增端点默认受保护，「想豁免」必须显式写进
    WRITE_GUARD_EXEMPT 并说明理由。默认拒绝、按需开通。

    两种凭证，任一即可（强度相同，都不降低门槛）：
      ① `X-Session-Token` —— 登录页拿到的会话令牌，**要求 role=admin**
      ② `X-Admin-Token`   —— backend/.env 里的管理口令，留给脚本与 curl
    ②保留的原因：文档、体检脚本、命令行调试都在用它，去掉会平白打断既有用法；
    它本来就能做所有写操作，所以「支持①」并没有放宽任何东西。

    注册顺序说明：本中间件写在 request_context 之前，因此 request_context
    更外层、会先执行，被拒绝时响应里也能带上 request_id。
    """
    if not settings.PROTECT_WRITES or request.method in SAFE_METHODS:
        return await call_next(request)

    path = request.url.path
    if (request.method, path) in WRITE_GUARD_EXEMPT:
        return await call_next(request)
    if path.startswith(WRITE_GUARD_PREFIX_EXEMPT):
        return await call_next(request)

    actor = _session_actor(request)

    # ① 管理员：会话身份与旧口令任一满足即放行。
    #    两者放在一起判，是为了避免「已登录成普通用户、同时又持旧口令」
    #    这种组合被前面的会话判定提前拦死。
    if (actor and actor["role"] == "admin") \
            or verify_admin_token(request.headers.get("X-Admin-Token")):
        return await call_next(request)

    rid = getattr(request.state, "request_id", "") or uuid.uuid4().hex[:12]
    client = getattr(request.client, "host", "?")

    # ② 已登录但不是管理员：只有明确列进 WRITE_GUARD_USER_LEVEL 的端点放行
    #    （登出、改自己的密码 —— 否则注册出来的账号连退出都做不到）。
    #    这里必须放在 ① 之后、③ 之前：
    #    放在 ① 之前会让普通用户拿到本该管理员才能用的端点，
    #    放在 ③ 之后则永远轮不到（actor 不为 None 时已经在 ③ 之前的 403 里返回了）。
    if actor is not None and (request.method, path) in WRITE_GUARD_USER_LEVEL:
        return await call_next(request)

    # ③ 登录了但权限不够：这是「权限不足」，不是「没登录」，
    #    回 401 会误导前端把用户踢回登录页（他明明登录着）。回 403 更准确。
    if actor is not None:
        logger.warning(f"[{rid}] 拒绝越权写操作：{request.method} {path} "
                       f"(user={actor['username']}, role={actor['role']}, client={client})")
        return JSONResponse(
            status_code=403,
            content=error_payload(
                rid, "admin_required",
                f"该操作需要管理员权限（{request.method} {path}）",
                "当前账号是普通用户，只能查看数据。需要执行写操作请让管理员"
                "在「后台管理」把账号角色调整为 admin。", None, path),
        )

    # ④ 完全未登录：引导去登录页（而不是旧版的「输入管理口令」）
    logger.warning(f"[{rid}] 拒绝未登录写操作：{request.method} {path} (client={client})")
    return JSONResponse(
        status_code=401,
        content=error_payload(
            rid, "session_required",
            f"写操作需要先登录（{request.method} {path}）",
            "请先在登录页登录。登录一次后本机会记住会话，"
            "之后的写操作无需重复输入。", None, path),
    )


# ============================================================ 请求上下文中间件

@app.middleware("http")
async def request_context(request: Request, call_next):
    """为每个请求打上 request_id 并计时。

    - request_id 写入 scope["state"]，因此异常处理器（更外层）也能读到
    - 未捕获异常在此记录日志 + 落审计，并**直接返回结构化 500**
    - 不做任何可能失败的业务动作（日志失败也不影响请求）
    """
    rid = sanitize_request_id(request.headers.get("X-Request-ID")) or uuid.uuid4().hex[:12]
    try:
        request.state.request_id = rid
    except Exception as exc:  # noqa: BLE001 — 上下文写入失败不影响请求
        logger.debug(f"写入 request_id 到 request.state 失败：{exc}")

    t0 = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception as exc:  # noqa: BLE001
        cost_ms = int((time.perf_counter() - t0) * 1000)
        logger.error(
            f"[{rid}] {request.method} {request.url.path} 未捕获异常 "
            f"({type(exc).__name__}, {cost_ms}ms): {exc}"
        )
        _audit_server_error(request, exc, rid, cost_ms)

        # 为什么在这里出响应而不是上抛给全局 Exception 处理器：
        # 全局处理器挂在 ServerErrorMiddleware 上，那是比 CORS 更外层的位置，
        # 它生成的响应不会经过 CORS → 浏览器按跨域失败处理，
        # 用户只能看到「无法连接后端」，看不到 message/hint/request_id。
        # 在 CORS 内侧返回，结构化错误才能完整送达前端。
        # （全局 Exception 处理器保留为最后一道网，此处已是 CORS 内层。）
        info = describe_exception(exc)
        return JSONResponse(
            status_code=500,
            content=error_payload(
                rid, info["code"], info["message"], info["hint"],
                {"exception": type(exc).__name__, "raw": str(exc)[:300]},
                request.url.path,
            ),
        )

    cost_ms = int((time.perf_counter() - t0) * 1000)
    try:
        response.headers["X-Request-ID"] = rid
        response.headers["X-Elapsed-Ms"] = str(cost_ms)
    except Exception as exc:  # noqa: BLE001 — 响应头写入失败不影响响应体
        logger.debug(f"写入响应头失败：{exc}")

    if cost_ms >= SLOW_REQUEST_MS and request.url.path != "/api/health":
        logger.warning(f"[{rid}] 慢请求 {request.method} {request.url.path} 耗时 {cost_ms}ms")

    return response


# ============================================================ CORS（必须最后注册）

# 显式清单之外，再放行本机任意端口 —— 前端 vite dev server 在 5173 被占用时会自动换端口
# （5174/5175…），固定白名单会导致换端口后接口全被浏览器拦截。
#
# 注意：这里刻意放在**所有 @app.middleware 之后**。add_middleware 后注册者在外层，
# 放最后才能让 CORS 处于最外层，从而给「写操作守卫的 401」「兜底的 500」
# 这类由中间件直接生成的响应也补上跨域头。顺序写错会让前端只看到 "Failed to fetch"。
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID", "X-Elapsed-Ms"],
)


def _audit_server_error(request: Request, exc: BaseException, rid: str, cost_ms: int) -> None:
    """把未捕获异常写进操作审计，让「后台管理」能看见服务端错误现场。"""
    try:
        from app.services.audit import log_event
        info = describe_exception(exc)
        db = next(get_db())
        try:
            log_event(
                db, "server_error", actor="system",
                target_type="request",
                target_name=f"{request.method} {request.url.path}",
                summary=f"{info['message']}（{type(exc).__name__}）",
                status="error",
                duration_ms=cost_ms,
                detail={
                    "request_id": rid,
                    "method": request.method,
                    "path": request.url.path,
                    "query": safe_detail(dict(request.query_params)),
                    "exception": type(exc).__name__,
                    "error": str(exc)[:500],
                    "hint": info.get("hint", ""),
                },
            )
        finally:
            db.close()
    except Exception as audit_exc:  # noqa: BLE001 — 审计失败绝不能影响响应
        logger.warning(f"记录服务端错误审计失败：{audit_exc}")


# ============================================================ 全局异常处理器

def _rid_of(request: Request) -> str:
    try:
        return getattr(request.state, "request_id", "") or uuid.uuid4().hex[:12]
    except Exception:  # noqa: BLE001
        return uuid.uuid4().hex[:12]


@app.exception_handler(AppError)
async def handle_app_error(request: Request, exc: AppError):
    """业务异常：语义明确，直接把 message/hint 交给前端。"""
    rid = _rid_of(request)
    logger.info(f"[{rid}] 业务异常 {exc.code}: {exc.message}")
    return JSONResponse(
        status_code=exc.status_code,
        content=error_payload(rid, exc.code, exc.message, exc.hint, exc.detail,
                              request.url.path),
    )


@app.exception_handler(StarletteHTTPException)
async def handle_http_exception(request: Request, exc: StarletteHTTPException):
    """HTTP 异常：保持 `detail` 字段兼容老前端，同时补上统一结构。"""
    rid = _rid_of(request)
    if exc.status_code >= 500:
        logger.error(f"[{rid}] HTTP {exc.status_code} {request.url.path}: {exc.detail}")
    body = error_payload(rid, f"http_{exc.status_code}", str(exc.detail or ""),
                         "", None, request.url.path)
    body["detail"] = exc.detail  # 向后兼容
    return JSONResponse(status_code=exc.status_code, content=body,
                        headers=getattr(exc, "headers", None))


@app.exception_handler(RequestValidationError)
async def handle_validation_error(request: Request, exc: RequestValidationError):
    """参数校验失败：把 Pydantic 的错误列表翻成「哪个字段、错在哪」。"""
    rid = _rid_of(request)
    fields = []
    for err in (exc.errors() or [])[:10]:
        loc = " → ".join(str(x) for x in err.get("loc", []) if x not in ("body", "query"))
        fields.append({
            "field": loc or "(请求体)",
            "issue": err.get("msg", ""),
            "type": err.get("type", ""),
        })
    detail_text = "；".join(f"{f['field']}: {f['issue']}" for f in fields) or "参数不合法"
    logger.info(f"[{rid}] 参数校验失败 {request.url.path}: {detail_text[:200]}")
    return JSONResponse(
        status_code=422,
        content=error_payload(
            rid, "bad_params", f"请求参数不合法：{detail_text[:180]}",
            "请对照 detail.fields 逐项修正后重试。",
            {"fields": fields}, request.url.path,
        ),
    )


@app.exception_handler(Exception)
async def handle_unexpected(request: Request, exc: Exception):
    """最后一道网：任何未捕获异常都变成结构化 JSON，不让用户看到裸 500。"""
    rid = _rid_of(request)
    info = describe_exception(exc)
    logger.exception(f"[{rid}] 未捕获异常 {type(exc).__name__} @ {request.url.path}")
    return JSONResponse(
        status_code=500,
        content=error_payload(
            rid, info["code"], info["message"], info["hint"],
            {"exception": type(exc).__name__, "raw": str(exc)[:300]},
            request.url.path,
        ),
    )


# ============================================================ 路由注册

# 注册路由
app.include_router(system.router, prefix="/api/system", tags=["System"])
app.include_router(files.router, prefix="/api/files", tags=["Files"])
app.include_router(knowledge.router, prefix="/api/knowledge", tags=["Knowledge"])
app.include_router(graph.router, prefix="/api/graph", tags=["Graph"])
app.include_router(notes.router, prefix="/api/notes", tags=["Notes"])
app.include_router(kb.router, prefix="/api/kb", tags=["KnowledgeBase"])
app.include_router(summary.router, prefix="/api/summary", tags=["GraphSummary"])
app.include_router(admin.router, prefix="/api/admin", tags=["Admin"])
app.include_router(auth.router, prefix="/api/auth", tags=["Auth"])
app.include_router(profile.router, prefix="/api/profile", tags=["Profile"])

# 用户上传的图片（头像 / 背景）静态服务：/uploads/...
# 目录取 settings.resolved_upload_dir（单一事实来源），与 profile.py 的写入路径保持一致
_upload_root = settings.resolved_upload_dir
os.makedirs(_upload_root, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=_upload_root), name="uploads")


@app.get("/api/health")
async def health_check():
    return {"status": "ok", "version": "1.0.0"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host=settings.HOST, port=settings.PORT, reload=settings.DEBUG)
