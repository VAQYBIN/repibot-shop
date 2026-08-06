"""Доступ к тарифам."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from repibot_core.db.models import Plan


class PlanRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, plan_id: int) -> Plan | None:
        return await self._session.get(Plan, plan_id)

    async def get_by_code(self, code: str) -> Plan | None:
        statement = select(Plan).where(Plan.code == code)
        return (await self._session.execute(statement)).scalar_one_or_none()

    async def list_all(self) -> list[Plan]:
        statement = select(Plan).order_by(Plan.sort_order, Plan.id)
        return list((await self._session.execute(statement)).scalars())

    async def list_visible(self) -> list[Plan]:
        """Тарифы для витрины: снятые с продажи и скрытые не показываются."""
        statement = (
            select(Plan)
            .where(Plan.is_active.is_(True), Plan.is_visible.is_(True))
            .order_by(Plan.sort_order, Plan.id)
        )
        return list((await self._session.execute(statement)).scalars())

    async def active_trial(self) -> Plan | None:
        """Единственный активный триальный тариф.

        `scalar_one_or_none` намеренно: частичный уникальный индекс
        `uq_plans_single_active_trial` не даёт появиться второму такому тарифу,
        и падение здесь означало бы расхождение схемы с ожиданием кода.
        """
        statement = select(Plan).where(Plan.is_trial.is_(True), Plan.is_active.is_(True))
        return (await self._session.execute(statement)).scalar_one_or_none()

    async def create(self, **fields: Any) -> Plan:
        plan = Plan(**fields)
        self._session.add(plan)
        await self._session.flush()
        return plan

    async def archive(self, plan: Plan) -> None:
        """Снимает тариф с продажи, не удаляя строку.

        Физическое удаление порвало бы ссылки из подписок и журнала
        начислений, а в подпроекте 3 — ещё и из платежей.
        """
        plan.is_active = False
        await self._session.flush()
