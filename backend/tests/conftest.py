"""pytest 全局夹具

改这个文件前先看三条：

1. **环境必须在导入任何 app 模块之前设好。**
   `app.config.settings` 是模块级单例，`app.database.engine` 也在导入时就建好了。
   一旦 import 完成再改环境就晚了 —— 测试会写到正式库 `backend/kg.db` 上去。
   所以本文件顶部「先设环境、后 import app」，顺序不能调。

2. **测试库放系统临时目录，每次运行一个独立文件，用完不删。**
   本机有安全删除钩子会拦截 `os.remove`（报 SAFE_DELETE_FAIL_CLOSED），
   删不掉不如不删：文件名带进程号与时间戳，互不干扰，系统临时目录自会清理。

3. **默认走 tfidf 引擎。** 真模型要加载 470MB，每个测试进程都加载会让测试慢到没人愿意跑。
   向量相关测试断言的是「关系」（改了算法指纹就得变、中文必须切多词元），
   而不是某个引擎的具体数值，所以降级路径足以覆盖。
   需要验证真模型时显式设 `VECTOR_BACKEND=transformers` 再跑。
"""
import os
import pathlib
import sys
import tempfile
import time

# ---------------------------------------------------------------- 环境（必须先于 app 导入）
BACKEND = pathlib.Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

_TMP_ROOT = pathlib.Path(tempfile.gettempdir()) / "kg-pytest"
_TMP_ROOT.mkdir(parents=True, exist_ok=True)
TEST_DB = _TMP_ROOT / f"kg_test_{os.getpid()}_{int(time.time())}.db"
TEST_EXPORTS = _TMP_ROOT / f"exports_{os.getpid()}_{int(time.time())}"

os.environ["DB_MODE"] = "sqlite"
os.environ["SQLITE_PATH"] = str(TEST_DB)
# 导出产物也要隔离。导出目录按 mtime 只保留最近 EXPORT_KEEP 个 ——
# 不隔离的话，跑一次导出用例就会把用户自己的导出产物挤掉。
os.environ["EXPORT_DIR"] = str(TEST_EXPORTS)
os.environ["VECTOR_BACKEND"] = "tfidf"          # 见文件头第 3 条
os.environ["PROTECT_WRITES"] = "true"           # 与生产一致，写守卫必须被测到
os.environ["ADMIN_TOKEN"] = "pytest-admin-token"
os.environ["REGISTRATION_OPEN"] = "true"
os.environ["AUDIT_KEEP_ROWS"] = "10000"         # 别让测试期间的审计被裁掉
os.environ["DEBUG"] = "false"
# 候选判定默认会联网交叉验证，测试里必须关掉：否则用例耗时取决于外网
os.environ["VERDICT_USE_WEB"] = "false"

import pytest                                       # noqa: E402
from fastapi.testclient import TestClient           # noqa: E402

from app.main import app                            # noqa: E402
from app.database import Base, SessionLocal, engine  # noqa: E402
from app.models import models                       # noqa: E402

ADMIN_TOKEN = os.environ["ADMIN_TOKEN"]

# 参照数据，用例之间不清：
#   knowledge_base / kb_relations —— 种子知识库，重建一次很慢
#   users                         —— 只保留 id=1（下面按条件清）
_KEEP_TABLES = {"knowledge_base", "kb_relations", "users"}


def _assert_not_production_db() -> None:
    """护栏：确认真的没连着正式库。这是整个测试套件的地基，值得单独立一条。"""
    url = str(engine.url)
    prod = (BACKEND / "kg.db").resolve()
    if str(prod).replace("\\", "/") in url.replace("\\", "/"):
        raise RuntimeError(
            f"测试连到了正式库！url={url}\n"
            f"夹具必须在 import app 之前设置 SQLITE_PATH，见 conftest.py 文件头。"
        )


@pytest.fixture(scope="session", autouse=True)
def _bootstrap():
    """建表 + 灌种子知识库。用 TestClient 的上下文触发 lifespan，与生产同一条路径。"""
    _assert_not_production_db()
    with TestClient(app) as client:
        yield client
    _assert_not_production_db()


@pytest.fixture()
def client(_bootstrap):
    """HTTP 客户端。走真实 ASGI 栈（含中间件、写守卫），不是直接调函数。"""
    return _bootstrap


@pytest.fixture()
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def workdir():
    """一个独立的临时工作目录（落在系统临时目录的 kg-pytest 下，用完不删）。

    刻意**不用 pytest 自带的 `tmp_path`**：它会在会话开始时清理历史的临时目录，
    而本机有安全删除钩子，一次删除的条目数超过阈值就被整批拒绝
    （`SAFE_DELETE_BULK_CONFIRM_REQUIRED`）—— 结果是**测试全过、退出码却是失败**，
    在 CI 里会被判定为红灯，排查起来还会以为是用例挂了。
    自己建目录就不经过那条清理路径。目录本身也不删（同一个钩子会拦），
    名字带前缀与随机后缀，互不干扰。
    """
    return pathlib.Path(tempfile.mkdtemp(prefix="wd_", dir=str(_TMP_ROOT)))


@pytest.fixture(autouse=True)
def clean_db(_bootstrap):
    """用例之间清空数据，保证互不干扰。

    autouse：忘了加这个夹具的用例会受别的用例污染，而这种失败往往表现为
    「单跑通过、全量跑失败」，很难查 —— 所以默认就清，而不是让每个用例自己记得清。
    """
    _reset()
    yield
    _reset()


def _reset() -> None:
    """清空可变表。

    删除顺序**不手写**，而是取 `Base.metadata.sorted_tables` 的**逆序** ——
    sorted_tables 是按外键依赖排的「父在前」，逆序即「子在前」，正好满足
    删除要求。手写顺序踩过一次：`knowledge_candidates` 排在 `nodes` 之后，
    于是库里有候选行时删 nodes 直接 IntegrityError，而且报错摊在夹具上、
    看起来像「测试环境坏了」而不是「顺序写错了」。
    让元数据来决定，以后新加表也不必回来改这里。
    """
    from sqlalchemy import text

    session = SessionLocal()
    try:
        for table in reversed(Base.metadata.sorted_tables):
            if table.name in _KEEP_TABLES:
                continue
            session.execute(table.delete())

        # 默认用户保留，注册出来的测试账号清掉（否则唯一约束会跨用例冲突）
        session.execute(text("DELETE FROM users WHERE id != 1"))
        # 测试自造的知识库条目统一用 _TEST_ 前缀，只清这些，不碰种子数据
        session.execute(text(
            r"DELETE FROM knowledge_base WHERE entity LIKE '\_TEST\_%' ESCAPE '\'"))
        session.execute(text(
            r"DELETE FROM kb_relations WHERE source_entity LIKE '\_TEST\_%' ESCAPE '\'"))
        session.commit()

        # 索引缓存是进程级的，跨用例必须失效，否则一个用例改了知识库会污染下一个
        from app.services.kb_index import invalidate_index
        invalidate_index()
    finally:
        session.close()


# ---------------------------------------------------------------- 常用夹具


@pytest.fixture()
def admin_headers():
    """旧口令通道（脚本/curl 用）。会话通道见 authed_headers。"""
    return {"X-Admin-Token": ADMIN_TOKEN}


@pytest.fixture()
def authed_headers(client):
    """登录会话通道：先 bootstrap 出管理员，再拿会话令牌。

    这条路径覆盖的是生产主通道（X-Session-Token），比旧口令更值得测。
    """
    from app.services.auth_service import SESSION_HEADER

    status = client.get("/api/auth/status").json()
    if status.get("need_bootstrap"):
        r = client.post("/api/auth/bootstrap",
                        json={"username": "pytest_admin", "password": "Pytest#12345"})
        assert r.status_code == 200, r.text
        token = r.json().get("token") or r.json().get("session_token")
    else:
        r = client.post("/api/auth/login",
                        json={"username": "pytest_admin", "password": "Pytest#12345"})
        if r.status_code != 200:
            r = client.post("/api/auth/bootstrap",
                            json={"username": "pytest_admin", "password": "Pytest#12345"})
            token = r.json().get("token") or r.json().get("session_token")
        else:
            token = r.json().get("token") or r.json().get("session_token")
    assert token, f"未能取得会话令牌：{r.text}"
    return {SESSION_HEADER: token}


@pytest.fixture()
def make_file(db):
    """造一个文件记录（含可选的节点），返回 file_id。"""
    import time as _t

    from app.models.models import File, Node

    def _make(name="t.md", nodes=0, user_id=1):
        f = File(user_id=user_id, name=name, content="测试内容", status="parsed")
        db.add(f)
        db.commit()
        db.refresh(f)
        for i in range(nodes):
            db.add(Node(file_id=f.id, user_id=user_id, entity=f"{name}-实体{i}",
                        title=f"标题{i}", description=f"描述{i}",
                        upload_time=int(_t.time())))
        db.commit()
        return f.id

    return _make
