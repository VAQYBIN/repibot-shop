"""Защищает весь неизменяемый коммерческий замысел заказа.

Revision ID: 0011
Revises: 0010
"""

from __future__ import annotations

from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE OR REPLACE FUNCTION orders_reject_snapshot_mutation() RETURNS trigger AS $$
        BEGIN
            IF (NEW.user_id, NEW.purpose, NEW.plan_id, NEW.plan_code_snapshot,
                NEW.plan_name_snapshot, NEW.duration_days_snapshot,
                NEW.price_rub_snapshot, NEW.price_stars_snapshot, NEW.gross_rub,
                NEW.discount_rub, NEW.amount_due_rub, NEW.promo_code_id,
                NEW.client_key, NEW.expires_at)
               IS DISTINCT FROM
               (OLD.user_id, OLD.purpose, OLD.plan_id, OLD.plan_code_snapshot,
                OLD.plan_name_snapshot, OLD.duration_days_snapshot,
                OLD.price_rub_snapshot, OLD.price_stars_snapshot, OLD.gross_rub,
                OLD.discount_rub, OLD.amount_due_rub, OLD.promo_code_id,
                OLD.client_key, OLD.expires_at) THEN
                RAISE EXCEPTION 'order commercial snapshot is immutable';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        CREATE OR REPLACE FUNCTION orders_reject_snapshot_mutation() RETURNS trigger AS $$
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
