"""写守卫与认证语义

守的是三个「模型对但很容易写错」的点，每个都对应一类真实事故：

  1. **豁免名单漏了登录端点** → 写守卫把 login 自己拦死 → 永远登不进去
  2. **401 / 403 混用** → 已登录但权限不够却回 401 → 前端把人踢回登录页
  3. **失效不关闭（fail-closed）** → 口令没配置就放行 → 等于门户大开
"""
import pytest

from app.services.security import verify_admin_token


# ---------------------------------------------------------------- fail-closed（纯函数）

def test_verify_admin_token_rejects_when_unconfigured(monkeypatch):
    """口令未配置时必须**拒绝**，不能因为「没配置就等于不校验」而放行。"""
    from app.config import settings

    monkeypatch.setattr(settings, "ADMIN_TOKEN", "")
    assert verify_admin_token("anything") is False
    assert verify_admin_token(None) is False


def test_verify_admin_token_rejects_empty_token(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "ADMIN_TOKEN", "real-token")
    assert verify_admin_token("") is False
    assert verify_admin_token(None) is False
    assert verify_admin_token("   ") is False


def test_verify_admin_token_accepts_correct(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "ADMIN_TOKEN", "real-token")
    assert verify_admin_token("real-token") is True
    assert verify_admin_token("wrong") is False


# ---------------------------------------------------------------- 写守卫

def test_write_without_credentials_is_unauthorized(client):
    r = client.post("/api/kb/entries", json={"entity": "_TEST_无凭证"})
    assert r.status_code == 401
    body = r.json()
    assert body["ok"] is False
    assert body["error"]["code"] == "session_required", body


def test_write_with_wrong_token_is_unauthorized(client):
    r = client.post("/api/kb/entries", json={"entity": "_TEST_错口令"},
                    headers={"X-Admin-Token": "definitely-wrong"})
    assert r.status_code == 401


def test_write_with_valid_token_succeeds(client, admin_headers):
    r = client.post("/api/kb/entries", json={"entity": "_TEST_合法写入"},
                    headers=admin_headers)
    assert r.status_code == 200, r.text
    assert r.json()["ok"] is True


def test_read_endpoints_need_no_credentials(client):
    """读接口不该要求凭证，否则登录页自己都拿不到 /auth/status。"""
    assert client.get("/api/health").status_code == 200
    assert client.get("/api/auth/status").status_code == 200


def test_login_endpoint_is_exempt_from_write_guard(client):
    """登录端点必须在写守卫的豁免名单里，否则会形成「永远登不进去」的死锁。

    怎么区分「被守卫拦下」和「守卫放行、但凭证不对」？两者都是 401，
    看错误码：守卫拦下是 `session_required`，凭证错是 `bad_credentials`。
    """
    r = client.post("/api/auth/login", json={"username": "nobody", "password": "nope"})
    assert r.status_code == 401
    assert r.json()["error"]["code"] != "session_required", (
        "登录端点被写守卫拦下了 —— 这正是「永远登不进去」的死锁，"
        "应把 /api/auth/login 加进 WRITE_GUARD_EXEMPT"
    )


def test_register_endpoint_is_exempt(client):
    r = client.post("/api/auth/register",
                    json={"username": "nobody2", "password": "Nope#12345"})
    assert r.json().get("error", {}).get("code") != "session_required"


def test_authed_session_can_write(client, authed_headers):
    """生产主通道：登录会话（X-Session-Token）也能通过写守卫。"""
    r = client.post("/api/kb/entries", json={"entity": "_TEST_会话写入"},
                    headers=authed_headers)
    assert r.status_code == 200, r.text


# ---------------------------------------------------------------- 401 与 403 不能混用

def test_non_admin_session_gets_403_not_401(client, authed_headers):
    """已登录但权限不足必须回 403。

    回 401 的后果：前端会认为「会话过期了」，把用户踢回登录页 ——
    而用户明明刚登录成功，表现为「一操作就退出登录」。
    """
    # 先确保管理员已初始化（authed_headers 会做），再注册一个普通账号
    reg = client.post("/api/auth/register",
                      json={"username": "plainuser", "password": "Plain#12345"})
    assert reg.status_code == 200, reg.text

    login = client.post("/api/auth/login",
                        json={"username": "plainuser", "password": "Plain#12345"})
    assert login.status_code == 200, login.text
    token = login.json().get("token") or login.json().get("session_token")
    assert token

    r = client.post("/api/kb/entries", json={"entity": "_TEST_越权"},
                    headers={"X-Session-Token": token})
    assert r.status_code == 403, (
        f"普通用户越权应回 403（不是 401，否则前端会把用户踢回登录页），实际 {r.status_code}"
    )
    assert r.json()["error"]["code"] == "admin_required"


def test_non_admin_session_gets_403_on_admin_pages_too(client, authed_headers):
    """后台页面的只读接口同样必须回 403。

    **这是两条独立的守卫，上面那条只覆盖了其中一条。**
      · 写守卫（`main.py`）—— 管 POST/PUT/PATCH/DELETE，回 403 ✔（上一条用例）
      · 后台路由守卫（`api/admin.py` 的 `require_admin`）—— 管整个 `/api/admin/*` 前缀，
        曾经**一律回 401**，于是已登录的普通用户点开「后台管理」看到的是
        「请在登录页登录管理员账号」，而他明明登录着 —— 真正的原因是权限不够。
    两条守卫都叫「管理员校验」，却给出不同的答案，所以必须各有一条用例钉住。
    """
    reg = client.post("/api/auth/register",
                      json={"username": "plainuser2", "password": "Plain#12345"})
    assert reg.status_code == 200, reg.text
    login = client.post("/api/auth/login",
                        json={"username": "plainuser2", "password": "Plain#12345"})
    assert login.status_code == 200, login.text
    token = login.json().get("token") or login.json().get("session_token")
    h = {"X-Session-Token": token}

    # 先确认令牌真的有效（否则下面测的是「未登录」而不是「已登录但权限不够」）
    assert client.get("/api/auth/me", headers=h).status_code == 200

    for path in ("/api/admin/auth", "/api/admin/overview", "/api/admin/audit?limit=5"):
        r = client.get(path, headers=h)
        assert r.status_code == 403, (
            f"{path} 对已登录的普通用户回了 {r.status_code}，应为 403"
        )
        assert r.json()["error"]["code"] == "admin_required", r.text

    # 反向：完全没有凭证时仍必须是 401（别把「未登录」也一并改成 403）
    anon = client.get("/api/admin/overview")
    assert anon.status_code == 401, f"匿名访问后台应回 401，实际 {anon.status_code}"
    # 错误码也要与写守卫一致：前端 isSessionExpired / isForbidden 判的是**码**不是状态码。
    # 后台守卫曾回通用的 http_401 / http_403，前端两个判定都不认。
    assert anon.json()["error"]["code"] == "session_required", anon.text


def test_normal_user_can_still_logout(client, authed_headers):
    """登出与改自己密码只要求「已登录」。

    这条是从实测里抓出来的：第一版把登出也列进「仅管理员」，
    于是注册出来的普通账号连退出都做不到。
    """
    reg = client.post("/api/auth/register",
                      json={"username": "logoutuser", "password": "Logout#12345"})
    assert reg.status_code == 200, reg.text
    login = client.post("/api/auth/login",
                        json={"username": "logoutuser", "password": "Logout#12345"})
    token = login.json().get("token") or login.json().get("session_token")

    r = client.post("/api/auth/logout", headers={"X-Session-Token": token})
    assert r.status_code == 200, f"普通账号无法登出：{r.status_code} {r.text}"


def test_normal_user_can_personalize_profile(client, authed_headers):
    """个人空间（昵称 / 头像 / 背景）登录即可，**不要求管理员**。

    这条对着一个真实的产品判断：把背景换色也挂到管理员门槛上，
    普通账号连「换个背景」都会被 403 挡住，而它既不改变知识内容，
    也不影响他人可见状态。权限边界应当是「改知识要管理员，改自己的外观不要」。

    同时反向守住：内容类写操作仍然必须是 403 —— 别把「放开个人空间」
    顺手做成「放开所有写操作」。
    """
    reg = client.post("/api/auth/register",
                      json={"username": "plainprofile", "password": "Plain#12345"})
    assert reg.status_code == 200, reg.text
    login = client.post("/api/auth/login",
                        json={"username": "plainprofile", "password": "Plain#12345"})
    token = login.json().get("token") or login.json().get("session_token")
    h = {"X-Session-Token": token}

    # ① 能改自己的资料与背景参数
    r = client.put("/api/profile", json={
        "display_name": "普通用户",
        "bio": "只改自己的东西",
        "background_config": {"preset": "paper", "opacity": 0.2},
    }, headers=h)
    assert r.status_code == 200, f"普通用户改自己的资料被拦：{r.status_code} {r.text}"

    # 配置真的落库了（不是「返回 200 但其实没存」）
    got = client.get("/api/profile", headers=h).json()
    prof = got.get("profile", got)
    assert prof.get("background_config", {}).get("preset") == "paper", prof

    # ② 反向：知识内容的写操作仍然只有管理员能做
    deny = client.post("/api/kb/entries", json={"entity": "_TEST_仍然越权"}, headers=h)
    assert deny.status_code == 403, f"普通用户写知识仍应 403，实际 {deny.status_code}"


# ---------------------------------------------------------------- 凭证不泄漏

def test_auth_status_does_not_leak_password_hash(client):
    body = client.get("/api/auth/status").text
    for leak in ("password_hash", "$2b$", "bcrypt"):
        assert leak not in body, f"/auth/status 泄漏了 {leak}"


def test_error_body_does_not_echo_the_submitted_token(client):
    secret = "super-secret-token-value"
    r = client.post("/api/kb/entries", json={"entity": "_TEST_回显"},
                    headers={"X-Admin-Token": secret})
    assert r.status_code == 401
    assert secret not in r.text, "错误响应里回显了提交的凭证"
