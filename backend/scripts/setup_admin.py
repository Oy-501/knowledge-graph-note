"""配置管理员账号：把指定用户规范化为管理员，重设密码并签发恢复码。

用法：
    py scripts/setup_admin.py --user-id 1 --username admin --password "..."

不给 --password 时自动生成 15 位强密码，明文只在本次输出中出现一次。
"""
import argparse
import os
import secrets
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

# 固定落到本机 SQLite 库，避免 auto 模式去探测 PostgreSQL
os.environ.setdefault("DB_MODE", "sqlite")
os.environ.setdefault("SQLITE_PATH", str(BACKEND / "kg.db"))

from app.config import settings  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.models.models import User  # noqa: E402
from app.services import auth_service, audit  # noqa: E402

_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789"


def generate_password(length: int = 15) -> str:
    """生成随机强口令。"""
    rng = secrets.SystemRandom()
    chars = [rng.choice(_ALPHABET) for _ in range(length - 2)]
    chars += [rng.choice("23456789"), rng.choice("@#$%&*+-=")]
    rng.shuffle(chars)
    return "".join(chars)


def main() -> int:
    """命令行入口：配置管理员账号。"""
    parser = argparse.ArgumentParser(description="配置管理员账号")
    parser.add_argument("--user-id", type=int, default=1)
    parser.add_argument("--username", default="admin")
    parser.add_argument("--password", default="")
    args = parser.parse_args()

    print("db_url =", settings.resolved_database_url)

    db = SessionLocal()
    try:
        user = db.query(User).filter_by(id=args.user_id).first()
        if user is None:
            print(f"错误：用户 id={args.user_id} 不存在")
            return 1
        if db.query(User).filter(User.username == args.username,
                                 User.id != user.id).first():
            print(f"错误：用户名 {args.username} 已被占用")
            return 1

        password = args.password or generate_password()
        auth_service._validate_credentials(args.username, password)

        recovery_code = auth_service.generate_recovery_code()

        print("old_username =", user.username)
        user.username = args.username
        user.password_hash = auth_service.hash_password(password)
        user.recovery_hash = auth_service.hash_password(
            auth_service.normalize_recovery_code(recovery_code))
        user.role = "admin"
        user.is_disabled = False
        db.commit()

        revoked = auth_service.revoke_user_sessions(db, user.id)
        audit.log_event(
            db, "user_update", actor="admin", user_id=user.id,
            target_type="user", target_id=user.id, target_name=user.username,
            summary=f"规范化管理员账号：重设密码与恢复码，吊销 {revoked} 个会话",
        )

        print("username =", user.username)
        print("password =", password)
        print("recovery_code =", recovery_code)
        print("revoked_sessions =", revoked)
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
