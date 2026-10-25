"""学习提醒：SM-2 间隔推进与到期过滤。"""
from app.models.models import User
from app.services.learning_service import add_review, due_reviews, next_interval, review, stats


def _user(db, name: str) -> User:
    user = User(username=name, password_hash="x")
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def test_interval_progression():
    interval, _ = next_interval(1, 2.5, 5)
    assert interval == 3
    interval, _ = next_interval(3, 2.5, 5)
    assert interval == 6
    interval, _ = next_interval(6, 2.5, 5)
    assert interval > 6


def test_failed_review_resets_interval():
    interval, ease = next_interval(10, 2.5, 2)
    assert interval == 1
    assert ease < 2.5


def test_add_and_due(db):
    user = _user(db, "learn_user")
    row = add_review(db, user.id, post_id=1, title="复习项")
    assert row["already"] is False

    due = due_reviews(db, user.id)
    assert due["due"] == 1
    assert due["items"][0]["title"] == "复习项"

    again = add_review(db, user.id, post_id=1, title="复习项")
    assert again["already"] is True
    assert due_reviews(db, user.id)["total"] == 1


def test_review_moves_due_date_forward(db):
    user = _user(db, "learn_reviewer")
    add_review(db, user.id, post_id=2, title="待复习")
    item = due_reviews(db, user.id)["items"][0]

    out = review(db, item["id"], user.id, 5)
    assert out["interval_days"] == 3
    assert out["review_count"] == 1
    assert due_reviews(db, user.id)["due"] == 0
    assert stats(db, user.id)["total"] == 1


def test_review_requires_owner(db):
    from app.services.errors import AppError

    owner = _user(db, "learn_owner")
    other = _user(db, "learn_other")
    add_review(db, owner.id, post_id=3, title="别人的复习项")
    item = due_reviews(db, owner.id)["items"][0]

    try:
        review(db, item["id"], other.id, 4)
    except AppError as exc:
        assert exc.status_code == 404
    else:
        raise AssertionError("不应允许修改他人的复习计划")
