"""认证与会话服务：注册/登录/登出、会话签发与滑动续期、初始化向导、依赖注入。

设计要点（对应架构 §1.1/§1.2 与共享知识第 1/2 条）：
- 密码用 bcrypt 哈希；会话是不透明令牌（kgt_ 前缀），库中只存 SHA-256 哈希
- 会话 7 天滑动续期：每次鉴权命中时 expires_at 顺延，登出/禁用即吊销
- 首个管理员走初始化向导：把 id 最小的既有用户行升格为管理员，
  旧数据（files/nodes/notes 的 user_id=1）天然归属，零迁移成本
- 各接口一律用 Depends(require_user) / Depends(require_admin) 取身份，
  禁止把 query 里的 user_id 当身份依据
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional, Tuple

import bcrypt
from fastapi import Depends, Request
from loguru import logger
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models.models import AuthSession, User, UserProfile
from app.services.errors import AppError
from app.services.security import (
    client_key, hash_token, login_limiter, new_session_token, token_hashes_equal,
)

SESSION_HEADER = "X-Session-Token"

# 用户名/密码的最小约束（本地应用，保持简单但挡住空值与超长）
_USERNAME_MIN, _USERNAME_MAX = 2, 32
_PASSWORD_MIN, _PASSWORD_MAX = 6, 72  # bcrypt 只取前 72 字节，超长直接拒绝更明确


# ---------------------------------------------------------------- 密码

def hash_password(password: str) -> str:
    """bcrypt 哈希（自带随机盐）"""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: Optional[str]) -> bool:
    """校验密码；哈希缺失或任何异常一律失败（fail-closed）"""
    if not password_hash:
        return False
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except Exception:  # noqa: BLE001 — 校验出错也必须拒绝
        return False


def _validate_credentials(username: str, password: str) -> Tuple[str, str]:
    """入库前的账号格式守卫"""
    username = (username or "").strip()
    if not (_USERNAME_MIN <= len(username) <= _USERNAME_MAX):
        raise AppError(f"用户名长度需在 {_USERNAME_MIN}~{_USERNAME_MAX} 字之间",
                       status_code=400, code="bad_username",
                       hint="用户名只用于登录与展示，2~32 个字符即可。")
    password = password or ""
    if not (_PASSWORD_MIN <= len(password) <= _PASSWORD_MAX):
        raise AppError(f"密码长度需在 {_PASSWORD_MIN}~{_PASSWORD_MAX} 位之间",
                       status_code=400, code="bad_password",
                       hint="请使用 6 位以上的密码。")
    return username, password


# ---------------------------------------------------------------- 初始化向导（首个管理员）

def need_bootstrap(db: Session) -> bool:
    """是否处于「未初始化」态：全库没有任何一行写了密码哈希"""
    return db.query(User).filter(User.password_hash.isnot(None)).count() == 0


def bootstrap(db: Session, username: str, password: str,
              display_name: str = "") -> Tuple[str, dict]:
    """初始化向导：把 id 最小的既有用户升格为首个管理员并签发会话。

    旧数据全部挂在 user#1 上（files/nodes/notes 外键），直接升格原行
    即可完成「承接」，不需要搬数据；若库中已有多行用户，按 id 最小者升格
    并在审计里留痕（共享知识：多用户行的处置约定）。
    """
    if not need_bootstrap(db):
        raise AppError("系统已完成初始化，请直接登录", status_code=403,
                       code="bootstrap_closed", hint="如需新账号请使用注册入口。")

    username, password = _validate_credentials(username, password)
    users = db.query(User).order_by(User.id.asc()).all()
    if not users:
        # 理论上启动时 ensure_default_user 已保证 user#1 存在，这里兜底
        user = User(username=username)
        db.add(user)
        db.flush()
    else:
        user = users[0]
    if user.username != username and db.query(User).filter(
            User.username == username, User.id != user.id).first():
        raise AppError("该用户名已被占用", status_code=409, code="username_taken",
                       hint="请换一个用户名。")

    user.username = username
    user.password_hash = hash_password(password)
    user.role = "admin"
    user.is_disabled = False
    if display_name:
        profile = db.query(UserProfile).filter_by(user_id=user.id).first()
        if not profile:
            profile = UserProfile(user_id=user.id)
            db.add(profile)
        profile.display_name = display_name[:100]
    db.commit()

    from app.services import audit
    audit.log_event(
        db, "bootstrap", actor="admin", user_id=user.id, target_type="user",
        target_id=user.id, target_name=user.username,
        summary=f"初始化向导：{user.username} 成为首个管理员",
        detail={"promoted_user_id": user.id, "other_user_rows": len(users) - 1},
    )
    token = issue_session(db, user.id)
    return token, user_public(db, user)


# ---------------------------------------------------------------- 注册 / 登录 / 登出

def register(db: Session, username: str, password: str) -> Tuple[str, dict]:
    """注册普通用户并签发会话"""
    if not settings.REGISTRATION_OPEN:
        raise AppError("当前未开放注册", status_code=403, code="registration_closed",
                       hint="请联系管理员在 backend/.env 打开 REGISTRATION_OPEN。")
    username, password = _validate_credentials(username, password)
    if db.query(User).filter(User.username == username).first():
        raise AppError("该用户名已被占用", status_code=409, code="username_taken",
                       hint="请换一个用户名，或直接登录。")
    user = User(username=username, password_hash=hash_password(password),
                role="user", is_disabled=False)
    db.add(user)
    db.commit()
    db.refresh(user)

    from app.services import audit
    audit.log_event(db, "register", actor="user", user_id=user.id,
                    target_type="user", target_id=user.id, target_name=username,
                    summary=f"新用户注册：{username}")
    token = issue_session(db, user.id)
    return token, user_public(db, user)


def login(db: Session, request: Optional[Request],
          username: str, password: str) -> Tuple[str, dict]:
    """登录：限流（10 次/5 分钟，键=用户名|IP）→ 校验 → 签发会话。

    用户不存在与密码错误返回同一句文案，不泄露「该用户名是否注册过」。
    """
    username = (username or "").strip()
    key = f"{username}|{client_key(request) if request is not None else 'unknown'}"
    allowed, retry_after = login_limiter.check(key)
    if not allowed:
        raise AppError(f"登录尝试过于频繁，请 {retry_after} 秒后重试",
                       status_code=429, code="login_rate_limited",
                       hint="连续失败会触发临时限制，稍后再试。",
                       detail={"retry_after": retry_after})

    user = db.query(User).filter(User.username == username).first()
    if not user or not verify_password(password, user.password_hash):
        login_limiter.hit(key)
        raise AppError("用户名或密码不正确", status_code=401, code="bad_credentials",
                       hint="请确认输入无误；连续失败 10 次会被临时限制。")
    if user.is_disabled:
        login_limiter.hit(key)
        raise AppError("该账号已被禁用", status_code=403, code="user_disabled",
                       hint="请联系管理员恢复。")

    login_limiter.reset(key)
    token = issue_session(db, user.id)
    from app.services import audit
    audit.log_event(db, "login", actor="user", user_id=user.id,
                    target_type="user", target_id=user.id, target_name=user.username,
                    summary=f"{user.username} 登录成功")
    return token, user_public(db, user)


# ---------------------------------------------------------------- 会话

def issue_session(db: Session, user_id: int) -> str:
    """签发会话：返回明文令牌（只出现这一次），库中只存 SHA-256 哈希"""
    token = new_session_token()
    now = datetime.utcnow()
    db.add(AuthSession(
        user_id=user_id,
        token_hash=hash_token(token),
        created_at=now,
        last_seen_at=now,
        expires_at=now + timedelta(days=settings.SESSION_TTL_DAYS),
        revoked=False,
    ))
    db.commit()
    return token


def resolve_session(db: Session, token: Optional[str]) -> Optional[AuthSession]:
    """按令牌解析有效会话；命中即滑动续期。任何不满足条件一律返回 None（fail-closed）。

    校验链：格式 → 哈希匹配（恒定时间）→ 未吊销 → 未过期 → 用户存在且未禁用。
    """
    if not token or not str(token).startswith("kgt_"):
        return None
    try:
        candidate_hash = hash_token(token)
        rows = db.query(AuthSession).filter(
            AuthSession.token_hash == candidate_hash).all()
        # unique 约束下最多一行；循环 + compare_digest 保持恒定时间比较语义
        session = None
        for row in rows:
            if token_hashes_equal(row.token_hash, candidate_hash):
                session = row
                break
        if session is None or session.revoked:
            return None
        now = datetime.utcnow()
        if session.expires_at and session.expires_at < now:
            return None
        user = db.query(User).filter_by(id=session.user_id).first()
        if not user or user.is_disabled:
            return None
        # 滑动续期：本地单机写放大可忽略
        session.expires_at = now + timedelta(days=settings.SESSION_TTL_DAYS)
        session.last_seen_at = now
        db.commit()
        return session
    except Exception as exc:  # noqa: BLE001 — 鉴权任何异常一律拒绝
        logger.warning(f"会话解析异常（按拒绝处理）：{exc}")
        try:
            db.rollback()
        except Exception:  # noqa: BLE001
            logger.debug("会话解析异常后的回滚也失败，忽略")
        return None


def revoke_session(db: Session, token: Optional[str]) -> bool:
    """吊销单个会话（登出）；幂等，找不到也算成功"""
    if not token:
        return False
    row = db.query(AuthSession).filter(
        AuthSession.token_hash == hash_token(token)).first()
    if row and not row.revoked:
        row.revoked = True
        db.commit()
        return True
    return False


def revoke_user_sessions(db: Session, user_id: int) -> int:
    """吊销某用户全部会话（禁用用户时即时踢出）"""
    count = (db.query(AuthSession)
             .filter(AuthSession.user_id == user_id, AuthSession.revoked.is_(False))
             .update({"revoked": True}, synchronize_session=False))
    db.commit()
    return count


# ---------------------------------------------------------------- 依赖注入

def require_user(request: Request, db: Session = Depends(get_db)) -> User:
    """FastAPI 依赖：取当前登录用户（新接口一律用它取身份）。

    同时把 user_id 写进 request.state，供中间件与审计使用。
    """
    session = resolve_session(db, request.headers.get(SESSION_HEADER))
    if session is None:
        raise AppError("需要登录", status_code=401, code="session_required",
                       hint="请先登录；若刚登录过，可能是会话已过期，请重新登录。")
    user = db.query(User).filter_by(id=session.user_id).first()
    if not user:
        raise AppError("需要登录", status_code=401, code="session_required",
                       hint="会话对应的用户不存在，请重新登录。")
    try:
        request.state.user_id = user.id
    except Exception:  # noqa: BLE001 — state 写不进去不影响鉴权结论
        logger.debug("写入 request.state.user_id 失败，忽略")
    return user


def require_admin(request: Request, db: Session = Depends(get_db)) -> User:
    """FastAPI 依赖：取当前登录的管理员（未登录 401、非管理员 403）"""
    user = require_user(request, db)
    if (user.role or "user") != "admin":
        raise AppError("需要管理员权限", status_code=403, code="admin_required",
                       hint="该操作仅管理员可用。")
    return user


def current_user_id(request: Request, fallback: int = 1) -> int:
    """过渡期兼容：旧接口仍收 query user_id 时，以中间件写入的会话用户覆盖"""
    try:
        uid = getattr(request.state, "user_id", None)
        if isinstance(uid, int) and uid > 0:
            return uid
    except Exception as exc:  # noqa: BLE001 — 取不到会话用户时降级回 fallback
        logger.debug(f"读取 request.state.user_id 失败: {exc}")
    return fallback


# ---------------------------------------------------------------- 出参

def user_public(db: Session, user: User) -> dict:
    """用户公开信息（任何接口不得回显 password_hash）"""
    profile = db.query(UserProfile).filter_by(user_id=user.id).first()
    return {
        "id": user.id,
        "username": user.username,
        "display_name": (profile.display_name if profile and profile.display_name
                         else user.username),
        "role": user.role or "user",
        "avatar_url": (profile.avatar_url if profile else "") or "",
        "created_at": user.created_at.isoformat() if user.created_at else None,
    }
