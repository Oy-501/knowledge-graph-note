"""系统自检（`/api/system/doctor`）的报告完整性

自检是「出问题先看它」的入口，所以它**漏报比误报危险得多**：
用户看到「一切正常」就不会再去查别的。这里守的就是漏报。

抓到过的真实漏报：向量载荷损坏（`embedding` 存了坏 JSON）已经被
`embedding_health` 数出来了，但自检只报 `stale`，于是这类节点的 β 维
恒为 0，而自检显示一切正常 —— 符合「静默失效」的典型形态。

顺带守一条设计约束：**三类问题不能只报优先级最高的那个**。
只报一个的话，另外两个会一直在绿灯背面躺着（陈旧当年就是这么藏住的）。
"""
import json

from app.api import system as system_api
from app.models.models import Node
from app.services import vector_engine as ve


def _node(fid: int, entity: str, embedding, meta) -> Node:
    return Node(file_id=fid, user_id=1, entity=entity,
                embedding=embedding, embedding_meta=meta)


def _fresh_info(dim: int = 4) -> dict:
    """假装引擎是就绪的真模型。

    测试默认跑降级引擎，而降级本身就是一条 WARN —— 不替换掉的话
    「干净状态应报 OK」这条根本测不到。
    """
    return {"mode": "transformers", "signature": f"transformers|demo|{dim}|1",
            "dim": dim, "degraded": False, "reason": ""}


def test_doctor_reports_broken_vectors(db, make_file):
    """损坏的向量必须被自检报出来，且带得上条数。"""
    fid = make_file("broken.md", nodes=0)
    sig = ve.engine_signature()
    db.add_all([
        _node(fid, "好向量", json.dumps([0.1, 0.2]), sig),
        _node(fid, "坏向量", "{not json", sig),
    ])
    db.commit()

    r = system_api._check_vector_engine(db)
    assert r["status"] == system_api.WARN, f"损坏向量没有触发告警：{r}"
    assert "载荷损坏" in r["detail"], f"自检没提「载荷损坏」：{r}"
    assert "1 条" in r["detail"], f"没带上损坏条数：{r}"


def test_doctor_reports_stale_and_broken_together(db, make_file):
    """陈旧与损坏是两回事，各自的原因和修法都不同，必须同时可见。

    若实现退化成「只报优先级最高的那一个」，这条会失败 ——
    那正是本轮修掉的漏报模式。
    """
    fid = make_file("both.md", nodes=0)
    sig = ve.engine_signature()
    db.add_all([
        _node(fid, "陈旧", json.dumps([0.1, 0.2]), "st|other-model|768|1"),
        _node(fid, "损坏", "{not json", sig),
    ])
    db.commit()

    r = system_api._check_vector_engine(db)
    assert r["status"] == system_api.WARN, r
    assert "载荷损坏" in r["detail"], f"报损坏时把陈旧吞掉了：{r}"
    assert "旧引擎产出" in r["detail"], f"报陈旧时把损坏吞掉了：{r}"


def test_doctor_reports_ok_when_nothing_to_fix(db, make_file, monkeypatch):
    """干净状态必须报 OK —— 否则这一项会变成永远黄灯的噪音，没人再看。"""
    monkeypatch.setattr(ve, "get_engine_info", lambda: _fresh_info())
    fid = make_file("clean.md", nodes=0)
    db.add(_node(fid, "干净的", json.dumps([0.1, 0.2, 0.3, 0.4]),
                 ve.engine_signature()))
    db.commit()

    r = system_api._check_vector_engine(db)
    assert r["status"] == system_api.OK, f"干净状态却报了告警：{r}"


def test_doctor_ok_on_empty_graph(db, monkeypatch):
    """空图谱不该报错 —— 没数据不等于坏掉了，报到 WARN 会让首次使用就见到黄灯。"""
    monkeypatch.setattr(ve, "get_engine_info", lambda: _fresh_info())
    r = system_api._check_vector_engine(db)
    assert r["status"] == system_api.OK, f"空图谱（零节点）不该报错：{r}"


def test_doctor_degraded_hint_targets_the_root_cause(db, make_file):
    """降级时若只提示「重建向量」，用户会拿降级引擎重建一遍，问题原样保留。"""
    info = ve.get_engine_info()
    if not info["degraded"]:
        # 跑在真模型上时这条无从触发，跳过而不是假装通过
        import pytest
        pytest.skip("当前引擎未降级，降级指引无从触发")
    fid = make_file("deg.md", nodes=0)
    db.add(_node(fid, "任意", json.dumps([0.1, 0.2]), ve.engine_signature()))
    db.commit()

    r = system_api._check_vector_engine(db)
    assert r["status"] == system_api.WARN, r
    assert "sentence-transformers" in r["hint"], (
        f"降级时的修复指引没有指向根因（装模型）：{r}"
    )
