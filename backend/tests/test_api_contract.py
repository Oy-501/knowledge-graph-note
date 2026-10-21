"""接口契约：错误信封、请求标识、HTTP 语义

这些是「前端能不能正确报错」的地基：

  · 每条响应都带 `X-Request-ID` —— 用户截图报错时，靠它把前端现象与后端日志对上
  · 错误体结构固定（ok / error.code / error.message / request_id / path / hint）——
    前端不必按端点猜错误格式
  · 4xx 要真的 4xx、5xx 才算服务端故障 —— 用户能据此区分「我填错了」和「服务坏了」

顺带钉住一条安全约定：**CORS 中间件必须在最外层**，否则守卫返回的 401
不带跨域头，浏览器只会报「无法连接后端服务」（而 curl 是正常的，
极易误判成后端没启动）。这里用「响应带 CORS 头」把这条约定固化下来。
"""
import pytest

WRITE_PATHS = [
    ("POST", "/api/kb/entries", {"entity": "_TEST_契约"}),
    ("POST", "/api/knowledge/infer", {}),
]


# ---------------------------------------------------------------- request_id

def test_every_response_carries_request_id(client, admin_headers):
    r = client.get("/api/health")
    assert r.headers.get("x-request-id"), "响应缺 X-Request-ID，出问题就无法与日志对齐"


def test_request_id_present_on_client_errors(client):
    """报错时更要有 request_id —— 这是用户报障时唯一的线索。"""
    r = client.post("/api/kb/entries", json={"entity": "_TEST_无凭证"})
    assert r.status_code == 401
    assert r.headers.get("x-request-id")
    assert r.json()["error"]["request_id"]


def test_request_id_present_on_404(client):
    r = client.get("/api/definitely/not/here")
    assert r.status_code == 404
    assert r.headers.get("x-request-id")


def test_client_supplied_request_id_is_echoed(client):
    """允许调用方自带 request_id（便于跨系统串联），但要净化后回显。"""
    r = client.get("/api/health", headers={"X-Request-ID": "abc123def"})
    assert r.headers.get("x-request-id") == "abc123def"


def test_malicious_request_id_is_sanitized(client):
    """带控制字符与路径分隔符的 request_id 必须被净化 —— 它会被写进日志与审计表。

    断言的是**真正的安全属性**（不能出现能用于路径穿越或日志注入的字符），
    而不是「某个字符集合一定不出现」。`.` 保留是安全的：没有斜杠就穿越不了。
    """
    r = client.get("/api/health", headers={"X-Request-ID": "../../etc/passwd\x00"})
    assert r.status_code == 200
    rid = r.headers.get("x-request-id", "")
    for bad in ("/", "\\", "\x00", "\r", "\n"):
        assert bad not in rid, f"request_id 未净化，含 {bad!r}：{rid!r}"


def test_sanitize_strips_crlf():
    """CRLF 必须剔除，否则可以在日志里伪造出一行新的日志记录（日志注入）。

    这条直接测函数：HTTP 客户端自身会拒绝发送含 CRLF 的头，
    走请求发不出去，测不到服务端行为。
    """
    from app.services.security import sanitize_request_id

    out = sanitize_request_id("abc\r\nX-Injected: yes")
    assert "\r" not in out and "\n" not in out, f"CRLF 未剔除：{out!r}"


def test_request_id_is_length_bounded(client):
    """超长 request_id 要截断，否则能撑爆日志与审计字段。"""
    from app.services.security import _RID_MAX_LEN

    r = client.get("/api/health", headers={"X-Request-ID": "a" * 5000})
    assert len(r.headers.get("x-request-id", "")) <= _RID_MAX_LEN


def test_request_id_whitelist_is_ascii_only():
    """记录净化器的既有白名单行为（`[A-Za-z0-9._:\\-]`）。

    走 HTTP 测不到这条：httpx / 浏览器按 HTTP 规范不接受非 ASCII 的头值，
    非 ASCII 的 request_id 在客户端就被拦下了，根本到不了服务端。
    所以这里直接测函数 —— 它才是真正会面对任意字节的那一层
    （手工拼原始报文的客户端能塞进 latin-1）。
    """
    from app.services.security import sanitize_request_id

    assert sanitize_request_id("正常-id_123") == "-id_123"
    assert sanitize_request_id("abc.def:ghi-jkl_123") == "abc.def:ghi-jkl_123"


# ---------------------------------------------------------------- 错误信封

@pytest.mark.parametrize("path", ["/api/definitely/not/here"])
def test_error_envelope_shape(client, path):
    r = client.get(path)
    body = r.json()
    assert body["ok"] is False
    err = body["error"]
    for key in ("code", "message", "request_id", "path"):
        assert key in err, f"错误信封缺字段 {key}：{err}"
    assert isinstance(err["message"], str) and err["message"]


def test_param_error_envelope(client, admin_headers):
    r = client.get("/api/kb/entries?limit=abc", headers=admin_headers)
    assert r.status_code == 422
    body = r.json()
    assert body["ok"] is False
    assert body["error"]["code"]


# ---------------------------------------------------------------- HTTP 语义

def test_unknown_path_is_404(client):
    assert client.get("/api/no/such/route").status_code == 404


def test_wrong_method_is_405(client, admin_headers):
    assert client.post("/api/health", json={}, headers=admin_headers).status_code == 405
    assert client.get("/api/files/upload", headers=admin_headers).status_code == 405


def test_malformed_json_is_422_not_500(client, admin_headers):
    r = client.post("/api/knowledge/infer", content=b"{not json",
                    headers={**admin_headers, "Content-Type": "application/json"})
    assert r.status_code in (400, 422), f"坏 JSON 应被拦成 4xx，实际 {r.status_code}"


def test_openapi_closed_in_non_debug(client):
    """生产（DEBUG=false）不暴露接口文档 —— 否则等于给攻击者一张地图。"""
    from app.config import settings

    if settings.DEBUG:
        pytest.skip("DEBUG=true 时接口文档是开着的，本用例只覆盖生产配置")
    for path in ("/docs", "/redoc", "/openapi.json"):
        assert client.get(path).status_code == 404, f"{path} 在生产配置下不应对外"


# ---------------------------------------------------------------- CORS 顺序（易错点）

def test_error_responses_carry_cors_headers(client):
    """守卫返回的 401 也必须带跨域头。

    CORS 中间件若不在最外层，401/500 会绕过它 —— 表现是
    **curl 一切正常、浏览器却报「无法连接后端服务」**，非常容易被误判成后端没启动。
    """
    r = client.post("/api/kb/entries", json={"entity": "_TEST_cors"},
                    headers={"Origin": "http://127.0.0.1:5173"})
    assert r.status_code == 401
    assert r.headers.get("access-control-allow-origin"), (
        "401 响应缺跨域头 —— 检查 main.py 里 CORSMiddleware 是否注册在所有 "
        "@app.middleware 之后（后注册者在外层）"
    )


def test_success_responses_carry_cors_headers(client):
    r = client.get("/api/health", headers={"Origin": "http://127.0.0.1:5173"})
    assert r.headers.get("access-control-allow-origin")


# ---------------------------------------------------------------- 关键端点存活

@pytest.mark.parametrize("path", [
    "/api/health",
    "/api/kb/stats",
    "/api/kb/entries?limit=5",
    "/api/kb/files",
    "/api/files/limits",
    "/api/admin/overview",
])
def test_core_read_endpoints_respond(client, admin_headers, path):
    r = client.get(path, headers=admin_headers)
    assert r.status_code == 200, f"{path} 返回 {r.status_code}: {r.text[:200]}"
