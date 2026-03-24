from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Optional, List

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
    text,
    Index,
)
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
    relationship,
)


# === БАЗА ===
class Base(DeclarativeBase):
    pass


# === USERS ===
class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True, nullable=False)

    full_name: Mapped[str] = mapped_column(String(100), nullable=False)
    phone: Mapped[str] = mapped_column(String(20), nullable=False)
    email: Mapped[Optional[str]] = mapped_column(String(100))

    balance_cents: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    is_admin: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("False"))
    # timestamptz
    subscription_until: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    # 1–N заказы, где пользователь — заказчик
    orders: Mapped[List["Order"]] = relationship(
        "Order",
        back_populates="user",
        foreign_keys="Order.user_id",
        lazy="selectin",
    )

    # ---- методы и свойства ----
    def is_subscribed_utc(self) -> bool:
        """Безопасная проверка подписки: aware-UTC сравнение."""
        if not self.subscription_until:
            return False
        dt = self.subscription_until
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt > datetime.now(timezone.utc)

    @property
    def balance_rub(self) -> float:
        return round((self.balance_cents or 0) / 100, 2)

    def add_funds_kop(self, amount_kop: int) -> None:
        self.balance_cents = int(self.balance_cents or 0) + int(amount_kop)

    def add_funds(self, amount_cents: int) -> None:
        self.add_funds_kop(amount_cents)

    def charge_kop(self, amount_kop: int) -> bool:
        if (self.balance_cents or 0) < int(amount_kop):
            return False
        self.balance_cents -= int(amount_kop)
        return True

    def activate_subscription(self, days: int) -> None:
        base = self.subscription_until or datetime.now(timezone.utc)
        if base.tzinfo is None:
            base = base.replace(tzinfo=timezone.utc)
        self.subscription_until = base + timedelta(days=int(days))



# === PAYMENTS ===
class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(primary_key=True)

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)  # +пополнение / -списание
    kind: Mapped[str] = mapped_column(String(32), nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    user: Mapped["User"] = relationship()



# === ORDERS ===
class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(primary_key=True)

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )  # заказчик

    worker_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )  # исполнитель

    title: Mapped[str] = mapped_column(String(200), nullable=False)

    # timestamptz
    start_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    description: Mapped[str] = mapped_column(Text, nullable=False)
    photo: Mapped[Optional[str]] = mapped_column(String(300))
    file: Mapped[Optional[str]] = mapped_column(String(300))

    price_cents: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))

    status: Mapped[str] = mapped_column(String(50), nullable=False, server_default=text("'Ожидает откликов'"))
    channel_message_id: Mapped[Optional[int]] = mapped_column(Integer)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    cancel_pending: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    cancel_reason: Mapped[Optional[str]] = mapped_column(Text)

    user: Mapped["User"] = relationship(  # заказчик
        foreign_keys=[user_id],
        back_populates="orders",
    )


# индексы для orders
Index("ix_orders_status", Order.status)
Index("ix_orders_created_at", Order.created_at)


# === SUPPORT THREADS ===
class SupportThread(Base):
    __tablename__ = "support_threads"

    id: Mapped[int] = mapped_column(primary_key=True)

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,   # один активный тред на пользователя
        nullable=False,
        index=True,
    )
    thread_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False, index=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    user: Mapped["User"] = relationship()


# === OFFERS ===
class Offer(Base):
    __tablename__ = "offers"

    id: Mapped[int] = mapped_column(primary_key=True)

    order_id: Mapped[int] = mapped_column(
        ForeignKey("orders.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    worker_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    message: Mapped[str] = mapped_column(Text, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # связи
    order: Mapped["Order"] = relationship("Order")
    worker: Mapped["User"] = relationship("User")