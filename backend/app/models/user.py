import enum

from sqlalchemy import Boolean, Enum as SAEnum, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class UserRole(str, enum.Enum):
    admin = "admin"
    recruiter = "recruiter"
    viewer = "viewer"


class User(Base):
    """Application user account with role-based access control."""

    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(
        SAEnum(UserRole, name="user_role", create_constraint=False),
        nullable=False,
        default=UserRole.recruiter,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
