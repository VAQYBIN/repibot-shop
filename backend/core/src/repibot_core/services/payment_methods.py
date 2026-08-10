"""Действующая карта пользователя.

Карту сохраняет плательщик галочкой на форме провайдера, поэтому здесь нет
ни одного решения «сохранить»: сервис лишь записывает то, что провайдер уже
подтвердил, и гасит прежнюю строку.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from typing import Protocol

from sqlalchemy import Select, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from repibot_core.db.models import (
    CardBinding,
    CardBindingStatus,
    PaymentProvider,
    SavedPaymentMethod,
    Subscription,
)
from repibot_core.integrations.yookassa.types import YooKassaBindingStatus, YooKassaCardBinding
from repibot_core.services.errors import ServiceError
from repibot_core.settings import Settings, get_settings


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


@dataclass(frozen=True, slots=True)
class StartedBinding:
    """Наша строка привязки и адрес, куда отправить пользователя подтверждать карту."""

    binding_id: int
    confirmation_url: str | None


class CardBindingCreator(Protocol):
    async def create_card_binding(
        self, *, idempotence_key: str, return_url: str
    ) -> YooKassaCardBinding: ...


class CardBindingReader(Protocol):
    async def get_card_binding(self, binding_id: str) -> YooKassaCardBinding: ...


class CardBindingService:
    """Привязка карты без списания.

    Сеть здесь всегда идёт между транзакциями: удерживать строку на время
    запроса к провайдеру значит держать блокировку столько, сколько он молчит.
    """

    def __init__(self, session: AsyncSession, settings: Settings | None = None) -> None:
        self._session = session
        self._settings = settings or get_settings()

    async def start(self, user_id: int, provider: CardBindingCreator) -> StartedBinding:
        """Заводит привязку и просит у провайдера адрес подтверждения."""
        if not self._settings.yookassa_zero_amount_binding:
            # Магазину без подключённой привязки провайдер ответил бы своей
            # ошибкой на чужом языке; отказ должен быть нашим и стабильным.
            raise ServiceError("привязка карты недоступна", "binding_unavailable")
        if self._session.in_transaction():
            await self._session.commit()

        binding = CardBinding(user_id=user_id, provider=PaymentProvider.yookassa)
        async with self._session.begin():
            self._session.add(binding)
        binding_id = binding.id

        # Строка коммитится до обращения к провайдеру: иначе потерянный ответ
        # оставил бы у него привязку, о которой у нас нет ни следа, ни ключа
        # идемпотентности, чтобы повтор попал в неё же.
        created = await provider.create_card_binding(
            idempotence_key=self._idempotence_key(binding_id),
            return_url=self._settings.public_app_url,
        )
        async with self._session.begin():
            await self._session.execute(
                update(CardBinding)
                .where(CardBinding.id == binding_id)
                .values(provider_binding_id=created.id)
            )
        return StartedBinding(binding_id=binding_id, confirmation_url=created.confirmation_url)

    async def settle(self, binding_id: int, provider: CardBindingReader) -> bool:
        """Дочитывает исход у провайдера; True — карта сохранена этим вызовом.

        Возврат пользователя и тело webhook ничего не доказывают: карта
        появляется только из прочитанного у провайдера ``active`` и ``saved``.
        """
        if self._session.in_transaction():
            await self._session.commit()
        row = (
            await self._session.execute(
                select(CardBinding.status, CardBinding.provider_binding_id).where(
                    CardBinding.id == binding_id
                )
            )
        ).one_or_none()
        # Читающая транзакция закрывается до обращения к провайдеру: держать её
        # открытой значит занимать соединение всё время, пока он молчит.
        await self._session.commit()
        if row is None or row.status is not CardBindingStatus.pending:
            return False
        if row.provider_binding_id is None:
            # Ответ на создание привязки потерян: у провайдера её опознать
            # нечем, и добор такой строке не поможет.
            return False

        state = await provider.get_card_binding(row.provider_binding_id)
        if state.status is YooKassaBindingStatus.pending:
            return False

        async with self._session.begin():
            binding = await self._session.scalar(
                select(CardBinding)
                .where(CardBinding.id == binding_id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
            # Пока шёл запрос, ту же привязку мог закрыть webhook или добор.
            if binding is None or binding.status is not CardBindingStatus.pending:
                return False
            binding.settled_at = datetime.now(UTC)
            if state.status is not YooKassaBindingStatus.active or not state.saved:
                binding.status = CardBindingStatus.failed
                return False
            binding.status = CardBindingStatus.active
            await PaymentMethodService(self._session).save(
                binding.user_id,
                provider_method_id=state.id,
                title=state.title,
                provider=binding.provider,
            )
        return True

    async def settle_pending(self, provider: CardBindingReader) -> int:
        """Добирает незавершённые привязки и возвращает число сохранённых карт.

        Подтверждение теряется так же, как и оплата: пользователь закрывает
        вкладку, webhook не доходит, и без добора карта не появилась бы никогда.
        """
        if self._session.in_transaction():
            await self._session.commit()
        pending = list(
            (
                await self._session.scalars(
                    select(CardBinding.id).where(
                        CardBinding.status == CardBindingStatus.pending,
                        CardBinding.provider_binding_id.is_not(None),
                    )
                )
            ).all()
        )
        settled = 0
        for pending_id in pending:
            if await self.settle(pending_id, provider):
                settled += 1
        return settled

    @staticmethod
    def _idempotence_key(binding_id: int) -> str:
        """Устойчивый ключ от нашей строки: повтор попадёт в ту же привязку."""
        return sha256(f"card-binding:{binding_id}".encode()).hexdigest()
