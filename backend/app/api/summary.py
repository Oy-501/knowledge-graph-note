"""图谱总结 API：总结 / 流程图(Mermaid) / AI 摘要 / 文档与 PPT 导出"""
import json
from typing import Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.graph_summary import attach_raw_links, build_summary, to_ai_digest, to_mermaid
from app.services import summary_export as exporter

router = APIRouter()


def _build(db: Session, user_id: int, group_by: str, max_paths: int):
    summary = build_summary(db, user_id=user_id, max_paths=max_paths)
    attach_raw_links(summary, db, user_id=user_id)
    mermaid = to_mermaid(summary, group_by=group_by)
    return summary, mermaid


def _public(summary: dict) -> dict:
    """去掉内部字段（原始连线明细 / 全量节点索引），保持响应体轻量"""
    return {k: v for k, v in summary.items() if k not in ("_raw_links", "node_index")}


class SummaryOptions(BaseModel):
    user_id: int = 1
    group_by: str = "level"      # level | domain
    max_paths: int = 6
    title: str = "知识图谱总结"


@router.post("/build")
def build(options: SummaryOptions = None, db: Session = Depends(get_db)):
    """生成图谱总结：结构化数据 + Mermaid 流程图 + AI 可读摘要"""
    options = options or SummaryOptions()
    summary, mermaid = _build(db, options.user_id, options.group_by, options.max_paths)
    return {
        "ok": True,
        "summary": _public(summary),
        "mermaid": mermaid,
        "ai_digest": to_ai_digest(summary),
        "empty": summary.get("empty", False),
    }


@router.get("/mermaid")
def get_mermaid(user_id: int = 1, group_by: str = "level",
                db: Session = Depends(get_db)):
    """只取总结流程图（Mermaid 源码）"""
    summary, mermaid = _build(db, user_id, group_by, 6)
    return {"ok": True, "mermaid": mermaid, "node_count": summary["overview"].get("node_count", 0)}


@router.get("/ai-digest")
def get_ai_digest(user_id: int = 1, db: Session = Depends(get_db)):
    """AI 可读摘要（纯文本，直接投喂大模型）"""
    summary, _ = _build(db, user_id, "level", 6)
    return {"ok": True, "digest": to_ai_digest(summary)}


@router.get("/download")
def download(
    fmt: str = Query("md", pattern="^(md|docx|pptx|mermaid|mmd|digest|json)$"),
    user_id: int = 1,
    group_by: str = "level",
    title: str = "知识图谱总结",
    db: Session = Depends(get_db),
):
    """导出总结：Markdown / Word / PPTX / Mermaid / AI 摘要 / JSON"""
    summary, mermaid = _build(db, user_id, group_by, 6)

    if fmt == "json":
        path = exporter.export_path("知识图谱总结", "json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(_public(summary), f, ensure_ascii=False, indent=2)
        return FileResponse(path, filename=f"{title}.json",
                            media_type="application/json")
    if fmt in ("mermaid", "mmd"):
        path = exporter.export_path("知识图谱流程图", "mmd")
        with open(path, "w", encoding="utf-8") as f:
            f.write(mermaid)
        return FileResponse(path, filename="知识图谱流程图.mmd",
                            media_type="text/plain; charset=utf-8")
    if fmt == "digest":
        path = exporter.to_ai_digest_file(summary)
        return FileResponse(path, filename="知识图谱AI摘要.md",
                            media_type="text/markdown; charset=utf-8")
    if fmt == "docx":
        path = exporter.to_docx(summary, mermaid, title=title)
        return FileResponse(
            path, filename=f"{title}.docx",
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document")
    if fmt == "pptx":
        path = exporter.to_pptx(summary, mermaid, title=title)
        return FileResponse(
            path, filename=f"{title}.pptx",
            media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation")

    path = exporter.export_path("知识图谱总结", "md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(exporter.to_markdown(summary, mermaid, title=title))
    return FileResponse(path, filename=f"{title}.md", media_type="text/markdown; charset=utf-8")
