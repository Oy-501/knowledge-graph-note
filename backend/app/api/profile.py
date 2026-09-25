"""个人主页 API：资料、头像与自定义背景（图片存服务端，跨设备可用）

图片上传的约束：
  - 限制大小（settings.MAX_IMAGE_MB）与类型（按**文件头魔数**判断，不信任扩展名）；
  - 落盘到 settings.UPLOAD_DIR/{avatars|backgrounds}/，文件名随机化，避免覆盖与猜测；
  - 通过 /uploads 静态目录对外提供，URL 存进 user_profiles。
"""
import os
import secrets
from datetime import datetime

from fastapi import APIRouter, Depends, File as FastAPIFile, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models.models import File, KnowledgeBase, KnowledgeCandidate, Node, User, UserProfile
from app.services import audit

router = APIRouter()

# 图片魔数 → 扩展名
_MAGIC = [
    (b"\xff\xd8\xff", "jpg"),
    (b"\x89PNG\r\n\x1a\n", "png"),
    (b"GIF87a", "gif"),
    (b"GIF89a", "gif"),
    (b"RIFF", "webp"),          # RIFF....WEBP
]


def _upload_root() -> str:
    root = settings.UPLOAD_DIR
    if not os.path.isabs(root):
        root = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__)))), root.lstrip("./"))
    os.makedirs(root, exist_ok=True)
    return root


def _detect_image(raw: bytes) -> str:
    for magic, ext in _MAGIC:
        if raw.startswith(magic):
            if ext == "webp" and b"WEBP" not in raw[:16]:
                continue
            return ext
    return ""


async def _save_image(upload: UploadFile, kind: str) -> str:
    """保存图片并返回可访问 URL"""
    limit = settings.MAX_IMAGE_MB * 1024 * 1024
    raw = await upload.read(limit + 1)
    if len(raw) > limit:
        raise HTTPException(status_code=413,
                            detail=f"图片超过 {settings.MAX_IMAGE_MB}MB 上限，请压缩后再上传")
    if not raw:
        raise HTTPException(status_code=400, detail="图片内容为空")
    ext = _detect_image(raw)
    if not ext:
        raise HTTPException(status_code=415,
                            detail="仅支持 JPG / PNG / GIF / WebP 图片（已按文件头校验）")

    folder = os.path.join(_upload_root(), kind)
    os.makedirs(folder, exist_ok=True)
    name = f"{kind}_{datetime.now().strftime('%Y%m%d%H%M%S')}_{secrets.token_hex(4)}.{ext}"
    with open(os.path.join(folder, name), "wb") as f:
        f.write(raw)
    return f"/uploads/{kind}/{name}"


def _get_or_create_profile(db: Session, user_id: int) -> UserProfile:
    p = db.query(UserProfile).filter_by(user_id=user_id).first()
    if not p:
        user = db.query(User).filter_by(id=user_id).first()
        # 单用户模式下 username 是 "default"，直接拿来当昵称很怪，留空由用户自己填
        name = user.username if (user and user.username not in ("default", "")) else ""
        p = UserProfile(user_id=user_id, display_name=name, bio="",
                        background_config={"opacity": 0.8, "blur": 0, "scope": "global", "fit": "cover"})
        db.add(p)
        db.commit()
        db.refresh(p)
    return p


def _profile_dict(p: UserProfile) -> dict:
    return {
        "user_id": p.user_id,
        "display_name": p.display_name or "",
        "bio": p.bio or "",
        "avatar_url": p.avatar_url or "",
        "background_url": p.background_url or "",
        "background_config": p.background_config or {
            "opacity": 0.8, "blur": 0, "scope": "global", "fit": "cover"},
        "updated_at": p.updated_at.isoformat() if p.updated_at else None,
    }


@router.get("")
def get_profile(user_id: int = 1, db: Session = Depends(get_db)):
    """读取个人主页资料"""
    return {"ok": True, "profile": _profile_dict(_get_or_create_profile(db, user_id))}


@router.get("/overview")
def profile_overview(user_id: int = 1, db: Session = Depends(get_db)):
    """个人主页上的「我的数据」概览"""
    from app.models.models import AuditLog
    return {
        "ok": True,
        "stats": {
            "files": db.query(File).filter_by(user_id=user_id).count(),
            "nodes": db.query(Node).filter_by(user_id=user_id).count(),
            "candidates": db.query(KnowledgeCandidate).filter_by(user_id=user_id).count(),
            "pending_review": db.query(KnowledgeCandidate).filter_by(
                user_id=user_id, status="open").count(),
            "accepted": db.query(KnowledgeCandidate).filter_by(
                user_id=user_id, status="accepted").count(),
            "audit_rows": db.query(AuditLog).filter_by(user_id=user_id).count(),
            "kb_entries": db.query(KnowledgeBase).count(),
        },
    }


class ProfilePayload(BaseModel):
    display_name: str = ""
    bio: str = ""
    background_config: dict = {}


@router.put("")
def update_profile(payload: ProfilePayload, user_id: int = 1, db: Session = Depends(get_db)):
    """更新昵称/简介/背景参数"""
    p = _get_or_create_profile(db, user_id)
    before = {"display_name": p.display_name, "bio": (p.bio or "")[:60],
              "background_config": p.background_config}
    if payload.display_name is not None:
        p.display_name = payload.display_name[:100]
    if payload.bio is not None:
        p.bio = payload.bio[:1000]
    if payload.background_config:
        cfg = dict(p.background_config or {})
        cfg.update(payload.background_config)
        p.background_config = cfg
    p.updated_at = datetime.utcnow()
    db.commit()

    audit.log_event(
        db, "profile_update", actor="user", user_id=user_id, target_type="profile",
        target_id=user_id, target_name=p.display_name,
        summary="更新个人主页资料/背景设置",
        detail={"before": before, "after": {
            "display_name": p.display_name, "bio": (p.bio or "")[:60],
            "background_config": p.background_config}},
    )
    return {"ok": True, "profile": _profile_dict(p)}


@router.post("/avatar")
async def upload_avatar(file: UploadFile = FastAPIFile(...), user_id: int = 1,
                        db: Session = Depends(get_db)):
    """上传头像"""
    p = _get_or_create_profile(db, user_id)
    old = p.avatar_url
    url = await _save_image(file, "avatars")
    p.avatar_url = url
    p.updated_at = datetime.utcnow()
    db.commit()
    audit.log_event(
        db, "profile_upload", actor="user", user_id=user_id, target_type="profile",
        target_id=user_id, summary=f"上传头像 {url}",
        detail={"kind": "avatar", "url": url, "replaced": old,
                "limits": {"max_mb": settings.MAX_IMAGE_MB,
                           "types": ["jpg", "png", "gif", "webp"],
                           "校验方式": "文件头魔数"}},
    )
    _cleanup_old(old, url)
    return {"ok": True, "avatar_url": url, "profile": _profile_dict(p)}


@router.post("/background")
async def upload_background(file: UploadFile = FastAPIFile(...), user_id: int = 1,
                            db: Session = Depends(get_db)):
    """上传自定义背景图"""
    p = _get_or_create_profile(db, user_id)
    old = p.background_url
    url = await _save_image(file, "backgrounds")
    p.background_url = url
    cfg = dict(p.background_config or {})
    cfg.setdefault("opacity", 0.8)
    cfg.setdefault("blur", 0)
    cfg.setdefault("scope", "global")
    cfg.setdefault("fit", "cover")
    p.background_config = cfg
    p.updated_at = datetime.utcnow()
    db.commit()
    audit.log_event(
        db, "profile_upload", actor="user", user_id=user_id, target_type="profile",
        target_id=user_id, summary=f"上传自定义背景 {url}",
        detail={"kind": "background", "url": url, "replaced": old,
                "config": cfg,
                "limits": {"max_mb": settings.MAX_IMAGE_MB}},
    )
    _cleanup_old(old, url)
    return {"ok": True, "background_url": url, "profile": _profile_dict(p)}


@router.delete("/background")
def clear_background(user_id: int = 1, db: Session = Depends(get_db)):
    """移除自定义背景（回到预设/纯色）"""
    p = _get_or_create_profile(db, user_id)
    old = p.background_url
    p.background_url = None
    p.updated_at = datetime.utcnow()
    db.commit()
    audit.log_event(db, "profile_update", actor="user", user_id=user_id,
                    target_type="profile", target_id=user_id,
                    summary="移除自定义背景", detail={"removed": old}, status="warn")
    _cleanup_old(old, "")
    return {"ok": True, "profile": _profile_dict(p)}


def _cleanup_old(old_url: str, new_url: str):
    """删除被替换掉的旧图片文件（只删自己 uploads 目录里的）"""
    if not old_url or old_url == new_url or not old_url.startswith("/uploads/"):
        return
    try:
        rel = old_url[len("/uploads/"):]
        path = os.path.join(_upload_root(), rel)
        if os.path.isfile(path) and _upload_root() in os.path.abspath(path):
            os.remove(path)
    except OSError:
        pass
