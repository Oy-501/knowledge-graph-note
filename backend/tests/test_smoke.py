"""套件自身的地基测试

这个文件测的不是业务，而是「测试环境本身是否可靠」。它必须最先跑。
理由：如果夹具把测试连到了正式库，后面所有用例都会在真实数据上跑 ——
那种损伤是不可逆的，而且很可能当场看不出来。

用例失败时先看这里。
"""
import os
from pathlib import Path

from app.database import engine


def test_not_pointing_at_production_db():
    """测试库必须是临时目录里的独立文件，绝不能是 backend/kg.db。"""
    url = str(engine.url).replace("\\", "/")
    backend = Path(__file__).resolve().parents[1]
    prod = str((backend / "kg.db").resolve()).replace("\\", "/")

    assert prod not in url, f"连到了正式库：{url}"
    assert "kg_test_" in url, f"测试库名不符合约定（应含 kg_test_）：{url}"


def test_test_db_is_isolated_from_repo():
    """测试库落在系统临时目录，不落在仓库里（否则会污染工作区）。"""
    path = Path(os.environ["SQLITE_PATH"]).resolve()
    backend = Path(__file__).resolve().parents[1]
    assert backend not in path.parents, f"测试库落在仓库内：{path}"


def test_engine_is_sqlite():
    assert engine.dialect.name == "sqlite"


def test_health_endpoint_ok(client):
    r = client.get("/api/health")
    assert r.status_code == 200


def test_seed_knowledge_base_present(db):
    """种子知识库要真的灌进去 —— 很多用例依赖它（知识锚定、桥接）。"""
    from app.models.models import KnowledgeBase

    assert db.query(KnowledgeBase).count() > 100, "种子知识库没灌进来，检查 lifespan 是否跑过"


def test_relative_paths_resolve_under_backend():
    """配置里的相对路径一律按 backend/ 解析，且不能把 `../` 悄悄吃掉。

    这条守的是一个真实踩过的坑：`path.lstrip("./")` 剥的是**字符集**不是前缀，
    `"../data/kg.db"` 会被剥成 `"data/kg.db"` —— 用户以为数据在上一级，
    实际连的是 backend/ 下的另一个文件（甚至新建空库）。
    与 `resolved_sqlite_path` 文档里记的「静默连错库」是同一类事故。
    """
    from app.config import BACKEND_DIR, Settings

    s = Settings(SQLITE_PATH="../data/x.db", UPLOAD_DIR="./up", EXPORT_DIR="./ex",
                 VECTOR_CACHE_DIR="./md")
    assert s.resolved_sqlite_path == os.path.normpath(
        os.path.join(BACKEND_DIR, "..", "data", "x.db"))
    assert Path(s.resolved_sqlite_path).parent.name == "data", s.resolved_sqlite_path

    for got, name in ((s.resolved_upload_dir, "up"), (s.resolved_export_dir, "ex"),
                      (s.resolved_model_dir, "md")):
        assert os.path.isabs(got), f"{name} 没解析成绝对路径：{got}"
        assert Path(got).name == name, f"{name} 解析到了 {got}"

    # 绝对路径必须原样返回
    abs_path = str(Path(os.environ["SQLITE_PATH"]).resolve())
    assert Settings(SQLITE_PATH=abs_path).resolved_sqlite_path == abs_path


def test_export_dir_is_isolated_in_tests():
    """导出产物目录也必须隔离。

    导出目录按 mtime 只保留最近 N 个文件 —— 不隔离的话，
    跑一次导出用例就会把用户自己的导出产物挤掉。
    """
    from app.config import settings

    assert "kg-pytest" in settings.resolved_export_dir, (
        f"测试没有隔离导出目录，会写进正式产物目录：{settings.resolved_export_dir}"
    )


def test_vector_engine_degraded_on_purpose():
    """测试进程刻意走 tfidf，避免每次加载 470MB 模型。这条是给未来的人的提醒。"""
    from app.services import vector_engine

    info = vector_engine.get_engine_info()
    assert info["signature"].startswith("tfidf"), (
        f"测试应当走降级引擎，实际 {info['signature']}；"
        f"若确实要测真模型，请显式设置 VECTOR_BACKEND=transformers 并接受加载耗时"
    )
