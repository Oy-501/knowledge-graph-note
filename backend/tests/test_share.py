"""分享空间：判定、点赞唯一、推荐与搜索。"""
from app.models.models import PostLike, SharedPost, User
from app.services.share_service import (create_post, judge_post, like_post, list_posts,
                                        recommend, search, unlike_post)


def _user(db, name: str) -> User:
    user = User(username=name, password_hash="x")
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _post(db, user_id: int, title: str, domain: str = "frontend",
          likes: int = 0) -> SharedPost:
    post = SharedPost(user_id=user_id, title=title, summary="内容", domain=domain,
                      status="approved", like_count=likes)
    db.add(post)
    db.commit()
    db.refresh(post)
    return post


def test_judge_approved():
    status, score, _ = judge_post(
        "数据库索引原理",
        "B+ 树是索引最常用的数据结构，用于加速查询。",
        "B+ 树是一种平衡树，由根节点和叶子节点组成，广泛用于数据库索引。" * 3)
    assert status == "approved"
    assert score >= 0.6


def test_judge_pending_for_thin_content():
    status, score, _ = judge_post("1. 索引", "短", "")
    assert status == "pending"
    assert score < 0.6


def test_like_is_idempotent(db):
    author = _user(db, "share_author")
    reader = _user(db, "share_reader")
    post = _post(db, author.id, "前端工程化")

    first = like_post(db, post.id, reader.id)
    assert first["liked"] is True
    assert first["already"] is False
    assert first["like_count"] == 1

    second = like_post(db, post.id, reader.id)
    assert second["already"] is True
    assert second["like_count"] == 1
    assert db.query(PostLike).filter_by(post_id=post.id, user_id=reader.id).count() == 1

    other = like_post(db, post.id, author.id)
    assert other["like_count"] == 2


def test_unlike_never_goes_negative(db):
    author = _user(db, "unlike_author")
    post = _post(db, author.id, "状态管理")
    result = unlike_post(db, post.id, author.id)
    assert result["like_count"] == 0


def test_like_rejects_pending(db):
    from app.services.errors import AppError

    author = _user(db, "pending_author")
    post = SharedPost(user_id=author.id, title="待审内容", status="pending")
    db.add(post)
    db.commit()
    db.refresh(post)
    try:
        like_post(db, post.id, author.id)
    except AppError as exc:
        assert exc.status_code == 409
    else:
        raise AssertionError("pending 分享不应允许点赞")


def test_recommend_prefers_same_domain(db):
    me = _user(db, "rec_me")
    other = _user(db, "rec_other")
    _post(db, me.id, "我上传的前端笔记", domain="frontend")
    same = _post(db, other.id, "同领域热门", domain="frontend", likes=10)
    far = _post(db, other.id, "生物领域热门", domain="biology", likes=10)

    items = recommend(db, me.id, limit=5)["items"]
    ids = [x["id"] for x in items]
    assert ids.index(same.id) < ids.index(far.id)
    assert items[0]["reason"] == "同领域内容"


def test_search_filters_and_escapes(db):
    author = _user(db, "search_author")
    _post(db, author.id, "Vue 组件通信")
    _post(db, author.id, "数据库索引")

    hit = search(db, author.id, "Vue")
    assert hit["total"] == 1
    assert hit["items"][0]["title"] == "Vue 组件通信"

    # LIKE 通配符必须被转义，不能当成「匹配一切」
    assert search(db, author.id, "%")["total"] == 0


def test_create_post_enters_pending_or_approved(db):
    user = _user(db, "create_user")
    thin = create_post(db, user.id, "短标题", "短", "")
    assert thin["status"] == "pending"

    full = create_post(
        db, user.id, "CSS 层叠上下文",
        "层叠上下文决定元素在 z 轴上的绘制顺序。",
        "层叠上下文是一种由特定 CSS 属性创建的独立渲染层级，"
        "包含根元素、定位元素与 transform 元素等。" * 3)
    assert full["status"] == "approved"


def test_list_only_shows_approved_or_mine(db):
    author = _user(db, "list_author")
    viewer = _user(db, "list_viewer")
    _post(db, author.id, "公开内容")
    pending = SharedPost(user_id=author.id, title="未通过内容", status="pending")
    db.add(pending)
    db.commit()

    public = list_posts(db, viewer.id, limit=20)
    titles = [x["title"] for x in public["items"]]
    assert "公开内容" in titles
    assert "未通过内容" not in titles

    mine = list_posts(db, author.id, limit=20)
    assert "未通过内容" in [x["title"] for x in mine["items"]]
