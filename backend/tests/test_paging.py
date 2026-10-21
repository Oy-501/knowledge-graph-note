"""分页参数守卫

守的是一类静默的安全问题：SQLite 里 `LIMIT -1` 等于**不限制行数**，
所以 `?limit=-1` 会把整张表返回给调用方。这不是「参数没写对」，
是数据外泄 + 慢查询，而且状态码还是 200，从响应上看不出异常。

所以这里既测纯函数，也测端点真实返回的**条数** —— 只看状态码区分不了
「被夹住了」和「整表泄漏」，两者都是 200。
"""
import pytest

from app.services.errors import clamp_paging


# ---------------------------------------------------------------- 纯函数

@pytest.mark.parametrize("limit,offset,expected", [
    (-1, 0, (30, 0)),          # 负数 → 回落默认值（关键用例）
    (-999, 0, (30, 0)),
    (0, 0, (30, 0)),           # 0 也按非法处理
    (5, 0, (5, 0)),
    (200, 0, (200, 0)),        # 正好等于上限
    (201, 0, (200, 0)),        # 超上限 → 夹到上限
    (999999, 0, (200, 0)),
    (10, -5, (10, 0)),         # 负数 offset 静默归零
    (10, 50, (10, 50)),
])
def test_clamp_paging_normalizes(limit, offset, expected):
    assert clamp_paging(limit, offset) == expected


@pytest.mark.parametrize("bad", ["abc", None, "", [], {}])
def test_clamp_paging_survives_type_errors(bad):
    """非数字不该抛异常 —— 分页参数属于「怎么给都能用」的参数。"""
    lim, off = clamp_paging(bad, 0)
    assert lim == 30 and off == 0


def test_clamp_paging_respects_custom_bounds():
    assert clamp_paging(-1, 0, max_limit=400, default_limit=200) == (200, 0)
    assert clamp_paging(9999, 0, max_limit=400, default_limit=200) == (400, 0)


def test_clamp_paging_never_returns_negative_limit():
    """不变式：任何输入都不能产出一个会让 SQLite 变成「不限行数」的 limit。"""
    for limit in (-10**9, -1, 0, 1, 10**9):
        lim, _ = clamp_paging(limit, 0)
        assert lim > 0, f"limit={limit} 产出了非正数 {lim}"


# ---------------------------------------------------------------- 端点行为

def test_entries_negative_limit_is_clamped_to_default(client, admin_headers):
    """`limit=-1` 必须被夹到默认值，而不是把整张表吐出来。"""
    total = client.get("/api/kb/stats", headers=admin_headers).json()["entries"]
    assert total > 60, "种子知识库太少，这条用例失去意义"

    r = client.get("/api/kb/entries?limit=-1", headers=admin_headers)
    assert r.status_code == 200
    items = r.json()["entries"]
    assert len(items) == 30, f"limit=-1 返回了 {len(items)} 条，未被夹到默认值 30"
    assert len(items) < total, "返回了整张表 —— 会泄漏数据且拖慢响应"


def test_entries_huge_limit_is_clamped_to_max(client, admin_headers):
    r = client.get("/api/kb/entries?limit=999999", headers=admin_headers)
    assert r.status_code == 200
    assert len(r.json()["entries"]) <= 200


def test_entries_zero_limit_falls_back(client, admin_headers):
    r = client.get("/api/kb/entries?limit=0", headers=admin_headers)
    assert r.status_code == 200
    assert len(r.json()["entries"]) == 30


def test_entries_huge_offset_returns_empty(client, admin_headers):
    r = client.get("/api/kb/entries?offset=1000000000", headers=admin_headers)
    assert r.status_code == 200
    assert r.json()["entries"] == []


def test_entries_bad_limit_type_is_422(client, admin_headers):
    r = client.get("/api/kb/entries?limit=abc", headers=admin_headers)
    assert r.status_code == 422, "类型错误应由 FastAPI 校验拦下，而不是进到业务层"
