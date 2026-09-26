"""统一错误模型与「把异常翻译成人话」的映射层。

设计目标（防御机制第 2 层：运行期兜底）
--------------------------------------
1. **任何未捕获异常都不许变成裸 500**：统一交给 main.py 的异常处理器，
   返回结构化 JSON（含 request_id），前端能展示可读原因而不是白屏。
2. **每个错误都要带「下一步怎么办」**：按异常类型映射出可执行建议（hint），
   避免用户只看到 "Internal Server Error"。
3. **可追溯**：request_id 同时出现在响应、服务端日志与审计记录里，
   报错截图就能定位到具体一次请求。

约定：不在此模块做任何 I/O，保持纯函数，便于单测与复用。
"""
from __future__ import annotations

import re
import sqlite3
from typing import Any, Dict, Optional

# ---------------------------------------------------------------- 业务异常


class AppError(Exception):
    """带语义的业务异常：调用方可直接抛，由处理器转成结构化响应。

    用法::

        raise AppError("知识库索引未就绪", hint="请先运行 知识库.bat", status_code=503)
    """

    def __init__(
        self,
        message: str,
        *,
        status_code: int = 400,
        code: str = "app_error",
        hint: str = "",
        detail: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.code = code
        self.hint = hint
        self.detail = detail or {}


class NotFoundError(AppError):
    def __init__(self, what: str = "资源", hint: str = ""):
        super().__init__(f"{what}不存在", status_code=404, code="not_found",
                         hint=hint or "请确认该记录是否已被删除，或刷新列表后重试。")


class GuardError(AppError):
    """守卫拦截（限额、格式、状态不允许等）：属于「预期内的拒绝」。"""

    def __init__(self, message: str, *, status_code: int = 400,
                 code: str = "guard", hint: str = ""):
        super().__init__(message, status_code=status_code, code=code, hint=hint)


# ---------------------------------------------------------------- 异常 → 人话


# 顺序敏感：先匹配具体异常，再落到通用规则
_RULE_LIST = [
    # (异常类型名关键字, 错误码, 可读原因模板, 建议)
    ("JSONDecodeError", "bad_json",
     "请求体不是合法 JSON",
     "请检查请求体格式（引号、逗号、括号是否配对）。"),
    ("ValidationError", "bad_params",
     "请求参数不满足接口要求",
     "请对照错误明细中的字段逐项修正后重试。"),
    ("KeyError", "missing_key",
     "缺少必要字段",
     "该错误通常是请求体或数据库记录缺字段引起，请补齐后重试。"),
    ("IndexError", "out_of_range",
     "数据越界（访问了不存在的下标）",
     "这属于程序缺陷，已记录现场；请把本次操作与 request_id 一并反馈，便于定位。"),
    ("ZeroDivisionError", "div_zero",
     "计算时出现除零",
     "通常是某个统计分母为 0（如空图谱）；请先导入数据或调整参数。"),
    ("IntegrityError", "db_integrity",
     "数据库约束冲突（唯一键/外键/非空）",
     "可能存在重复记录或引用了已删除的数据；请检查后重试。"),
    ("OperationalError", "db_operational",
     "数据库不可用或被占用",
     "若提示 database is locked，说明有长事务在写库（如正在重建关联），等它跑完再试。"),
    ("FileNotFoundError", "file_missing",
     "文件不存在",
     "文件可能已被移动或删除；请重新上传或检查路径。"),
    ("PermissionError", "permission",
     "没有文件访问权限",
     "请确认该文件未被其他程序占用（Windows 上常见于 Excel 打开着 CSV）。"),
    ("UnicodeDecodeError", "bad_encoding",
     "文本编码无法识别",
     "请把文件另存为 UTF-8 后重新上传。"),
    ("TimeoutError", "timeout",
     "操作超时",
     "数据量可能过大，请在 .env 调大对应预算，或拆分文件后重试。"),
    ("ConnectionError", "net_unreachable",
     "网络连接失败",
     "请检查网络或代理；联网判定失败不会影响本地判定，可忽略。"),
]


def _type_chain_name(exc: BaseException) -> str:
    """返回异常类型链的名字（含 mro），用于模糊匹配，避免强依赖具体库。"""
    names = []
    for cls in type(exc).__mro__:
        names.append(cls.__name__)
    return "|".join(names)


# 报文关键字规则必须**先于**类型规则判定。
# 反例（真实踩到过）：sqlite3.OperationalError("no such column: nodes.foo")
# 会先命中类型规则里的 OperationalError → 被误报成「数据库被占用」，
# 而真实原因是「表结构不一致，去跑体检」。越具体的判断越要放前面。
_TEXT_RULES = (
    ("no such column", "schema_mismatch", "数据库结构与代码不一致",
     "运行 `体检.bat`（或 py backend/scripts/check.py）查看缺列，"
     "并在 database.py 的 _COLUMN_MIGRATIONS 补上 ALTER 语句。"),
    ("no such table", "schema_mismatch", "数据库缺少数据表",
     "重启后端即可由 create_all 自动建表；若仍报错请运行 `体检.bat` 查看详情。"),
    ("database is locked", "db_locked", "数据库被占用（写锁等待超时）",
     "通常有重建/解析任务正在写库，等它结束后重试；长期如此建议改用 PostgreSQL。"),
    ("unique constraint failed", "db_unique", "唯一约束冲突（记录已存在）",
     "系统已按幂等处理；若反复出现请检查是否重复提交。"),
    ("disk i/o error", "disk_io", "磁盘读写失败",
     "请检查磁盘空间与文件权限，必要时运行 `体检.bat` 查看磁盘项。"),
    ("out of memory", "oom", "内存不足",
     "当前处理的数据量超出内存；请拆分文件或调低 MAX_* 上限后重试。"),
)


def describe_exception(exc: BaseException) -> Dict[str, str]:
    """把异常翻译成 {code, message, hint}。

    纯函数、不抛异常 —— 兜底逻辑自身出错是最糟的情况，因此全程 try 包裹。
    判定顺序：先按报文关键字（最具体）→ 再按异常类型（较泛）。
    """
    try:
        text = str(exc).lower()
        for needle, code, message, hint in _TEXT_RULES:
            if needle in text:
                return {"code": code, "message": message, "hint": hint}

        chain = _type_chain_name(exc)
        for key, code, message, hint in _RULE_LIST:
            if key in chain:
                return {"code": code, "message": message, "hint": hint}

        return {"code": "internal", "message": "服务内部错误",
                "hint": "已记录现场。请带上 request_id 反馈，便于从审计日志还原调用链。"}
    except Exception:  # noqa: BLE001 — 兜底函数绝不能再抛
        return {"code": "internal", "message": "服务内部错误", "hint": ""}


# ---------------------------------------------------------------- 脱敏


_SENSITIVE_RE = re.compile(
    r"(token|password|passwd|secret|authorization|api[_-]?key)", re.IGNORECASE
)


def safe_detail(data: Optional[Dict[str, Any]], limit: int = 800) -> Dict[str, Any]:
    """裁剪并脱敏要回传给前端的细节，避免泄露令牌或撑爆响应体。"""
    if not data:
        return {}
    out: Dict[str, Any] = {}
    for k, v in list(data.items())[:20]:
        if _SENSITIVE_RE.search(str(k)):
            out[k] = "***"
            continue
        text = str(v)
        out[k] = text if len(text) <= limit else text[:limit] + "…"
    return out


def error_payload(
    request_id: str,
    code: str,
    message: str,
    hint: str = "",
    detail: Optional[Dict[str, Any]] = None,
    path: str = "",
) -> Dict[str, Any]:
    """统一错误响应体。前端只需读 detail.message / detail.hint 即可展示。"""
    body: Dict[str, Any] = {
        "ok": False,
        "error": {
            "code": code,
            "message": message,
            "request_id": request_id,
            "path": path,
        },
    }
    if hint:
        body["error"]["hint"] = hint
    clean = safe_detail(detail)
    if clean:
        body["error"]["detail"] = clean
    return body


# ---------------------------------------------------------------- 数据守卫


def require_text(value: Any, field: str, *, min_len: int = 1,
                 max_len: int = 4000) -> str:
    """入库前的文本守卫：类型 + 去空白 + 长度。

    用在「用户可控内容写库」的入口，避免 None/超长/空白字符串
    变成脏数据后在别处引发 IndexError / 渲染异常。
    """
    if value is None:
        raise GuardError(f"{field} 不能为空", code="empty_field",
                         hint=f"请在请求里带上 {field}。")
    if not isinstance(value, str):
        value = str(value)
    value = value.strip()
    if len(value) < min_len:
        raise GuardError(f"{field} 不能为空", code="empty_field",
                         hint=f"请在请求里带上 {field}。")
    if len(value) > max_len:
        raise GuardError(f"{field} 过长（{len(value)} 字，上限 {max_len}）",
                         code="too_long",
                         hint=f"请把 {field} 精简到 {max_len} 字以内。")
    return value


def require_int(value: Any, field: str, *, low: int = 0,
                high: int = 10 ** 9, default: Optional[int] = None) -> int:
    """整数守卫：容忍数字字符串，越界即拒绝（防止 LIMIT 100000000 这类拖库查询）。"""
    if value is None or value == "":
        if default is not None:
            return default
        raise GuardError(f"{field} 不能为空", code="empty_field")
    try:
        num = int(value)
    except (TypeError, ValueError) as exc:
        raise GuardError(f"{field} 必须是整数",
                         hint=f"收到的是 {value!r}。") from exc
    if num < low or num > high:
        raise GuardError(f"{field} 超出允许范围（{low}~{high}）",
                         code="out_of_range", hint=f"收到的是 {num}。")
    return num


def is_db_locked(exc: BaseException) -> bool:
    """判断是否是 SQLite 写锁冲突 —— 供调用方决定「重试一次」而非直接失败。"""
    if isinstance(exc, sqlite3.OperationalError):
        return "locked" in str(exc).lower()
    return "database is locked" in str(exc).lower()


def escape_like(value: Any) -> str:
    """转义 LIKE/ILIKE 的通配符。

    用户输入的 `%` 会被当成「匹配任意字符」、`_` 当成「匹配单个字符」，
    于是搜索 `%` 会命中全表、`a_b` 的匹配范围被悄悄放大 ——
    这属于「输入未被当作数据、而是被当成了语法」。
    转义后配合 `ESCAPE '\\'` 使用即可按字面量匹配。
    """
    text = "" if value is None else str(value)
    return (text.replace("\\", "\\\\")
                .replace("%", "\\%")
                .replace("_", "\\_"))


def clamp_paging(
    limit: Any,
    offset: Any = 0,
    *,
    max_limit: int = 200,
    default_limit: int = 30,
) -> tuple:
    """分页参数守卫，返回 (limit, offset)。

    为什么需要它：各接口此前只写 `min(limit, 200)`，**没有防负数**。
    而 SQLite 的语义是「LIMIT 为负数 = 不限制行数」，
    于是 `?limit=-1` 会把整张表（例如上万条审计日志）一次返回给客户端 ——
    既慢又可能造成数据外泄。OFFSET 负数则被静默当成 0。

    这里把非法值收敛到安全区间而不是报错：分页参数属于「怎么给都能用」的参数，
    静默收敛比让用户看到 400 更友好；越界也只在服务端收敛，不改变正常调用行为。
    """
    try:
        lim = int(limit)
    except (TypeError, ValueError):
        lim = default_limit
    try:
        off = int(offset)
    except (TypeError, ValueError):
        off = 0
    if lim <= 0:
        lim = default_limit
    if off < 0:
        off = 0
    return min(lim, max_limit), off
