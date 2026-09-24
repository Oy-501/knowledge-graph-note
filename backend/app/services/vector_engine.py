"""向量编码服务"""
import json
import hashlib
import re
from typing import List, Optional
from loguru import logger

_encoder = None
_engine_mode = "fallback-tfidf"


def _init_encoder():
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
    _init_encoder()
    if _encoder is not None:
        try:
            vec = _encoder.encode(text, convert_to_numpy=True)
            return vec.tolist()
        except Exception as e:
            logger.error(f"Transformers encode failed: {e}")
    return _tfidf_encode(text)


def encode_batch(texts: List[str]) -> List[List[float]]:
    _init_encoder()
    if _encoder is not None:
        try:
            vecs = _encoder.encode(texts, convert_to_numpy=True)
            return [v.tolist() for v in vecs]
        except Exception:
            pass
    return [_tfidf_encode(t) for t in texts]


def cosine_similarity(a: List[float], b: List[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(x * x for x in b) ** 0.5
    if na == 0 or nb == 0:
        return 0.0
    return max(0.0, min(1.0, dot / (na * nb)))


def jaccard_similarity(a: List[str], b: List[str]) -> float:
    if not a or not b:
        return 0.0
    sa = set(a)
    sb = set(b)
    intersection = len(sa & sb)
    union = len(sa | sb)
    return intersection / union if union > 0 else 0.0


def _tfidf_encode(text: str, dim: int = 100) -> List[float]:
    text = re.sub(r'[^\w\s\u4e00-\u9fff]', ' ', text.lower())
    words = text.split()
    if not words:
        return [0.0] * dim
    tf = {}
    for w in words:
        tf[w] = tf.get(w, 0) + 1
    vec = [0.0] * dim
    for w, freq in tf.items():
        h = int(hashlib.md5(w.encode()).hexdigest(), 16) % dim
        vec[h] += freq / len(words)
    norm = sum(x * x for x in vec) ** 0.5
    if norm > 0:
        vec = [x / norm for x in vec]
    return vec


def get_engine_info() -> dict:
    return {
        "mode": _engine_mode,
        "dim": 768 if _engine_mode == "transformers" else 100
    }


def embed_to_db(nodes: list, db) -> None:
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
    for i, node_data in enumerate(nodes):
        if i < len(vectors):
            node_id = node_data.get("id")
            if node_id:
                node = db.query(Node).filter_by(id=node_id).first()
                if node:
                    node.embedding = json.dumps(vectors[i])
    db.commit()
