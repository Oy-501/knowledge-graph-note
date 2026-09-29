"""向量编码服务

负责把节点文本编码成可比较的向量，供 inference 的四维打分里 β 维（语义相似度）使用。

两种引擎：
  1) transformers —— sentence-transformers 加载本地模型，真正的语义向量（首选）。
     「换个说法说同一件事」靠它才认得出：词不一样但意思一样也有高相似度。
  2) tfidf —— 没装模型时的降级实现：CJK 单字 + 二元组、拉丁词，真实 IDF 加权，
     带符号哈希 + L2 归一。（只认字面重合，换个说法就不行，是明确的降级而非等价方案。）

改动注意：
- 不同引擎/不同模型产出的向量维度不同。维度不同的两个向量做 cosine 恒为 0，
  这不是「不相似」而是「没法比」。所以每条向量都要记下它的引擎指纹
  （nodes.embedding_meta），换引擎后必须重建向量，否则 β 维会静默失效。
- 指纹和实际向量必须一起写，别只写其中一个。
"""
import hashlib
import json
import math
import os
import re
import threading
from typing import Dict, Iterable, List, Optional
from loguru import logger

# 算法版本：降级编码的切词/加权方式一旦改动就 +1，
# 这样即便仍走 tfidf，旧向量也会被识别为「陈旧」而不是被当成可比。
ALGO_VERSION = "2"

# 降级向量的维度。哈希到固定维度，取 256 以减少碰撞（原来是 100，碰撞概率偏高）。
FALLBACK_DIM = 256

# 模型推理的批大小。实测（300 条文本、12 线程）96 比 32 快约 10%，
# 再往上（128+）就没收益了，只多占内存。
ENCODE_BATCH_SIZE = 96

_encoder = None
_engine_mode = "fallback-tfidf"
_engine_dim = FALLBACK_DIM
_engine_error = ""
_model_error_detail = ""   # 保留原始报错，供 doctor 展示原因
_initialized = False       # 初始化只做一次；三态（成功/降级/指定降级）都要认
_init_lock = threading.Lock()   # 模型加载互斥：没有它，并发请求会各加载一份（见 _init_encoder）

# 语料 IDF 表：doc -> 词频分布
_IDF: Dict[str, float] = {}
_IDF_DOCS = 0


# ---------------------------------------------------------------- 文本切分

# CJK 统一表意文字（含扩展 A 与兼容表意），其余按「拉丁/数字词」处理。
_CJK = r"\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff"
_TOKEN_RE = re.compile(rf"[{_CJK}]+|[a-z0-9][a-z0-9_+#.\-]*")

# 只放高频虚词，不追求全。目的是别让「的/了/是/the/of」这类词主导相似度。
_STOPWORDS = {
    "的", "了", "和", "与", "及", "或", "是", "在", "对", "为", "以", "被", "把", "从",
    "到", "中", "上", "下", "个", "这", "那", "有", "也", "就", "都", "而", "并", "则",
    "其", "之", "由", "等", "可", "能", "会", "将", "使", "让", "向", "由", "于", "以",
    "the", "a", "an", "of", "to", "in", "on", "for", "and", "or", "is", "are", "was",
    "were", "be", "been", "it", "its", "this", "that", "these", "those", "as", "at",
    "by", "with", "from", "we", "you", "they", "he", "she", "his", "her", "their",
    "our", "your", "not", "no", "but", "if", "then", "than", "so", "such", "which",
    "who", "whom", "what", "when", "where", "how", "can", "could", "will", "would",
    "should", "may", "might", "must", "have", "has", "had", "do", "does", "did",
}


def analyze(text: str) -> List[str]:
    """把文本切成可比对的词元。

    中文没有空格，按空白切词会把整句话变成一个词元（两个不同的句子因此毫不相干），
    所以中日韩文按「字」处理：连续汉字串切成相邻二元组（bigram），单字串保留自身。
    这样「数据库索引优化」与「优化数据库的索引」能共享 数据/据库/索引 三个词元。
    """
    if not text:
        return []
    tokens: List[str] = []
    for raw in _TOKEN_RE.findall(text.lower()):
        if _is_cjk_run(raw):
            if len(raw) == 1:
                if raw not in _STOPWORDS:
                    tokens.append(raw)
            else:
                for i in range(len(raw) - 1):
                    bigram = raw[i:i + 2]
                    if bigram[0] in _STOPWORDS and bigram[1] in _STOPWORDS:
                        continue
                    tokens.append(bigram)
        else:
            if len(raw) >= 2 and raw not in _STOPWORDS:
                tokens.append(raw)
    return tokens


def _is_cjk_run(part: str) -> bool:
    first = part[0]
    return "\u3400" <= first <= "\u4dbf" or "\u4e00" <= first <= "\u9fff" or "\uf900" <= first <= "\ufaff"


# ---------------------------------------------------------------- IDF

def build_idf(texts: Iterable[str]) -> int:
    """用整个语料统计 IDF 表（文档频率），返回参与统计的文档数。

    必须在「编码这批向量之前」先建好，且整批共用同一张表 —— 否则同一批节点里
    前面用旧 IDF、后面用新 IDF，向量之间就不可比了。
    """
    global _IDF, _IDF_DOCS
    df: Dict[str, int] = {}
    doc_count = 0
    for text in texts:
        tokens = set(analyze(text))
        if not tokens:
            continue
        doc_count += 1
        for tok in tokens:
            df[tok] = df.get(tok, 0) + 1
    # 平滑 IDF：出现在越少文档里的词权重越高；+1 保证不会出现 0（0 权重等于丢词）
    _IDF = {
        tok: math.log((1 + doc_count) / (1 + freq)) + 1.0
        for tok, freq in df.items()
    }
    _IDF_DOCS = doc_count
    return doc_count


def idf_stats() -> dict:
    return {"terms": len(_IDF), "docs": _IDF_DOCS}


def reset_idf() -> None:
    global _IDF, _IDF_DOCS
    _IDF = {}
    _IDF_DOCS = 0


def _weight(token: str) -> float:
    """词元权重。没有语料统计时退回 1.0（等价于只用 TF），仍然远好于整句哈希。"""
    if not _IDF:
        return 1.0
    return _IDF.get(token, math.log((1 + _IDF_DOCS) / 1.0) + 1.0)


# ---------------------------------------------------------------- 编码

def _init_encoder() -> None:
    """初始化向量编码器（进程内只做一次）。

    **必须加锁。** 这里原来是「先检查 _initialized、再加载」的写法，而
    `_initialized` 要到加载完成后才置位 —— 于是加载期间到达的并发请求
    全都通过检查、各自加载一份模型。模型是几百 MB、加载要十几秒，
    这个窗口大到必炸：实测 24 个并发请求触发了 24 次加载，
    进程峰值内存 8.1GB，最慢请求 67 秒。

    修法是双重检查 + 锁：锁外先快速判断（热路径不进锁），锁内再判断一次，
    保证只有第一个线程真正加载，其余线程等它加载完直接复用。
    """
    global _encoder, _engine_mode, _engine_dim, _engine_error, _model_error_detail, _initialized
    if _initialized:
        return

    with _init_lock:
        # 双重检查：等锁期间可能已经被别的线程加载好了
        if _initialized:
            return
        _load_encoder()


def _load_encoder() -> None:
    """真正加载模型。只在持有 _init_lock 时调用。"""
    global _encoder, _engine_mode, _engine_dim, _engine_error, _model_error_detail, _initialized
    from app.config import settings

    backend = (getattr(settings, "VECTOR_BACKEND", "auto") or "auto").lower()
    if backend == "tfidf":
        _engine_mode = "fallback-tfidf"
        _engine_dim = FALLBACK_DIM
        _engine_error = "VECTOR_BACKEND=tfidf（显式指定走降级路径）"
        _model_error_detail = _engine_error
        _initialized = True
        logger.warning("VECTOR_BACKEND=tfidf：按要求使用降级编码，不加载模型。")
        return

    _apply_hf_env(settings)
    try:
        import torch
        from sentence_transformers import SentenceTransformer

        name = settings.VECTOR_MODEL
        cache_dir = settings.resolved_model_dir
        os.makedirs(cache_dir, exist_ok=True)

        # CPU 推理的线程数是个大旋钮，实测（16 逻辑核、300 条文本）：
        #   6 线程 7.3ms/条 / 8 线程（torch 默认，等于物理核）6.0 / 12 线程 4.4 / 16 线程 4.9
        # 也就是「留几个核给服务本身、其余都给推理」最快，吃满全部核反而因为
        # 超订变慢。取逻辑核的 3/4，至少 2 个。
        logical = os.cpu_count() or 2
        threads = max(2, int(logical * 0.75))
        torch.set_num_threads(threads)

        logger.info(f"Loading vector model: {name} (cache={cache_dir}, torch_threads={threads})")
        model = SentenceTransformer(
            name,
            device="cpu",
            cache_folder=cache_dir,
        )
        # 维度取值方法在 sentence-transformers 6.x 改名了，两个名字都试一下，
        # 免得版本一升级就抛 FutureWarning（甚至 AttributeError）。
        dim_getter = (getattr(model, "get_embedding_dimension", None)
                      or getattr(model, "get_sentence_embedding_dimension", None))
        dim = int(dim_getter() or 0) if dim_getter else 0
        _encoder = model
        _engine_mode = "transformers"
        _engine_dim = dim
        _engine_error = ""
        _model_error_detail = ""
        logger.info(f"Vector encoder ready: transformers/{name} dim={dim}")
    except Exception as exc:  # noqa: BLE001
        # 不静默：降级必须留下原因，否则「语义相似度很差」会被当成算法本身的问题。
        _engine_mode = "fallback-tfidf"
        _engine_dim = FALLBACK_DIM
        _engine_error = f"{type(exc).__name__}: {exc}"
        _model_error_detail = _engine_error
        logger.warning(
            f"Failed to load transformers, using TF-IDF fallback: {_engine_error}"
        )
    finally:
        _initialized = True


def _model_already_cached(cache_dir: str, model_name: str) -> bool:
    """缓存目录里是不是已经有这个模型的完整快照。"""
    try:
        if not os.path.isdir(cache_dir):
            return False
        tail = model_name.split("/")[-1]
        for entry in os.listdir(cache_dir):
            if not entry.startswith("models--") or not entry.endswith(tail):
                continue
            snapshots = os.path.join(cache_dir, entry, "snapshots")
            if not os.path.isdir(snapshots):
                continue
            for rev in os.listdir(snapshots):
                if os.listdir(os.path.join(snapshots, rev)):
                    return True
    except OSError as exc:
        # 判不出来就当没缓存（会走联网检查），但留个线索：多半是权限或路径问题
        logger.debug(f"探测模型缓存失败，按未缓存处理：{type(exc).__name__}: {exc}")
    return False


def _apply_hf_env(settings) -> None:
    """HuggingFace 官方站在部分网络下不可达，允许配置镜像（默认 hf-mirror）。

    模型已经下好时**自动切离线**。huggingface-hub 每次加载都会去线上做一圈
    HEAD 检查（adapter_config / processor_config / preprocessor_config…），
    实测把冷启动从 4.0s 拖到 12.0s —— 全花在等网络往返上，而且模型就在本地。
    命中缓存就置 HF_HUB_OFFLINE，既省这 8 秒，也让「断网也能启动」成立。
    """
    endpoint = (getattr(settings, "HF_ENDPOINT", "") or "").strip()
    if endpoint and not os.environ.get("HF_ENDPOINT"):
        os.environ["HF_ENDPOINT"] = endpoint

    if getattr(settings, "HF_HUB_OFFLINE", False):
        os.environ["HF_HUB_OFFLINE"] = "1"
        return

    if os.environ.get("HF_HUB_OFFLINE") != "1":
        cache_dir = getattr(settings, "resolved_model_dir", "")
        model_name = getattr(settings, "VECTOR_MODEL", "")
        if cache_dir and model_name and _model_already_cached(cache_dir, model_name):
            os.environ["HF_HUB_OFFLINE"] = "1"
            logger.info("模型已在本地缓存，本次加载走离线模式（跳过版本检查）")


def prepare(force: bool = False) -> bool:
    """显式准备编码器（供启动自检 / 重建向量用），返回是否用上了模型。

    force=True 会先清掉进程内的编码器再重新加载，用于「刚才失败了想再试一次」。
    必须与 _init_encoder 共用同一把锁：否则清空的动作可能插在别的线程
    正在用编码器的时候，把它手里的 _encoder 抽走。
    """
    global _encoder, _engine_mode, _engine_dim, _engine_error, _model_error_detail, _initialized
    with _init_lock:
        if force:
            _encoder = None
            _engine_mode = "fallback-tfidf"
            _engine_dim = FALLBACK_DIM
            _engine_error = ""
            _model_error_detail = ""
            _initialized = False
        if not _initialized:
            _load_encoder()
    return _engine_mode == "transformers"


def warm_up() -> None:
    """后台预加载模型，把首次请求的十几秒挪到启动期（不阻塞服务就绪）。

    为什么值得做：模型是延迟加载的，重启后第一个碰到向量引擎的请求
    （通常是「系统自检」）要等整个加载过程，实测 28~67 秒 ——
    用户看到的就是按钮点了半天没反应，很容易被当成服务挂了。
    """
    import threading as _t

    def _worker():
        try:
            _init_encoder()
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"向量引擎预热失败（不影响启动）：{type(exc).__name__}: {exc}")

    _t.Thread(target=_worker, name="vector-warmup", daemon=True).start()


def encode(text: str) -> List[float]:
    """将文本编码为向量"""
    _init_encoder()

    if _encoder is not None:
        try:
            vec = _encoder.encode(text, convert_to_numpy=True, normalize_embeddings=True)
            return _to_list(vec)
        except Exception as exc:  # noqa: BLE001
            logger.error(f"Transformers encode failed: {type(exc).__name__}: {exc}")

    return _tfidf_encode(text)


def encode_batch(texts: List[str]) -> List[List[float]]:
    """批量编码。走模型时单批一次前向，比逐条 encode 快一个量级。"""
    global _encoder, _engine_mode, _engine_dim
    _init_encoder()

    if _encoder is not None and texts:
        try:
            vecs = _encoder.encode(
                texts,
                convert_to_numpy=True,
                normalize_embeddings=True,
                batch_size=ENCODE_BATCH_SIZE,
                show_progress_bar=False,
            )
            return [_to_list(v) for v in vecs]
        except Exception as exc:  # noqa: BLE001
            # 这里原本是静默 pass —— 危险：编码器中途失败会让同一批节点出现
            # 「一部分模型向量、一部分 TF-IDF 向量」，两者维度不同时
            # cosine_similarity 直接返回 0（相似度静默失效）。
            # 至少留下告警，并禁用坏掉的编码器避免后续继续踩。
            logger.warning(
                f"向量模型编码失败（{type(exc).__name__}: {exc}），本次降级为 TF-IDF。"
                f"注意：降级向量与模型向量不可混用比较，修复后建议重建向量。"
            )
            _encoder = None
            _engine_mode = "fallback-tfidf"
            _engine_dim = FALLBACK_DIM

    return [_tfidf_encode(t) for t in texts]


def _to_list(vec) -> List[float]:
    if hasattr(vec, "tolist"):
        return vec.tolist()
    return [float(x) for x in vec]


def _tfidf_encode(text: str, dim: int = FALLBACK_DIM) -> List[float]:
    """TF-IDF 降级编码：词元加权后带符号哈希到固定维度，再 L2 归一。

    带符号哈希（signed hashing）是为了让碰撞的期望贡献为 0 ——
    只用取模时，两个无关词元撞到同一维会互相「加正分」，凭空制造相似度。
    """
    tokens = analyze(text)
    if not tokens:
        return [0.0] * dim

    tf: Dict[str, int] = {}
    for tok in tokens:
        tf[tok] = tf.get(tok, 0) + 1

    vec = [0.0] * dim
    for tok, freq in tf.items():
        # 次线性 TF：出现 10 次不等于重要 10 倍
        weight = (1.0 + math.log(freq)) * _weight(tok)
        digest = hashlib.md5(tok.encode("utf-8")).digest()
        h = int.from_bytes(digest[:8], "big")
        idx = h % dim
        sign = -1.0 if (h >> 63) & 1 else 1.0
        vec[idx] += sign * weight

    norm = math.sqrt(sum(x * x for x in vec))
    if norm > 0:
        vec = [x / norm for x in vec]
    return vec


# ---------------------------------------------------------------- 相似度

def cosine_similarity(a: List[float], b: List[float]) -> float:
    """计算余弦相似度

    维度不一致时返回 0：调用方应先用 is_stale 判断「是不是没法比」，
    不要把这里的 0 解读成「不相似」。
    """
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
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


# ---------------------------------------------------------------- 引擎指纹

def engine_signature() -> str:
    """当前引擎指纹：换模型 / 换编码方式 / 换维度都会变。"""
    _init_encoder()
    from app.config import settings
    if _engine_mode == "transformers":
        return f"st|{settings.VECTOR_MODEL}|{_engine_dim}|{ALGO_VERSION}"
    return f"tfidf|ngram|{FALLBACK_DIM}|{ALGO_VERSION}"


def embedding_is_stale(meta: Optional[str], sig: Optional[str] = None) -> bool:
    """这条向量的引擎指纹与当前引擎是否不一致（不一致就得重建）"""
    if not meta:
        return True
    return meta != (sig or engine_signature())


def get_engine_info() -> dict:
    """获取向量引擎信息"""
    _init_encoder()
    return {
        "mode": _engine_mode,
        "dim": _engine_dim,
        "signature": engine_signature(),
        "degraded": _engine_mode != "transformers",
        "reason": _engine_error,
        "idf": idf_stats(),
    }


def embedding_for(node_dict: dict) -> Optional[List[float]]:
    """从节点字典里取向量，兼容「JSON 字符串」与「已经是数组」两种存法。"""
    raw = node_dict.get("embedding")
    if not raw:
        return None
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return None
    return raw or None


# ---------------------------------------------------------------- 落库

def node_text(n: dict) -> str:
    """节点参与编码的文本。保持与 inference 里 β 维的取值一致，别各写一套。"""
    parts = []
    if n.get("entity"):
        parts.append(str(n["entity"]))
    if n.get("title"):
        parts.append(str(n["title"]))
    if n.get("keywords"):
        parts.append(" ".join(map(str, n["keywords"])))
    if n.get("entities"):
        parts.append(" ".join(map(str, n["entities"])))
    if n.get("description"):
        parts.append(str(n["description"]))
    return " ".join(parts).strip()


def embed_to_db(nodes: list, db) -> None:
    """为节点生成向量并存储到数据库（同时写入引擎指纹）"""
    from app.models.models import Node

    texts = [node_text(n) for n in nodes]
    if not texts:
        return

    # 降级路径依赖语料 IDF：这批还没入库，用「既有节点 + 这批」一起统计，
    # 保证新老向量在同一张 IDF 表下产出，可比较。
    if not _IDF and _engine_mode != "transformers":
        _init_encoder()
    if not _IDF and _engine_mode != "transformers":
        corpus = _existing_texts(db, texts)
        docs = build_idf(corpus)
        logger.info(f"TF-IDF 降级：用语料 {docs} 篇建立 IDF（{len(_IDF)} 个词元）")

    try:
        vectors = encode_batch(texts)
    except Exception as exc:  # noqa: BLE001
        logger.error(f"Batch encode failed: {type(exc).__name__}: {exc}")
        return

    sig = engine_signature()
    id_list = [n.get("id") for n in nodes if n.get("id")]
    node_rows = {n.id: n for n in db.query(Node).filter(Node.id.in_(id_list)).all()} if id_list else {}

    for i, node_data in enumerate(nodes):
        if i >= len(vectors):
            continue
        node = node_rows.get(node_data.get("id"))
        if node:
            node.embedding = json.dumps(vectors[i])
            node.embedding_meta = sig
    db.commit()


def _existing_texts(db, extra: List[str]) -> List[str]:
    """取库里已有节点的文本（给 IDF 统计用）。库不可用时只用本批。"""
    texts = list(extra)
    try:
        from app.models.models import Node
        for (entity, title, keywords, entities, description) in db.query(
            Node.entity, Node.title, Node.keywords, Node.entities, Node.description
        ).all():
            texts.append(node_text({
                "entity": entity, "title": title, "keywords": keywords,
                "entities": entities, "description": description,
            }))
    except Exception as exc:  # noqa: BLE001
        logger.debug(f"读取既有节点文本失败，IDF 只用本批统计：{type(exc).__name__}: {exc}")
    return texts


def rebuild_embeddings(db, user_id: Optional[int] = None, batch: int = 200) -> dict:
    """用当前引擎重建全部节点向量。

    装好模型之后必须跑一次，否则存量向量还是旧引擎（旧维度）产出的，
    与新建向量放在一起比较会恒为 0。
    """
    from app.models.models import Node

    query = db.query(Node)
    if user_id is not None:
        query = query.filter(Node.user_id == user_id)
    nodes = query.all()
    if not nodes:
        return {"total": 0, "updated": 0, "signature": engine_signature()}

    _init_encoder()
    sig_before = {n.embedding_meta for n in nodes if n.embedding_meta}

    # 先把整个语料的 IDF 建好（仅降级路径需要），再统一切词编码
    if _engine_mode != "transformers":
        build_idf([
            node_text({
                "entity": n.entity, "title": n.title, "keywords": n.keywords,
                "entities": n.entities, "description": n.description,
            })
            for n in nodes
        ])

    updated = 0
    for start in range(0, len(nodes), batch):
        chunk = nodes[start:start + batch]
        texts = [
            node_text({
                "entity": n.entity, "title": n.title, "keywords": n.keywords,
                "entities": n.entities, "description": n.description,
            })
            for n in chunk
        ]
        vectors = encode_batch(texts)
        for node, vec in zip(chunk, vectors):
            node.embedding = json.dumps(vec)
            node.embedding_meta = sig = engine_signature()
            updated += 1
        db.commit()

    return {
        "total": len(nodes),
        "updated": updated,
        "signature": engine_signature(),
        "previous_signatures": sorted(s for s in sig_before if s),
    }


def embedding_health(db) -> dict:
    """向量健康度：多少节点缺向量 / 陈旧 / 维度与当前引擎不符。"""
    from app.models.models import Node

    total = db.query(Node).count()
    with_vec = 0
    stale = 0
    empty = 0
    broken = 0
    dims: Dict[int, int] = {}
    sig = engine_signature()
    expected_dim = _engine_dim if _engine_mode == "transformers" else FALLBACK_DIM

    for (emb, meta) in db.query(Node.embedding, Node.embedding_meta).all():
        if not emb:
            empty += 1
            continue
        with_vec += 1
        if embedding_is_stale(meta, sig):
            stale += 1
        try:
            v = json.loads(emb)
            dims[len(v)] = dims.get(len(v), 0) + 1
        except (json.JSONDecodeError, TypeError):
            # 不静默：向量字段损坏会让该节点的 β 维恒为 0，必须能数出来。
            broken += 1

    return {
        "total": total,
        "with_embedding": with_vec,
        "empty": empty,
        "broken": broken,
        "stale": stale,
        "dims": dims,
        "engine_dim": expected_dim,
        "signature": sig,
        "degraded": _engine_mode != "transformers",
    }
