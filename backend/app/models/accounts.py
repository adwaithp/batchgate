"""User accounts."""

from sqlalchemy import Column, ForeignKey, String, Table
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.enums import Role
from app.models.mixins import TimestampMixin, str_enum

# Customers each sales user manages.
user_customers = Table(
    "user_customers",
    Base.metadata,
    Column("user_id", ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
    Column("customer_id", ForeignKey("customers.id", ondelete="CASCADE"), primary_key=True),
)


class User(TimestampMixin, Base):
    """A person who signs in; sales users see only their assigned customers."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(255))
    role: Mapped[Role] = mapped_column(str_enum(Role))
    hashed_password: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(default=True)

    customers: Mapped[list["Customer"]] = relationship(  # noqa: F821
        secondary=user_customers, lazy="selectin"
    )
