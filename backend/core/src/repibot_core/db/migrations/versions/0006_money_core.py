"""Коммерческие заказы, платежные попытки и будущие денежные журналы.

Revision ID: 0006
Revises: 0005
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None

ORDER_PURPOSE = sa.Enum("purchase", "renew", "gift", name="order_purpose")
ORDER_STATUS = sa.Enum(
    "pending", "fulfilled", "expired", "canceled", "refunded", name="order_status"
)
PAYMENT_PROVIDER = sa.Enum("yookassa", "stars", name="payment_provider")
PAYMENT_STATUS = sa.Enum("pending", "succeeded", "canceled", "failed", name="payment_status")


def upgrade() -> None:
    op.create_table(
        "orders",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("purpose", ORDER_PURPOSE, nullable=False),
        sa.Column("plan_id", sa.Integer(), sa.ForeignKey("plans.id"), nullable=False),
        sa.Column("plan_code_snapshot", sa.String(32), nullable=False),
        sa.Column("plan_name_snapshot", postgresql.JSONB(), nullable=False),
        sa.Column("duration_days_snapshot", sa.Integer(), nullable=False),
        sa.Column("price_rub_snapshot", sa.Numeric(10, 2), nullable=False),
        sa.Column("price_stars_snapshot", sa.Integer(), nullable=False),
        sa.Column("gross_rub", sa.Numeric(10, 2), nullable=False),
        sa.Column("discount_rub", sa.Numeric(10, 2), nullable=False, server_default="0.00"),
        sa.Column("amount_due_rub", sa.Numeric(10, 2), nullable=False),
        sa.Column("promo_code_id", sa.Integer(), nullable=True),
        sa.Column("client_key", sa.String(128), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", ORDER_STATUS, nullable=False, server_default="pending"),
        sa.Column("fulfilled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("user_id", "client_key", name="uq_orders_user_client_key"),
        sa.CheckConstraint("duration_days_snapshot > 0", name="ck_orders_duration_positive"),
        sa.CheckConstraint("price_rub_snapshot >= 0", name="ck_orders_price_nonnegative"),
        sa.CheckConstraint("price_stars_snapshot >= 0", name="ck_orders_stars_nonnegative"),
        sa.CheckConstraint("gross_rub >= 0", name="ck_orders_gross_nonnegative"),
        sa.CheckConstraint("discount_rub >= 0", name="ck_orders_discount_nonnegative"),
        sa.CheckConstraint("amount_due_rub >= 0", name="ck_orders_due_nonnegative"),
        sa.CheckConstraint(
            "amount_due_rub = gross_rub - discount_rub", name="ck_orders_due_matches"
        ),
    )
    op.create_table(
        "payment_attempts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "order_id", sa.Integer(), sa.ForeignKey("orders.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("provider", PAYMENT_PROVIDER, nullable=False),
        sa.Column("attempt_no", sa.Integer(), nullable=False),
        sa.Column("provider_key", sa.String(128), nullable=False),
        sa.Column("provider_payment_id", sa.String(255), nullable=True),
        sa.Column("status", PAYMENT_STATUS, nullable=False, server_default="pending"),
        sa.Column("verified_payload", postgresql.JSONB(), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint(
            "order_id", "provider", "attempt_no", name="uq_attempts_order_provider_no"
        ),
        sa.UniqueConstraint("provider", "provider_key", name="uq_attempts_provider_key"),
        sa.UniqueConstraint(
            "provider", "provider_payment_id", name="uq_attempts_provider_payment_id"
        ),
        sa.CheckConstraint("attempt_no > 0", name="ck_attempts_number_positive"),
    )

    # Эти журналы получают сервисы следующих задач. Их ключи уже сейчас
    # принадлежат базе: проверка «есть ли запись» до INSERT не защищает гонки.
    op.create_table(
        "promo_reservations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "order_id", sa.Integer(), sa.ForeignKey("orders.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("promo_code_id", sa.Integer(), nullable=False),
        sa.Column(
            "user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "reserved_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("order_id", name="uq_promo_reservations_order"),
    )
    op.create_table(
        "gift_vouchers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "order_id", sa.Integer(), sa.ForeignKey("orders.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("code", sa.String(64), nullable=False),
        sa.Column(
            "purchased_by_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "redeemed_by_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")
        ),
        sa.Column("redeemed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("order_id", name="uq_gift_vouchers_order"),
        sa.UniqueConstraint("code", name="uq_gift_vouchers_code"),
    )
    op.create_table(
        "referral_rewards",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "referrer_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "referee_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("origin_order_id", sa.Integer(), sa.ForeignKey("orders.id"), nullable=False),
        sa.Column("days", sa.Integer(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("reversed_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("origin_order_id", name="uq_referral_rewards_origin_order"),
        sa.CheckConstraint("days > 0", name="ck_referral_rewards_days_positive"),
    )
    op.create_table(
        "notification_deliveries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "order_id", sa.Integer(), sa.ForeignKey("orders.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("kind", sa.String(64), nullable=False),
        sa.Column("channel", sa.String(16), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error", sa.String(512), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("order_id", "kind", "channel", name="uq_notification_deliveries_dedup"),
    )

    # Нельзя допустить, чтобы обработчик позднее дочитал изменившийся тариф
    # вместо согласованного покупателем снимка. CHECK не умеет сравнивать OLD
    # и NEW, поэтому неизменность гарантирует короткий серверный триггер.
    op.execute(
        """
        CREATE FUNCTION orders_reject_snapshot_mutation() RETURNS trigger AS $$
        BEGIN
            IF (NEW.plan_id, NEW.plan_code_snapshot, NEW.plan_name_snapshot,
                NEW.duration_days_snapshot, NEW.price_rub_snapshot,
                NEW.price_stars_snapshot, NEW.gross_rub, NEW.discount_rub,
                NEW.amount_due_rub, NEW.promo_code_id)
               IS DISTINCT FROM
               (OLD.plan_id, OLD.plan_code_snapshot, OLD.plan_name_snapshot,
                OLD.duration_days_snapshot, OLD.price_rub_snapshot,
                OLD.price_stars_snapshot, OLD.gross_rub, OLD.discount_rub,
                OLD.amount_due_rub, OLD.promo_code_id) THEN
                RAISE EXCEPTION 'order commercial snapshot is immutable';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER orders_reject_snapshot_mutation_trigger
        BEFORE UPDATE ON orders
        FOR EACH ROW EXECUTE FUNCTION orders_reject_snapshot_mutation();
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER orders_reject_snapshot_mutation_trigger ON orders")
    op.execute("DROP FUNCTION orders_reject_snapshot_mutation")
    op.drop_table("notification_deliveries")
    op.drop_table("referral_rewards")
    op.drop_table("gift_vouchers")
    op.drop_table("promo_reservations")
    op.drop_table("payment_attempts")
    op.drop_table("orders")
    for enum_type in (PAYMENT_STATUS, PAYMENT_PROVIDER, ORDER_STATUS, ORDER_PURPOSE):
        enum_type.drop(op.get_bind(), checkfirst=True)
