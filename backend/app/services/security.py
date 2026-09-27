"""安全原语：会话令牌生成/哈希/恒定时间比较、失败限流、不可信请求头净化。

集中放在这里，避免各接口各写一遍校验逻辑 —— 分散实现必然出现遗漏，
而「某一个端点忘了加校验」正是零信任最怕的情形。

对应原则：
- **失效安全**：任何配置缺失/异常一律**拒绝**，绝不放行（fail-closed）
- **输入永不信任**：所有来自请求头的值都当作不可信，先净化再使用
- **零信任**：不因请求来自本机就信任，写操作一律校验登录会话
- **纵深防御**：令牌哈希比较用恒定时间算法，避免逐字符时序侧信道
"""
from __future__ import annotations

import hashlib
import hmac
import re
import secrets
import threading
import time
from collections import defaultdict, deque
from typing import Dict, Optional, Tuple

# 请求头净化：只允许这些字符，长度截断
_RID_SAFE = re.compile(r"[^A-Za-z0-9._:\-]")
_RID_MAX_LEN = 64


def sanitize_request_id(raw: Optional[str]) -> str:
    """净化外部传入的 X-Request-ID。

    请求头由客户端完全控制，若原样写入日志/审计，攻击者可以塞入换行符
    伪造日志行（日志注入），或塞入超长串撑爆日志与审计字段。
    这里只保留安全字符并截断长度；剔除后为空则视为未提供。
    """
    if not raw:
        return ""
    cleaned = _RID_SAFE.sub("", str(raw))[:_RID_MAX_LEN]
    return cleaned


# ---------------------------------------------------------------- 会话令牌

# 令牌格式：kgt_ + urlsafe 随机串（43 字符）；请求头 X-Session-Token
TOKEN_PREFIX = "kgt_"


def new_session_token() -> str:
    """签发一个新的不透明会话令牌（明文只出现在本次响应里，不落库）"""
    return TOKEN_PREFIX + secrets.token_urlsafe(32)


def hash_token(token: Optional[str]) -> str:
    """令牌的 SHA-256 哈希（库中只存哈希，泄库不等于泄令牌）"""
    return hashlib.sha256(str(token or "").encode("utf-8")).hexdigest()


def token_hashes_equal(a: str, b: str) -> bool:
    """恒定时间比较两个令牌哈希；任何异常一律拒绝（fail-closed）"""
    try:
        return hmac.compare_digest(str(a or ""), str(b or ""))
    except Exception:  # noqa: BLE001 — 比较出错也必须拒绝
        return False


class _SlidingLimiter:
    """进程内滑动窗口限流（按 key 计数）。

    用途：限制管理口令的失败尝试次数，把「无限次暴力破解」变成「有限次」。
    刻意保持简单（内存字典 + 双端队列），单机单进程场景足够；
    多进程部署时应换成 Redis 之类的共享存储。
    """

    def __init__(self, max_events: int = 20, window_s: float = 300.0):
        self.max_events = max_events
        self.window_s = window_s
        self._hits: Dict[str, deque] = defaultdict(deque)
        self._lock = threading.Lock()

    def _prune(self, key: str, now: float) -> deque:
        q = self._hits[key]
        cutoff = now - self.window_s
        while q and q[0] < cutoff:
            q.popleft()
        return q

    def check(self, key: str) -> Tuple[bool, int]:
        """是否允许本次尝试 → (allowed, retry_after_s)"""
        now = time.monotonic()
        with self._lock:
            q = self._prune(key, now)
            if len(q) >= self.max_events:
                retry_after = int(max(1, self.window_s - (now - q[0]))) if q else int(self.window_s)
                return False, retry_after
            return True, 0

    def hit(self, key: str) -> None:
        """记一次失败"""
        now = time.monotonic()
        with self._lock:
            self._prune(key, now)
            self._hits[key].append(now)

    def reset(self, key: str) -> None:
        """校验成功后清空计数"""
        with self._lock:
            self._hits.pop(key, None)

    def stats(self) -> Dict[str, int]:
        with self._lock:
            now = time.monotonic()
            return {k: len(self._prune(k, now)) for k in list(self._hits) if self._hits[k]}


# 登录失败限流：同一「用户名|客户端IP」5 分钟内最多 10 次（防在线暴力破解）
login_limiter = _SlidingLimiter(max_events=10, window_s=300.0)

# 后台管理口令失败限流：同一来源 5 分钟内最多 20 次（防在线暴力破解）
admin_limiter = _SlidingLimiter(max_events=20, window_s=300.0)

# 前端错误上报限流：同一来源 1 分钟最多 30 条（防止刷爆审计表）
client_error_limiter = _SlidingLimiter(max_events=30, window_s=60.0)


def client_key(request) -> str:
    """限流键：优先用客户端 IP。

    注意：反向代理场景下 request.client.host 可能是代理地址，
    因此这里**刻意不信任 X-Forwarded-For**（该头可被伪造，
    信任它等于允许攻击者通过伪造头绕过限流）。
    """
    try:
        host = request.client.host if request.client else "unknown"
    except Exception:  # noqa: BLE001
        host = "unknown"
    return host or "unknown"


# ---------------------------------------------------------------- 后台管理口令

def admin_token_configured() -> bool:
    """是否已配置后台管理口令（非空即视为已配置；默认值 kg-admin 也算已配置，
    用户实际可访问后台但需要带口令）。

    失效安全：配置缺失（空字符串/None）一律视为未配置，拒绝后台访问。
    """
    try:
        from app.config import settings
        return bool((settings.ADMIN_TOKEN or "").strip())
    except Exception:  # noqa: BLE001 — 配置读取失败必须拒绝
        return False


def verify_admin_token(token: Optional[str]) -> bool:
    """恒定时间比较 X-Admin-Token 与 settings.ADMIN_TOKEN。

    - 失效安全：未配置口令或令牌两端任一为空 → 拒绝
    - 不泄露口令长度/前缀（先哈希再 hmac.compare_digest）
    """
    try:
        from app.config import settings
        expected_raw = (settings.ADMIN_TOKEN or "").strip()
        if not expected_raw:
            return False
        if not (token or "").strip():
            return False
        return token_hashes_equal(hash_token(expected_raw), hash_token(token))
    except Exception:  # noqa: BLE001 — 比较过程任何异常都拒绝
        return False
