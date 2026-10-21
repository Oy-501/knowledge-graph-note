"""真实 socket 层的行为（起真 uvicorn 子进程，走真 TCP）

其余用例走 `TestClient`，它在 ASGI 层用内存传输（httpx 的 ASGITransport），
**完全不经过 TCP**。所以下面这些它永远测不到：

  · keep-alive 到底有没有真的复用同一条连接（HTTP/1.1 默认长连接、1.0 默认短连接）
  · 畸形请求行、裸连接不发数据就断开 —— 这是**连接层**的输入，不是 HTTP 语义层的
  · 慢客户端（连上后迟迟不发）会不会被误杀
  · 被连接层垃圾输入打过之后，服务还活着没有
  · 响应在 TCP 上的实际分帧（状态行 + CRLFCRLF + Content-Length）

这些行为由 uvicorn / h11 决定，不由应用代码决定。哪天换 ASGI 服务器
（uvicorn → hypercorn）、加前置反向代理、或调整启动参数，只有这里会响 ——
其余 119 条用例会全绿。

代价：要真起一个子进程，本模块约 3~6 秒。子进程刻意用 `VECTOR_BACKEND=tfidf`：
这里测的是连接层，没必要为它加载 470MB 模型。
"""
from __future__ import annotations

import http.client
import json
import os
import socket
import pathlib
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parent.parent

pytestmark = pytest.mark.socket_layer


# ---------------------------------------------------------------- 起服务

def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_ready(port: int, proc: subprocess.Popen, deadline: float = 40.0) -> None:
    end = time.time() + deadline
    last = ""
    while time.time() < end:
        if proc.poll() is not None:
            raise RuntimeError(f"子进程已退出（退出码 {proc.returncode}）")
        try:
            conn = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
            conn.request("GET", "/api/health")
            if conn.getresponse().status == 200:
                conn.close()
                return
            conn.close()
        except (OSError, http.client.HTTPException) as exc:
            last = f"{type(exc).__name__}: {exc}"
        time.sleep(0.25)
    raise TimeoutError(f"等待服务就绪超时；最后一次错误：{last}")


@pytest.fixture(scope="module")
def server():
    """起一个真的 uvicorn 子进程（独立端口、独立临时库），用完关掉。

    独立库很重要：这个子进程会跑 init_db + 灌种子知识库，
    绝不能落在正式库 `kg.db` 上。

    目录自己建（模块级夹具用不了函数级的 `workdir`），并且刻意不用 pytest 的
    `tmp_path_factory` —— 见 conftest 里 `workdir` 的说明：它会清理历史临时目录，
    而本机安全删除钩子会把整批删除拒掉，导致「测试全过、退出码却是失败」。
    """
    base = pathlib.Path(tempfile.gettempdir()) / "kg-pytest"
    base.mkdir(parents=True, exist_ok=True)
    workdir = pathlib.Path(tempfile.mkdtemp(prefix="socket_", dir=str(base)))

    port = _free_port()
    db_file = workdir / "socket.db"
    log_file = workdir / "uvicorn.log"

    env = dict(os.environ)
    env.update({
        "DB_MODE": "sqlite",
        "SQLITE_PATH": str(db_file),
        "VECTOR_BACKEND": "tfidf",   # 连接层测试不需要语义模型
        "PYTHONUNBUFFERED": "1",
    })

    with open(log_file, "w", encoding="utf-8") as log:
        proc = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "app.main:app",
             "--host", "127.0.0.1", "--port", str(port), "--log-level", "warning"],
            cwd=str(BACKEND), env=env,
            stdout=log, stderr=subprocess.STDOUT,
        )
        try:
            _wait_ready(port, proc)
        except Exception as exc:  # noqa: BLE001
            proc.kill()
            proc.wait(timeout=10)
            tail = log_file.read_text(encoding="utf-8", errors="replace")[-800:]
            pytest.skip(f"无法启动被测服务（{type(exc).__name__}: {exc}）；日志尾部：\n{tail}")

        yield port

        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=10)


# ---------------------------------------------------------------- 工具

def _raw(port: int, payload: bytes, timeout: float = 10.0) -> bytes:
    """发原始字节，读到对端关闭为止。只适合服务端会关连接的用法。"""
    with socket.create_connection(("127.0.0.1", port), timeout=timeout) as s:
        s.sendall(payload)
        s.settimeout(timeout)
        out = bytearray()
        while True:
            try:
                chunk = s.recv(65536)
            except socket.timeout:
                break
            if not chunk:
                break
            out.extend(chunk)
        return bytes(out)


def _health_status(port: int) -> int:
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    try:
        conn.request("GET", "/api/health")
        return conn.getresponse().status
    finally:
        conn.close()


def _status_line(raw: bytes) -> bytes:
    return raw.split(b"\r\n", 1)[0]


# ---------------------------------------------------------------- 正常往返

def test_real_http_round_trip(server):
    """最基础的一条：真的走过 TCP 也能拿到合法响应。

    TestClient 能过不代表这条能过 —— 它跳过了 TCP 与 HTTP 解析。
    """
    conn = http.client.HTTPConnection("127.0.0.1", server, timeout=10)
    try:
        conn.request("GET", "/api/health")
        resp = conn.getresponse()
        body = resp.read()
        assert resp.status == 200, f"状态码 {resp.status}"
        assert resp.getheader("content-type", "").startswith("application/json")
        # request_id 要真的落在响应头里（日志/审计/响应三处一致靠它串联）
        assert resp.getheader("x-request-id"), f"缺 x-request-id，响应头：{dict(resp.getheaders())}"
        assert isinstance(json.loads(body), dict)
    finally:
        conn.close()


def test_response_is_framed_correctly_on_the_wire(server):
    """响应必须在 TCP 上分帧正确：状态行 + CRLFCRLF + 明确的报文长度。

    真浏览器/代理靠 Content-Length（或 chunked）判断「一个响应到哪结束」。
    这条错了，表现是「有时候页面卡住不结束」，而应用日志里一切正常。
    """
    raw = _raw(server, b"GET /api/health HTTP/1.1\r\nHost: localhost\r\n"
                       b"Connection: close\r\n\r\n")
    assert raw.startswith(b"HTTP/1.1 "), f"状态行不合法：{raw[:80]!r}"
    head, sep, body = raw.partition(b"\r\n\r\n")
    assert sep, "响应头没有以 CRLFCRLF 结束"
    headers = head.decode("latin-1").lower()
    assert "content-length" in headers or "transfer-encoding" in headers, (
        f"既没有 Content-Length 也没有 chunked，客户端无法判断响应边界：{head[:200]!r}"
    )
    assert body, "响应体是空的"


# ---------------------------------------------------------------- 连接复用

def test_keep_alive_reuses_the_same_connection(server):
    """HTTP/1.1 默认长连接：连发两次必须复用同一条 TCP 连接。

    不能只断言「两次都 200」—— http.client 在对端关闭时会自己重连，
    照样 200，那样这条用例就成了摆设。要比 socket 身份。
    """
    conn = http.client.HTTPConnection("127.0.0.1", server, timeout=10)
    try:
        conn.request("GET", "/api/health")
        assert conn.getresponse().read()  # 读完才会回到可复用状态
        first = conn.sock
        assert first is not None, "第一次请求后连接就被关了"

        conn.request("GET", "/api/health")
        resp2 = conn.getresponse()
        assert resp2.status == 200
        resp2.read()
        assert conn.sock is first, (
            "第二次请求换了新 socket —— 长连接没有生效，每个请求都在重新握手"
        )
    finally:
        conn.close()


def test_keep_alive_assertion_has_teeth(server):
    """负向对照：服务端关闭连接时，上面那条「socket 身份」断言确实会失败。

    没有这条对照，`test_keep_alive_reuses_the_same_connection` 有可能是因为
    断言写松了而永远通过 —— 那种「假绿」比没有测试更误导。
    这里用 `Connection: close` 主动让服务端关连接，验证客户端确实会丢弃 socket。
    """
    conn = http.client.HTTPConnection("127.0.0.1", server, timeout=10)
    try:
        conn.request("GET", "/api/health", headers={"Connection": "close"})
        conn.getresponse().read()
        assert conn.sock is None, (
            "要求关闭连接后客户端仍复用了同一个 socket —— 说明身份断言无法区分"
            "「复用」与「不复用」，上面那条用例是假绿"
        )
    finally:
        conn.close()


def test_http10_closes_connection_by_default(server):
    """HTTP/1.0 默认短连接。这是协议规定，错了会让老客户端一直挂着等。"""
    raw = _raw(server, b"GET /api/health HTTP/1.0\r\n\r\n")
    assert raw.startswith(b"HTTP/1."), f"没有响应：{raw[:80]!r}"
    head = raw.split(b"\r\n\r\n", 1)[0].decode("latin-1").lower()
    assert "connection: close" in head, f"HTTP/1.0 没有声明关闭连接：{head[:200]}"


# ---------------------------------------------------------------- 连接层垃圾输入

def test_malformed_request_line_gets_400_and_server_survives(server):
    """畸形请求行必须被拒且**不拖垮服务**。

    这是连接层的输入 —— TestClient 构造不出它来（它会先在客户端侧报错）。
    在真实网络里，任何人都能往端口里灌这串字节。
    """
    raw = _raw(server, b"THIS IS NOT HTTP\r\n\r\n")
    assert b"400" in _status_line(raw), f"畸形请求行没有回 400：{raw[:120]!r}"
    assert _health_status(server) == 200, "服务被畸形请求打死了"


def test_garbage_bytes_do_not_kill_server(server):
    """纯二进制垃圾（不是文本）也要扛得住。"""
    for payload in (b"\x16\x03\x01\x00\xa5\x01\x00\x00a",   # 像是 TLS 握手
                    b"\x00" * 256,
                    bytes(range(256))):
        with socket.create_connection(("127.0.0.1", server), timeout=5) as s:
            s.sendall(payload)
        assert _health_status(server) == 200, f"服务被垃圾字节打死：{payload[:16]!r}"


def test_connect_and_disconnect_without_sending(server):
    """连上就断（端口扫描、健康探测的常见形态）不该留下任何副作用。"""
    for _ in range(5):
        with socket.create_connection(("127.0.0.1", server), timeout=5):
            pass
    assert _health_status(server) == 200


def test_partial_request_then_disconnect(server):
    """发半截请求就断开：服务不能卡在等剩余字节上。"""
    for payload in (b"GET /api/health HTTP/1.1\r\n",          # 只有请求行
                    b"GET /api/health HTTP/1.1\r\nHost: loc",  # 头没写完
                    b"POST /api/health HTTP/1.1\r\nHost: x\r\nContent-Length: 9999\r\n\r\n" + b"a" * 10):
        with socket.create_connection(("127.0.0.1", server), timeout=5) as s:
            s.sendall(payload)
        assert _health_status(server) == 200, f"服务卡在半个请求上：{payload[:40]!r}"


def test_slow_client_is_not_killed_before_sending(server):
    """连上后先想 2 秒再发，必须仍然被正常服务。

    这是在钉「连接建立后到首个字节之间没有激进的超时」——
    有的话，弱网或做代理探测的用户会随机失败，而服务端日志里什么都看不到。
    """
    with socket.create_connection(("127.0.0.1", server), timeout=30) as s:
        time.sleep(2.0)
        s.sendall(b"GET /api/health HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n\r\n")
        s.settimeout(10)
        buf = bytearray()
        while True:
            chunk = s.recv(65536)
            if not chunk:
                break
            buf.extend(chunk)
    assert b" 200 " in _status_line(bytes(buf)), f"慢客户端被拒了：{bytes(buf)[:120]!r}"


def test_server_still_serves_after_all_the_abuse(server):
    """所有连接层用例跑完后的收尾断言：服务还是好的。

    放在最后是有意的 —— 前面的用例只断言「自己那一下没打死服务」，
    这里断言的是「累积下来也没打死」，能抓到连接泄漏一类的慢性问题。
    """
    assert _health_status(server) == 200
    conn = http.client.HTTPConnection("127.0.0.1", server, timeout=10)
    try:
        conn.request("GET", "/api/health")
        resp = conn.getresponse()
        assert resp.status == 200 and json.loads(resp.read())["status"] == "ok"
    finally:
        conn.close()
