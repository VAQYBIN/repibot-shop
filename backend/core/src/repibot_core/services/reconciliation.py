"""Сверка нашего состояния с панелью.

Молчаливое исправление недопустимо: расхождение обычно означает ручную правку
админа в панели, и о ней надо знать. Поэтому прогон приводит панель к нашему
состоянию и записывает всё найденное.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from repibot_core.db.models import FindingAction
from repibot_core.db.repositories.reconciliation import FindingRepository
from repibot_core.db.repositories.subscriptions import SubscriptionRepository
from repibot_core.integrations.remnawave.client import RemnawaveUnavailable
from repibot_core.services.provisioning import ProvisioningService

logger = logging.getLogger(__name__)


class ReconciliationService:
    """Записывает найденные при приведении панели расхождения."""

    def __init__(self, session: AsyncSession, provisioning: ProvisioningService) -> None:
        self._session = session
        self._provisioning = provisioning
        self._findings = FindingRepository(session)
        self._subscriptions = SubscriptionRepository(session)

    async def run(self, *, run_id: str, limit: int = 100) -> int:
        """Сверяет рабочие подписки страницами и возвращает число записей."""
        after_id = 0
        written = 0

        while subscriptions := await self._subscriptions.list_for_reconcile(
            limit=limit, after_id=after_id
        ):
            for subscription in subscriptions:
                try:
                    state = await self._provisioning.reconcile(subscription.user_id)
                except RemnawaveUnavailable:
                    logger.warning(
                        "панель недоступна во время сверки",
                        extra={"subscription_id": subscription.id, "user_id": subscription.user_id},
                    )
                    continue

                action = FindingAction.skipped if state.skipped else FindingAction.fixed
                for difference in state.differences:
                    await self._findings.add(
                        run_id=run_id,
                        user_id=subscription.user_id,
                        field=difference.field,
                        ours=difference.ours,
                        theirs=difference.theirs,
                        action=action,
                        now=datetime.now(UTC),
                    )
                    written += 1

            await self._session.commit()
            after_id = subscriptions[-1].id

        return written
