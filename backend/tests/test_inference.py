"""关联推理的打分维度

重点是 `_link_flags` —— 连线的「桥接类型」标记。

它出过一次影响很大的事故：实现里写死 `time_bridge=True`，于是所有自动推理出来的
连线都以「时间桥接」入库。于是「时间桥接 553 / 语义桥接 11」这类统计，
量的是**哪段代码写的**，不是「依据是什么」。拿这个数字去判断「语义路径有没有出力」
会被彻底带偏。

所以这里的核心用例不是「标记等于什么」，而是**标记会不会跟依据变**。
"""
import pytest

from app.services.inference import _link_flags, infer_links_batch
from app.services.vector_engine import cosine_similarity


# ---------------------------------------------------------------- 标记必须跟着依据走

def test_no_evidence_means_time_bridge():
    """内容上毫无依据、只因时间窗口接近才连上，这才叫时间桥接。"""
    flags = _link_flags({})
    assert flags["time_bridge"] is True
    assert flags["semantic_bridge"] is False


def test_keyword_evidence_is_not_time_bridge():
    flags = _link_flags({"sim_text": 0.5})
    assert flags["time_bridge"] is False, "有内容依据就不该标时间桥接"
    assert flags["semantic_bridge"] is False, "关键词重合不是语义桥接"


def test_vector_evidence_is_not_time_bridge():
    flags = _link_flags({"sim_vector": 0.7})
    assert flags["time_bridge"] is False


def test_topology_evidence_is_not_time_bridge():
    flags = _link_flags({"sim_topology": 0.3})
    assert flags["time_bridge"] is False, "拓扑也算内容依据"


def test_corpus_bridge_marks_semantic():
    flags = _link_flags({"sim_corpus": 0.4})
    assert flags["semantic_bridge"] is True
    assert flags["time_bridge"] is False


def test_zero_valued_evidence_is_still_no_evidence():
    """显式写了但值为 0，等于没依据 —— 不能因为「键存在」就当成有证据。"""
    flags = _link_flags({"sim_text": 0.0, "sim_vector": 0.0, "sim_corpus": 0.0})
    assert flags["time_bridge"] is True


def test_flags_actually_vary_with_input():
    """元用例：如果哪天有人把标记写死，这条会立刻发现「返回值不随输入变化」。"""
    samples = [
        _link_flags({}),
        _link_flags({"sim_text": 0.5}),
        _link_flags({"sim_corpus": 0.4}),
    ]
    assert len({(f["time_bridge"], f["semantic_bridge"]) for f in samples}) > 1, (
        "不同依据产出了完全相同的标记，说明标记退化成常量了"
    )


def test_flags_are_booleans():
    flags = _link_flags({"sim_text": 0.3})
    assert isinstance(flags["time_bridge"], bool)
    assert isinstance(flags["semantic_bridge"], bool)


# ---------------------------------------------------------------- 调用点（纯函数之外）

_WEIGHTS = {"alpha": 0.15, "beta": 0.25, "gamma": 0.50, "delta": 0.10}


def _node(nid, entity, keywords, file_id=1, upload_time=None):
    """构造 `_node_to_dict` 形状的节点字典。

    `upload_time` 必须是**正数**：`can_connect` 的三个准入条件之一是
    「两端 upload_time 都 > 0 且相差 7 天内」，给 0 会被当成「时间未知」而拒绝连线
    （这不是 bug，是刻意的闸门）。踩过一次，现在默认给当前时间。
    """
    import time as _t

    return {
        "id": nid, "entity": entity, "title": entity, "description": "",
        "keywords": keywords, "entities": [], "level": 3, "domain": "",
        "file_id": file_id, "group_id": "default",
        "upload_time": int(_t.time()) if upload_time is None else upload_time,
        "embedding": None, "embedding_meta": None, "isolate_blacklist": [],
    }


def test_pipeline_derives_flags_at_the_call_site(db):
    """从**真实入口**验证连线标记由依据推导。

    为什么不能只测 `_link_flags()`：调用点完全可以绕过它把标记写死，
    而纯函数测试照样全绿 —— 这个盲区是被反向验证抓出来的
    （把 `infer_links_batch` 里的标记改成硬编码 True，只测纯函数的用例毫无反应）。

    用**自造实体**（不在种子知识库里）来隔离 α 维：真实术语会额外命中
    知识库桥接（γ>0），那样 semantic_bridge 本来就该是 True，
    断言 False 会误伤 —— 这一点也是实测撞出来的。

    阈值取 0.01：`threshold or 0.15` 会把 0.0 当成「没给」而回落 0.15，
    而纯关键词重合只值 0.15×jaccard，传 0 反而什么都连不上。
    """
    new = [_node(1, "自造概念甲", ["共同特征词", "另一个特征词"], file_id=1)]
    old = [_node(2, "自造概念乙", ["共同特征词", "另一个特征词"], file_id=2)]

    links = infer_links_batch(new, 1, _WEIGHTS, 0.01, db, existing_nodes=old)
    assert links, "没有产出连线，这条用例就失去意义了"

    for link in links:
        assert "time_bridge" in link and "semantic_bridge" in link, (
            f"连线缺少桥接标记：{sorted(link)}"
        )
        # 有关键词重合 → 有内容依据 → 不能算「时间桥接」（写死 True 会被这条抓住）
        assert link["time_bridge"] is False, (
            f"有内容依据却被标成时间桥接（标记可能被写死了）：{link}"
        )
        # 实体不在知识库里 → 没有知识库桥接 → 不该标语义桥接
        assert link["semantic_bridge"] is False, (
            f"仅关键词重合、无知识库桥接，却标成了 semantic_bridge：{link}"
        )


def test_real_kb_terms_do_bridge_semantically(db):
    """真实术语（命中种子知识库）应当标出 semantic_bridge —— 与上一条互为对照。"""
    new = [_node(3, "数据库索引", ["数据库", "索引"], file_id=1)]
    old = [_node(4, "索引优化实践", ["数据库", "索引"], file_id=2)]
    links = infer_links_batch(new, 1, _WEIGHTS, 0.01, db, existing_nodes=old)
    assert links, "真实术语之间应当能连上"
    assert any(l["semantic_bridge"] for l in links), (
        f"真实术语命中知识库却没标语义桥接：{[{k: l[k] for k in ('score','semantic_bridge','evidence')} for l in links]}"
    )


def test_pipeline_emits_nothing_without_evidence(db):
    """零内容依据的节点对根本不连线 —— 于是 `time_bridge=True` 走不到。

    这是修掉「标记写死 time_bridge=True」之后的必然后果，值得钉住：
      连线的前提是 `score >= threshold`，而 threshold 恒为正
      （`threshold or 0.15`：传 0 会回落 0.15，传 0.0001 也是正数）；
      零依据时四维得分恒为 0，`0 >= 正数` 永远不成立。
    所以 `time_bridge` 在当前模型下**始终为 False** —— 它是对的，
    但也是一条不会发生的情况。若产品确实要「按时间相近建立关联」，
    应把它做成真正的打分维度，而不是靠一个残余标记。
    """
    new = [_node(10, "自造概念丙", ["红烧肉", "番茄炒蛋"], file_id=1)]
    old = [_node(11, "自造概念丁", ["数据结构", "算法复杂度"], file_id=3)]

    for th in (0.0001, 0.01, 0.15):
        assert infer_links_batch(new, 1, _WEIGHTS, th, db,
                                 existing_nodes=old) == [], (
            f"阈值 {th} 下零依据节点对竟然连上了 —— "
            f"检查时间窗口是否被当成了「依据」而不是「闸门」"
        )


def test_inference_source_has_no_hardcoded_bridge_flags():
    """源码级兜底：`inference.py` 里不该出现把标记写成字面量的代码。

    行为用例覆盖的是「当前能跑到的路径」；这条覆盖「写死的字面量」本身，
    两者互补（字面量可能出现在条件分支里，行为用例不一定走得到）。
    """
    import ast
    import pathlib

    src = pathlib.Path(__file__).resolve().parents[1] / "app" / "services" / "inference.py"
    tree = ast.parse(src.read_text(encoding="utf-8"))

    offenders = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            for kw in node.keywords:
                if kw.arg in ("time_bridge", "semantic_bridge") and isinstance(kw.value, ast.Constant):
                    offenders.append(f"第 {node.lineno} 行 {kw.arg}={kw.value.value!r}")
        elif isinstance(node, ast.Dict):
            for key, val in zip(node.keys, node.values):
                if (isinstance(key, ast.Constant)
                        and key.value in ("time_bridge", "semantic_bridge")
                        and isinstance(val, ast.Constant)):
                    offenders.append(f'第 {node.lineno} 行 "{key.value}": {val.value!r}')

    assert not offenders, (
        f"inference.py 里把桥接标记写成了字面量，应按依据推导：{offenders}"
    )


# ---------------------------------------------------------------- 打分基础

def test_cosine_used_by_beta_dimension_is_dimension_safe():
    """β 维依赖 cosine；维度不一致时必须返回 0 而不是抛异常或算出垃圾值。"""
    assert cosine_similarity([1.0] * 384, [1.0] * 256) == 0.0
    assert cosine_similarity([1.0] * 384, [1.0] * 384) == pytest.approx(1.0)


def test_infer_endpoint_requires_payload(client, admin_headers):
    """推理端点是写操作，参数不合法应当被拦下（422），而不是 500。"""
    r = client.post("/api/knowledge/infer", json={}, headers=admin_headers)
    assert r.status_code in (400, 422), f"期望参数错误，实际 {r.status_code}: {r.text[:200]}"


def test_infer_endpoint_rejects_malformed_json(client, admin_headers):
    r = client.post("/api/knowledge/infer", content=b"{not json",
                    headers={**admin_headers, "Content-Type": "application/json"})
    assert r.status_code in (400, 422)
