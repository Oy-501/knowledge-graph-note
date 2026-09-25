"""向量编码服务"""
import json
import hashlib
import re
from typing import List, Optional
from loguru import logger

# 尝试加载 sentence-transformers，失败则使用降级方法
_encoder = None
_engine_mode = "fallback-tfidf"


def _init_encoder():
    """延迟初始化向量编码器"""
    global _encoder, _engine_mode
    if _encoder is not None:
        return

    try:
        from sentence_transformers import SentenceTransformer
        from app.config import settings
        logger.info(f"Loading vector model: {settings.VECTOR_MODEL}")
        _encoder = SentenceTransformer(settings.VECTOR_MODEL, device="cpu")
        _engine_mode = "transformers"
        logger.info("Vector encoder ready: transformers")
    except Exception as e:
        logger.warning(f"Failed to load transformers, using TF-IDF fallback: {e}")
        _engine_mode = "fallback-tfidf"


def encode(text: str) -> List[float]:
    """将文本编码为向量"""
    _init_encoder()

    if _encoder is not None:
        try:
            vec = _encoder.encode(text, convert_to_numpy=True)
            return vec.tolist()
        except Exception as e:
            logger.error(f"Transformers encode failed: {e}")

    # TF-IDF 降级
    return _tfidf_encode(text)


def encode_batch(texts: List[str]) -> List[List[float]]:
    """批量编码"""
    _init_encoder()

    if _encoder is not None:
        try:
            vecs = _encoder.encode(texts, convert_to_numpy=True)
            return [v.tolist() for v in vecs]
        except Exception:
            pass

    return [_tfidf_encode(t) for t in texts]


def cosine_similarity(a: List[float], b: List[float]) -> float:
    """计算余弦相似度"""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(x * x for x in b) ** 0.5
    if na == 0 or nb == 0:
        return 0.0
    return max(0.0, min(1.0, dot / (na * nb)))


def jaccard_similarity(a: List[str], b: List[str]) -> float:
    """计算 Jaccard 相似度"""
    if not a or not b:
        return 0.0
    sa = set(a)
    sb = set(b)
    intersection = len(sa & sb)
    union = len(sa | sb)
    return intersection / union if union > 0 else 0.0


def _tfidf_encode(text: str, dim: int = 100) -> List[float]:
    """TF-IDF 降级编码"""
    text = re.sub(r'[^\w\s\u4e00-\u9fff]', ' ', text.lower())
    words = text.split()
    if not words:
        return [0.0] * dim

    # 词频统计
    tf = {}
    for w in words:
        tf[w] = tf.get(w, 0) + 1

    # 哈希到固定维度
    vec = [0.0] * dim
    for w, freq in tf.items():
        h = int(hashlib.md5(w.encode()).hexdigest(), 16) % dim
        vec[h] += freq / len(words)

    # 归一化
    norm = sum(x * x for x in vec) ** 0.5
    if norm > 0:
        vec = [x / norm for x in vec]

    return vec


def get_engine_info() -> dict:
    """获取向量引擎信息"""
    return {
        "mode": _engine_mode,
        "dim": 768 if _engine_mode == "transformers" else 100
    }


def embed_to_db(nodes: list, db) -> None:
    """为节点生成向量并存储到数据库"""
    from app.models.models import Node

    def _text(n):
        parts = []
        if n.get("entity"):
            parts.append(n["entity"])
        if n.get("keywords"):
            parts.append(" ".join(n["keywords"]))
        parts.append(n.get("description") or "")
        return " ".join(parts).strip()

    texts = [_text(n) for n in nodes]
    if not texts:
        return

    try:
        vectors = encode_batch(texts)
    except Exception as e:
        logger.error(f"Batch encode failed: {e}")
        return

    # 一次性查出这批节点再回填（原来每个节点一次 SELECT，大文件下几千次查询非常致命）
    id_list = [n.get("id") for n in nodes if n.get("id")]
    node_rows = {n.id: n for n in db.query(Node).filter(Node.id.in_(id_list)).all()} if id_list else {}

    for i, node_data in enumerate(nodes):
        if i >= len(vectors):
            continue
        node = node_rows.get(node_data.get("id"))
        if node:
            node.embedding = json.dumps(vectors[i])
    db.commit()