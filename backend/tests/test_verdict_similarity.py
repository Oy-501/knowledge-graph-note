"""定义相似度：语义判定优先于字面重叠。"""
from app.services import knowledge_verifier as kv


def test_semantic_similarity_is_used(monkeypatch):
    """同义改写字面重叠为 0，但语义向量一致时应判为相似。"""
    from app.services import vector_engine

    monkeypatch.setattr(vector_engine, "encode_cached", lambda _t: [1.0, 0.0])
    assert kv._def_similarity("甲概念", "乙概念") == 1.0


def test_orthogonal_vectors_score_zero(monkeypatch):
    from app.services import vector_engine

    monkeypatch.setattr(
        vector_engine, "encode",
        lambda t: [1.0, 0.0] if "树" in t else [0.0, 1.0])
    assert kv._def_similarity("索引结构", "平衡树") == 0.0


def test_falls_back_to_lexical_when_encoder_fails(monkeypatch):
    from app.services import vector_engine

    def boom(_text):
        raise RuntimeError("模型不可用")

    monkeypatch.setattr(vector_engine, "encode_cached", boom)
    assert kv._def_similarity("多路平衡查找树", "多路平衡查找树") == 1.0
