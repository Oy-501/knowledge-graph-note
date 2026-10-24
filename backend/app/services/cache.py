"""进程内 TTL 缓存：读接口短缓存，写操作后整体失效。

只缓存「可由数据库重建」的结果，不缓存会话/权限，避免越权读到别人的数据。
"""
import threading
import time
from typing import Any, Dict, Optional


class TTLCache:
    """线程安全的定长 TTL 缓存。"""

    def __init__(self, ttl: float = 30.0, maxsize: int = 128):
        self.ttl = ttl
        self.maxsize = maxsize
        self._data: Dict[str, tuple] = {}
        self._lock = threading.Lock()
        self._hits = 0
        self._misses = 0

    def get(self, key: str) -> Optional[Any]:
        """取值；过期或不存在返回 None。"""
        now = time.monotonic()
        with self._lock:
            item = self._data.get(key)
            if item is None:
                self._misses += 1
                return None
            value, expire_at = item
            if expire_at <= now:
                self._data.pop(key, None)
                self._misses += 1
                return None
            self._hits += 1
            return value

    def set(self, key: str, value: Any) -> None:
        """写入并续期；满容量时先清过期项，再丢最早插入的。"""
        now = time.monotonic()
        with self._lock:
            if len(self._data) >= self.maxsize:
                for k in [k for k, (_, exp) in self._data.items() if exp <= now]:
                    self._data.pop(k, None)
                while len(self._data) >= self.maxsize:
                    self._data.pop(next(iter(self._data)), None)
            self._data[key] = (value, now + self.ttl)

    def clear(self) -> None:
        """清空全部缓存（写操作成功后调用）。"""
        with self._lock:
            self._data.clear()

    def stats(self) -> Dict[str, int]:
        """返回当前容量与命中计数。"""
        with self._lock:
            return {"size": len(self._data), "hits": self._hits, "misses": self._misses}


# 读接口共用；写操作成功后整体清空（见 main.write_guard）
api_cache = TTLCache(ttl=30.0, maxsize=128)
