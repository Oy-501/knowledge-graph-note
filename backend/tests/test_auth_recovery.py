"""注册与「忘记密码」的安全边界。

这里守的是几条**看不出错但会致命**的规则：

1. 恢复码只存哈希 —— 库被拖走也不能直接换密码；
2. 错码与「用户不存在」返回同一句话 —— 否则这个匿名接口就是用户名枚举器；
3. 重置成功必须吊销全部会话 + 轮换恢复码 —— 改密的目的是「把别处踢下线」；
4. 只有管理员能创建账号 / 重置他人密码 —— 普通用户拿到这个口子等于接管全站。
"""
import re
import sqlite3

from app.config import settings

CODE_RE = re.compile(r"^[A-Z2-9]{4}(-[A-Z2-9]{4}){3}$")


def _register(client, name, password="Init#12345"):
    r = client.post("/api/auth/register", json={"username": name, "password": password})
    assert r.status_code == 200, r.text
    return r.json()


def _admin_create(client, headers, name, password="Init#12345", role="user"):
    r = client.post("/api/admin/users",
                    json={"username": name, "password": password, "role": role},
                    headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


# ---------------------------------------------------------------- 恢复码签发

def test_register_issues_a_recovery_code_but_stores_only_its_hash(client):
    """注册返回一次性恢复码；库里只有 bcrypt 哈希，明文不落盘。"""
    body = _register(client, "recovery_hash_probe")
    code = body["recovery_code"]
    assert CODE_RE.match(code), f"恢复码格式不对：{code!r}"

    # 直接查库确认明文没有落盘
    conn = sqlite3.connect(str(settings.SQLITE_PATH))
    try:
        row = conn.execute(
            "SELECT recovery_hash FROM users WHERE username = ?",
            ("recovery_hash_probe",)).fetchone()
    finally:
        conn.close()
    assert row and row[0], "恢复码没有写入 recovery_hash"
    assert row[0] != code, "恢复码被明文存进了数据库"
    assert row[0].startswith("$2"), f"不是 bcrypt 哈希：{row[0][:20]}"


def test_recovery_code_is_unique_per_issue(client):
    codes = {_register(client, f"recovery_unique_{i}")["recovery_code"] for i in range(3)}
    assert len(codes) == 3, "恢复码重复了 —— 随机源有问题"


# ---------------------------------------------------------------- 自助重置

def test_reset_with_recovery_rotates_the_code_and_the_password(client):
    body = _register(client, "reset_flow")
    old_code = body["recovery_code"]

    r = client.post("/api/auth/reset-password", json={
        "username": "reset_flow", "recovery_code": old_code,
        "new_password": "Brand#New99",
    })
    assert r.status_code == 200, r.text
    new_code = r.json()["recovery_code"]
    assert new_code != old_code, "重置后恢复码没有轮换"

    # 旧密码、旧恢复码双双失效
    assert client.post("/api/auth/login", json={
        "username": "reset_flow", "password": "Init#12345"}).status_code == 401
    assert client.post("/api/auth/reset-password", json={
        "username": "reset_flow", "recovery_code": old_code,
        "new_password": "Another#123"}).status_code == 401

    # 新密码、新恢复码可用
    ok = client.post("/api/auth/login", json={
        "username": "reset_flow", "password": "Brand#New99"})
    assert ok.status_code == 200, f"重置后的新密码登不进去：{ok.text[:200]}"


def test_recovery_code_ignores_case_and_separators(client):
    """手抄的码会有空格/小写 —— 校验的是同一串字符，不是格式。"""
    body = _register(client, "reset_lenient")
    messy = body["recovery_code"].lower().replace("-", " ")
    r = client.post("/api/auth/reset-password", json={
        "username": "reset_lenient", "recovery_code": messy,
        "new_password": "Lenient#123",
    })
    assert r.status_code == 200, f"宽松格式没通过：{r.text[:200]}"


def test_reset_revokes_every_existing_session(client):
    """重置后旧会话必须失效 —— 否则「改密把别处踢下线」这件事没做完。"""
    from app.services.auth_service import SESSION_HEADER

    body = _register(client, "reset_revoke")
    old_token = body["token"]
    h = {SESSION_HEADER: old_token}
    assert client.get("/api/auth/me", headers=h).status_code == 200

    r = client.post("/api/auth/reset-password", json={
        "username": "reset_revoke", "recovery_code": body["recovery_code"],
        "new_password": "Revoke#123",
    })
    assert r.status_code == 200, r.text

    assert client.get("/api/auth/me", headers=h).status_code == 401, \
        "重置密码后旧会话仍然有效"


# ---------------------------------------------------------------- 枚举防护

def test_wrong_code_and_unknown_user_are_indistinguishable(client):
    """两种失败必须回同一状态码与同一句话，否则就成了用户名枚举器。"""
    _register(client, "enum_target")

    wrong_code = client.post("/api/auth/reset-password", json={
        "username": "enum_target", "recovery_code": "AAAA-BBBB-CCCC-DDDD",
        "new_password": "Enum#12345",
    })
    unknown = client.post("/api/auth/reset-password", json={
        "username": "no_such_user_zzz", "recovery_code": "AAAA-BBBB-CCCC-DDDD",
        "new_password": "Enum#12345",
    })

    assert wrong_code.status_code == unknown.status_code == 401
    assert wrong_code.json()["error"]["code"] == unknown.json()["error"]["code"] == \
        "bad_recovery_code"
    assert wrong_code.json()["error"]["message"] == unknown.json()["error"]["message"]


# ---------------------------------------------------------------- 限流

def test_reset_attempts_are_rate_limited(client):
    """恢复码只有 80 bit 熵，但接口仍必须挡在线穷举。"""
    _register(client, "reset_ratelimit")
    statuses = [
        client.post("/api/auth/reset-password", json={
            "username": "reset_ratelimit",
            "recovery_code": f"AAAA-BBBB-CCCC-DDD{i}",
            "new_password": "Rl#123456",
        }).status_code
        for i in range(6)
    ]
    assert 429 in statuses, f"连续错码没有被限流：{statuses}"


# ---------------------------------------------------------------- 管理员兜底

def test_admin_can_create_user_and_reset_password(client, authed_headers):
    created = _admin_create(client, authed_headers, "made_by_admin")
    assert CODE_RE.match(created["recovery_code"]), created
    uid = created["user"]["id"]

    # 新账号能登录
    assert client.post("/api/auth/login", json={
        "username": "made_by_admin", "password": "Init#12345"}).status_code == 200

    r = client.post(f"/api/admin/users/{uid}/password",
                    json={"new_password": "Admin#Reset1"}, headers=authed_headers)
    assert r.status_code == 200, r.text
    assert CODE_RE.match(r.json()["recovery_code"])

    assert client.post("/api/auth/login", json={
        "username": "made_by_admin", "password": "Init#12345"}).status_code == 401
    assert client.post("/api/auth/login", json={
        "username": "made_by_admin", "password": "Admin#Reset1"}).status_code == 200


def test_regular_user_cannot_create_or_reset_users(client):
    """普通账号拿到这两个口子等于接管全站 —— 必须是 403。"""
    from app.services.auth_service import SESSION_HEADER

    body = _register(client, "plain_who_tries")
    h = {SESSION_HEADER: body["token"]}

    r1 = client.post("/api/admin/users",
                     json={"username": "sneaky", "password": "Sneaky#123"}, headers=h)
    assert r1.status_code == 403, f"普通用户能建号：{r1.status_code}"

    r2 = client.post("/api/admin/users/1/password",
                     json={"new_password": "Hacked#123"}, headers=h)
    assert r2.status_code == 403, f"普通用户能重置他人密码：{r2.status_code}"
