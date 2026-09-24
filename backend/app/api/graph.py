"""图谱构建 API"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, List
from app.database import get_db
from app.models.models import Node, Link

router = APIRouter()


class GraphOptions(BaseModel):
    group_id: Optional[str] = "all"
    user_id: int = 1
    include_discarded: bool = False
    weights: Optional[dict] = None


@router.post("/build")
def build_graph(options: GraphOptions = None, db: Session = Depends(get_db)):
    """构建图谱数据（节点+连线）"""
    if options is None:
        options = GraphOptions()

    user_id = options.user_id
    group_id = options.group_id

    # 查询节点
    query = db.query(Node).filter_by(user_id=user_id)

    if not options.include_discarded:
        query = query.filter(Node.status != "discarded")

    if group_id and group_id != "all":
        query = query.filter(Node.group_id == group_id)

    nodes = query.all()
    node_ids = [n.id for n in nodes]

    # 查询连线
    if node_ids:
        links = db.query(Link).filter(
            Link.source_id.in_(node_ids),
            Link.target_id.in_(node_ids)
        ).all()
    else:
        links = []

    # 格式化输出
    return {
        "nodes": [
            {
                "id": n.id,
                "fileId": n.file_id,
                "title": n.title or n.entity,
                "entity": n.entity,
                "description": n.description or "",
                "keywords": n.keywords or [],
                "entities": n.entities or [],
                "type": n.type,
                "level": n.level,
                "levelLabel": n.level_label,
                "domain": n.domain,
                "groupId": n.group_id,
                "groupName": n.group_name,
                "status": n.status,
                "validated": n.validated,
                "validateStatus": n.validate_status,
                "confidence": n.confidence,
                "visible": n.visible,
                "isolateBlackList": n.isolate_blacklist or [],
                "uploadTime": n.upload_time,
                "validate": {
                    "status": n.validate_status or "pending",
                    "issues": [],
                    "aiFix": None,
                    "manualEdit": None,
                    "confirmedAt": None
                }
            }
            for n in nodes
        ],
        "links": [
            {
                "id": l.id,
                "source": l.source_id,
                "target": l.target_id,
                "relation_type": l.relation_type,
                "relation_label": l.relation_label,
                "relation_color": l.relation_color,
                "relation_lineStyle": l.relation_line_style,
                "score": l.score,
                "final_weight": l.final_weight,
                "is_render": l.is_render,
                "evidence": l.evidence,
                "source_text": l.source_text,
                "source_file": l.source_file,
                "auto_generated": l.auto_generated,
                "user_confirmed": l.user_confirmed,
                "semantic_bridge": l.semantic_bridge,
                "timeBridge": l.time_bridge
            }
            for l in links
        ]
    }


@router.post("/update")
def update_graph(data: dict, db: Session = Depends(get_db)):
    """更新图谱数据（权重、阈值等）"""
    from app.models.models import UserSettings

    user_id = data.get("user_id", 1)
    settings = db.query(UserSettings).filter_by(user_id=user_id).first()

    if not settings:
        settings = UserSettings(user_id=user_id)
        db.add(settings)

    if "weights" in data:
        settings.weights = data["weights"]
    if "threshold" in data:
        settings.threshold = data["threshold"]
    if "corpus_enabled" in data:
        settings.corpus_enabled = data["corpus_enabled"]

    db.commit()
    return {"ok": True, "message": "配置已更新"}


@router.post("/rebuild")
def rebuild_graph(data: dict, db: Session = Depends(get_db)):
    """全量重排：删除全部自动连线后，按文件先后顺序重新推理（幂等，可反复执行）

    UI「强制重排全量图谱」调用此端点。
    """
    from app.models.models import File, Node, Link
    from app.services.inference import infer_links_for_new_file, _node_to_dict, infer_links_batch

    user_id = data.get("user_id", 1)
    weights = data.get("weights") or {}
    threshold = data.get("threshold") or 0.15

    files = db.query(File).filter_by(user_id=user_id).order_by(File.id.asc()).all()

    # 1) 清空该用户的自动连线
    node_ids = [n.id for n in db.query(Node).filter_by(user_id=user_id).all()]
    if node_ids:
        db.query(Link).filter(
            (Link.source_id.in_(node_ids)) | (Link.target_id.in_(node_ids))
        ).filter(Link.auto_generated.is_(True)).delete(synchronize_session=False)
    db.commit()

    # 2) 逐文件重推：新文件节点 vs 先前已解析文件的节点
    created = 0
    for i, f in enumerate(files):
        new_nodes = db.query(Node).filter_by(file_id=f.id, user_id=user_id).all()
        if not new_nodes:
            continue
        prior_ids = [ff.id for ff in files[:i]]
        existing = db.query(Node).filter(
            Node.file_id.in_(prior_ids) if prior_ids else Node.file_id == -1,
            Node.status == "active",
        ).all()
        new_dicts = [_node_to_dict(n) for n in new_nodes]
        existing_dicts = [_node_to_dict(n) for n in existing]

        links = infer_links_batch(
            new_dicts, user_id, weights, threshold, db,
            existing_nodes=existing_dicts
        )
        created += _persist_links(db, links)

    return {"ok": True, "created": created, "message": f"全量重排完成，新增 {created} 条连线"}


def _persist_links(db, links: list) -> int:
    """将推理结果写入 links 表（幂等去重）"""
    from app.models.models import Link
    count = 0
    for link_data in links:
        s, t = link_data["source"], link_data["target"]
        if s == t:
            continue
        exists = db.query(Link).filter(
            ((Link.source_id == s) & (Link.target_id == t)) |
            ((Link.source_id == t) & (Link.target_id == s))
        ).first()
        if exists:
            continue
        db.add(Link(
            source_id=s, target_id=t,
            relation_type=link_data.get("relation_type", "related"),
            relation_label=link_data.get("relation_label", "相关"),
            score=link_data.get("score", 0.0),
            final_weight=link_data.get("final_weight", link_data.get("score", 0.0)),
            evidence=link_data.get("evidence", ""),
            source_text=link_data.get("source_text", ""),
            source_file=link_data.get("source_file", ""),
            auto_generated=True,
            semantic_bridge=bool(link_data.get("sim_corpus", 0) > 0),
            time_bridge=bool(link_data.get("time_bridge", False)),
        ))
        count += 1
    db.commit()
    return count