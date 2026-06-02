import os

from sqlalchemy.orm import Session

import backend.models.domain as models
from backend.auth import hash_password


DEFAULT_ADMIN_ENABLED = os.getenv("SAFECHAT_CREATE_DEFAULT_ADMIN", "1").strip().lower() not in {
    "0",
    "false",
    "no",
}
DEFAULT_ADMIN_USERNAME = os.getenv("SAFECHAT_DEFAULT_ADMIN_USERNAME", "admin").strip() or "admin"
DEFAULT_ADMIN_EMAIL = os.getenv("SAFECHAT_DEFAULT_ADMIN_EMAIL", "admin@safechat.local").strip().lower() or "admin@safechat.local"
DEFAULT_ADMIN_PASSWORD = os.getenv("SAFECHAT_DEFAULT_ADMIN_PASSWORD", "Admin123!").strip() or "Admin123!"
DEFAULT_ADMIN_NAME = os.getenv("SAFECHAT_DEFAULT_ADMIN_NAME", "SafeChat Admin").strip() or "SafeChat Admin"


def ensure_default_admin(db: Session) -> None:
    if not DEFAULT_ADMIN_ENABLED:
        return

    email_match = db.query(models.User).filter(models.User.email == DEFAULT_ADMIN_EMAIL).first()
    username_match = db.query(models.User).filter(models.User.username == DEFAULT_ADMIN_USERNAME).first()

    if email_match and username_match and email_match.id != username_match.id:
        print(
            "Warning: default admin seed skipped because the configured email and username belong to different users."
        )
        return

    user = email_match or username_match
    if user is None:
        user = models.User(
            username=DEFAULT_ADMIN_USERNAME,
            email=DEFAULT_ADMIN_EMAIL,
            password_hash=hash_password(DEFAULT_ADMIN_PASSWORD),
            role="admin",
            is_active=True,
            name=DEFAULT_ADMIN_NAME,
        )
        db.add(user)
        db.commit()
        return

    user.username = DEFAULT_ADMIN_USERNAME
    user.email = DEFAULT_ADMIN_EMAIL
    user.password_hash = hash_password(DEFAULT_ADMIN_PASSWORD)
    user.role = "admin"
    user.is_active = True
    if not user.name:
        user.name = DEFAULT_ADMIN_NAME
    db.commit()
