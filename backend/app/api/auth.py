"""认证接口：初始化向导 / 登录 / 注册 / 登出 / 当前用户 / 修改密码。

这个文件负责把 `services/auth_service.py` 的能力暴露成 HTTP 接口。
在此之前服务层已经写好（bcrypt 口令、会话令牌、滑动续期、失败限流），
但没有任何路由引用它 —— 也就是说「登录页」缺的只有这一层接线。

为什么单独成文件而不并进 admin.py：
admin.py 的守卫是「管理口令」时代的产物（校验 X-Admin-Token），
而登录类接口必须在**未登录**时就能访问，两者职责不同，
混在一起会让「哪些端点匿名可达」变得难以看清。

安全约定
--------
- 匿名可达的只有 status / bootstrap / login / register 四个，
  且各自都有独立守卫：need_bootstrap()、REGISTRATION_OPEN、失败限流。
- 除 status 外的都写了审计（services/auth_service 负责），
  登录成功/失败、初始化、注册都会在「后台管理 → 操作审计」里留痕。
- 任何接口都不回显 password_hash（统一走 user_public）。
- 登录失败文案不区分「用户不存在」与「密码错误」，避免账号枚举。
"""
from typing import Optional

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models.models import User
from app.services import auth_service as auth
from app.services.errors import AppError

router = APIRouter()

# 会话令牌的请求头名（与 services/auth_service.SESSION_HEADER 同源，避免两处写两遍）
SESSION_HEADER = auth.SESSION_HEADER


# ---------------------------------------------------------------- 入参

class CredentialsPayload(BaseModel):
    """登录 / 注册 / 初始化共用的入参。

    刻意都给默认空串：缺字段时由 _validate_credentials 给出
    「用户名长度需在 2~32 字之间」这类可执行的提示，
    而不是让 FastAPI 抛 422 字段错误（用户看不懂 field/type 那套）。
    """
    username: str = ""
    password: str = ""
    display_name: str = ""


class ChangePasswordPayload(BaseModel):
    old_password: str = ""
    new_password: str = ""


# ---------------------------------------------------------------- 状态探测

@router.get("/status")
def auth_status(request: Request, db: Session = Depends(get_db)):
    """登录页的初始探测，**匿名可访问**。

    登录页需要靠它决定展示哪一种形态：
      need_bootstrap=true  → 初始化向导（设置首个管理员账号）
      否则未登录          → 登录表单（REGISTRATION_OPEN 时才显示注册入口）
      authenticated=true  → 直接把页面当已登录处理（刷新后免重复登录）

    顺带带上 user：前端刷新页面时可以一次请求同时拿到「是否已登录」与「我是谁」，
    不必先探测再请求 /me。
    """
    need = auth.need_bootstrap(db)

    # 已带有效会话时顺带返回用户信息。这里不强制要求令牌 —— 没带就当作未登录。
    user_info: Optional[dict] = None
    token = request.headers.get(SESSION_HEADER)
    if token:
        session = auth.resolve_session(db, token)
        if session is not None:
            user = db.query(User).filter_by(id=session.user_id).first()
            if user is not None:
                user_info = auth.user_public(db, user)

    return {
        "need_bootstrap": need,
        "registration_open": bool(settings.REGISTRATION_OPEN),
        "session_ttl_days": settings.SESSION_TTL_DAYS,
        "authenticated": user_info is not None,
        "user": user_info,
    }


# ---------------------------------------------------------------- 初始化向导

@router.post("/bootstrap")
def auth_bootstrap(payload: CredentialsPayload, db: Session = Depends(get_db)):
    """首次初始化：设置账号密码，并成为首个管理员。

    **匿名可访问**，但只在「全库没有任何一行写了密码哈希」时才允许 ——
    这个判定在 auth_service.bootstrap 里（need_bootstrap），
    初始化完成后本接口一律 403，不会变成永久敞开的后门。

    承接旧数据：既有 user#1 行会被直接升格（files/nodes/notes 都挂在
    user_id=1 上），因此不需要搬数据，历史内容天然归新管理员所有。
    """
    token, user = auth.bootstrap(db, payload.username, payload.password,
                                payload.display_name or "")
    return {
        "ok": True,
        "token": token,
        "user": user,
        "message": "初始化完成，已以管理员身份登录",
    }


# ---------------------------------------------------------------- 登录 / 注册 / 登出

@router.post("/login")
def auth_login(payload: CredentialsPayload, request: Request,
               db: Session = Depends(get_db)):
    """登录并签发会话令牌（**匿名可访问**，由 auth_service 内的失败限流保护）。"""
    token, user = auth.login(db, request, payload.username, payload.password)
    return {"ok": True, "token": token, "user": user}


@router.post("/register")
def auth_register(payload: CredentialsPayload, db: Session = Depends(get_db)):
    """注册普通用户（**匿名可访问**，但受 settings.REGISTRATION_OPEN 开关控制）。

    注册出来的是 role=user：能登录、能看数据，但**不能执行写操作**
    （写守卫要求管理员会话）。需要开通写权限请在「后台管理」调整角色。
    """
    token, user = auth.register(db, payload.username, payload.password)
    return {"ok": True, "token": token, "user": user}


@router.post("/logout")
def auth_logout(request: Request, db: Session = Depends(get_db)):
    """登出：吊销当前会话令牌（幂等，令牌无效也返回成功）。"""
    auth.revoke_session(db, request.headers.get(SESSION_HEADER))
    return {"ok": True, "message": "已退出登录"}


# ---------------------------------------------------------------- 当前用户

@router.get("/me")
def auth_me(request: Request, db: Session = Depends(get_db)):
    """当前登录用户信息（未登录 401，前端据此判断会话是否还有效）。"""
    user = auth.require_user(request, db)
    return {"ok": True, "user": auth.user_public(db, user)}


@router.post("/password")
def change_password(payload: ChangePasswordPayload, request: Request,
                    db: Session = Depends(get_db)):
    """修改自己的密码。

    改密必须同时提供**原密码** —— 光有会话令牌不够：
    令牌可能被留在别人能碰到的机器上，加上原密码才能挡住
    「拿到令牌就把账号彻底占领」。
    """
    user = auth.require_user(request, db)
    if not auth.verify_password(payload.old_password, user.password_hash):
        raise AppError("原密码不正确", status_code=401, code="bad_credentials",
                       hint="请填写当前正在使用的密码。")

    # 新密码同样要过格式校验（长度下限在这里兜住，避免改成 1 位数字）
    auth._validate_credentials(user.username, payload.new_password)
    user.password_hash = auth.hash_password(payload.new_password)
    db.commit()

    # 改完密码把**所有**会话吊销，包括当前这个 —— 让「改密」真正起到
    # 「把别处的登录踢下线」的作用。前端收到 re_login 后回到登录页重新登录。
    revoked = auth.revoke_user_sessions(db, user.id)

    from app.services import audit
    audit.log_event(db, "password_change", actor="user", user_id=user.id,
                    target_type="user", target_id=user.id, target_name=user.username,
                    summary=f"{user.username} 修改了密码，已吊销 {revoked} 个会话")

    return {
        "ok": True,
        "re_login": True,
        "revoked_sessions": revoked,
        "message": "密码已更新，请用新密码重新登录",
    }
