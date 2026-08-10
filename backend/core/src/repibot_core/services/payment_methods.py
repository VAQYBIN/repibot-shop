"""Действующая карта пользователя.

Карту сохраняет плательщик галочкой на форме провайдера, поэтому здесь нет
ни одного решения «сохранить»: сервис лишь записывает то, что провайдер уже
подтвердил, и гасит прежнюю строку.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import Select, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from repibot_core.db.models import PaymentProvider, SavedPaymentMethod, Subscription


@dataclass(frozen=True, slots=True)
class SavedCardView:
    title: str | None
    linked_at: datetime


class PaymentMethodService:
    """Меняет строки без commit и без сетевых вызовов."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def current(self, user_id: int) -> SavedCardView | None:
        row = await self._session.scalar(self._active(user_id))
        if row is None:
            return None
        return SavedCardView(title=row.title, linked_at=row.created_at)

    async def current_method_id(self, user_id: int) -> str | None:
        """Идентификатор для повторного списания или None, если карты нет."""
        row = await self._session.scalar(self._active(user_id))
        return None if row is None else row.provider_method_id

    async def save(
        self,
        user_id: int,
        *,
        provider_method_id: str,
        title: str | None,
        provider: PaymentProvider = PaymentProvider.yookassa,
    ) -> SavedPaymentMethod:
        """Заменяет действующую карту и включает автоплатёж.

        Согласие на повторные списания пользователь уже дал галочкой, так что
        отдельного переключателя для этого не нужно: иначе первый цикл
        автопродления не наступил бы никогда.
        """
        await self._session.execute(
            update(SavedPaymentMethod)
            .where(
                SavedPaymentMethod.user_id == user_id,
                SavedPaymentMethod.revoked_at.is_(None),
            )
            .values(revoked_at=datetime.now(UTC))
        )
        saved = SavedPaymentMethod(
            user_id=user_id,
            provider=provider,
            provider_method_id=provider_method_id,
            title=title,
        )
        self._session.add(saved)
        await self._set_auto_renew(user_id, enabled=True)
        await self._session.flush()
        return saved

    async def revoke(self, user_id: int) -> bool:
        """Гасит карту и выключает автоплатёж: списывать станет нечем."""
        result = await self._session.execute(
            update(SavedPaymentMethod)
            .where(
                SavedPaymentMethod.user_id == user_id,
                SavedPaymentMethod.revoked_at.is_(None),
            )
            .values(revoked_at=datetime.now(UTC))
            .returning(SavedPaymentMethod.id)
        )
        if not result.scalars().all():
            return False
        await self._set_auto_renew(user_id, enabled=False)
        return True

    async def _set_auto_renew(self, user_id: int, *, enabled: bool) -> None:
        await self._session.execute(
            update(Subscription)
            .where(Subscription.user_id == user_id)
            .values(auto_renew_enabled=enabled)
        )

    @staticmethod
    def _active(user_id: int) -> Select[tuple[SavedPaymentMethod]]:
        return select(SavedPaymentMethod).where(
            SavedPaymentMethod.user_id == user_id,
            SavedPaymentMethod.revoked_at.is_(None),
        )
