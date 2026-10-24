"""进程内 TTL 缓存：命中、过期、容量与接口级复用。"""
import time

from app.services.cache import TTLCache, api_cache


def test_set_and_get():
    cache = TTLCache(ttl=10)
    assert cache.get("a") is None
    cache.set("a", {"x": 1})
    assert cache.get("a") == {"x": 1}


def test_expires_after_ttl():
    cache = TTLCache(ttl=0.01)
    cache.set("a", 1)
    time.sleep(0.02)
    assert cache.get("a") is None


def test_maxsize_evicts():
    cache = TTLCache(ttl=10, maxsize=2)
    cache.set("a", 1)
    cache.set("b", 2)
    cache.set("c", 3)
    assert cache.stats()["size"] <= 2


def test_clear():
    cache = TTLCache()
    cache.set("a", 1)
    cache.clear()
    assert cache.get("a") is None


def test_stats_counts_hits_and_misses():
    cache = TTLCache()
    cache.get("x")
    cache.set("a", 1)
    cache.get("a")
    stats = cache.stats()
    assert stats["hits"] == 1
    assert stats["misses"] == 1


def test_kb_stats_is_cached(client, admin_headers):
    """同一份数据第二次读取应命中缓存，返回体一致。"""
    api_cache.clear()
    first = client.get("/api/kb/stats?user_id=1", headers=admin_headers)
    assert first.status_code == 200, first.text
    size_after_first = api_cache.stats()["size"]

    second = client.get("/api/kb/stats?user_id=1", headers=admin_headers)
    assert second.status_code == 200
    assert second.json() == first.json()
    assert api_cache.stats()["size"] == size_after_first
