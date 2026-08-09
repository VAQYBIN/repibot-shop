"""Тарифы: витрина и управление."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from repibot_core.db.models import Plan, TrafficResetStrategy
from repibot_core.db.repositories.plans import PlanRepository
from repibot_core.integrations.remnawave.squads import PanelSquads
from repibot_core.services.errors import ServiceError


@dataclass(frozen=True, slots=True)
class PlanInput:
    code: str
    name: dict[str, str]
    description: dict[str, str] | None
    duration_days: int
    price_rub: Decimal
    price_stars: int
    traffic_limit_bytes: int
    traffic_reset_strategy: TrafficResetStrategy
    hwid_device_limit: int
    internal_squad_uuids: list[str]
    is_trial: bool
    is_visible: bool
    sort_order: int


@dataclass(frozen=True, slots=True)
class PlanView:
    id: int
    code: str
    name: dict[str, str]
    description: dict[str, str] | None
    duration_days: int
    price_rub: Decimal
    price_stars: int
    traffic_limit_bytes: int
    traffic_reset_strategy: TrafficResetStrategy
    hwid_device_limit: int
    internal_squad_uuids: list[str]
    is_trial: bool
    is_active: bool
    is_visible: bool
    sort_order: int


class PlanService:
    def __init__(self, session: AsyncSession, squads: PanelSquads) -> None:
        self._session = session
        self._plans = PlanRepository(session)
        self._squads = squads

    async def visible(self) -> list[PlanView]:
        return [_view(plan) for plan in await self._plans.list_visible()]

    async def all(self) -> list[PlanView]:
        return [_view(plan) for plan in await self._plans.list_all()]

    async def require(self, plan_id: int) -> Plan:
        plan = await self._plans.get(plan_id)
        if plan is None:
            msg = "тариф не найден"
            raise ServiceError(msg, "plan_not_found")
        return plan

    async def create(self, data: PlanInput) -> PlanView:
        await self._check_squads(data.internal_squad_uuids)
        if await self._plans.get_by_code(data.code) is not None:
            msg = "тариф с таким кодом уже есть"
            raise ServiceError(msg, "plan_code_taken")

        # asdict, а не vars: dataclass со slots не имеет __dict__, и vars
        # на нём падает с TypeError.
        plan = await self._plans.create(is_active=True, **asdict(data))
        await self._session.commit()
        return _view(plan)

    async def update(self, plan_id: int, data: PlanInput) -> PlanView:
        plan = await self.require(plan_id)
        await self._check_squads(data.internal_squad_uuids)

        existing = await self._plans.get_by_code(data.code)
        if existing is not None and existing.id != plan.id:
            msg = "тариф с таким кодом уже есть"
            raise ServiceError(msg, "plan_code_taken")

        for field, value in asdict(data).items():
            setattr(plan, field, value)
        await self._session.commit()
        return _view(plan)

    async def archive(self, plan_id: int) -> None:
        plan = await self.require(plan_id)
        await self._plans.archive(plan)
        await self._session.commit()

    async def _check_squads(self, uuids: list[str]) -> None:
        """Сквады тарифа обязаны существовать в панели.

        Тариф с несуществующим сквадом продаётся, оплачивается и не даёт
        доступа: панель молча примет пустой набор. Ошибка здесь дешевле
        разбирательства с клиентом потом.
        """
        if not uuids:
            msg = "у тарифа должен быть хотя бы один сквад"
            raise ServiceError(msg, "plan_squads_unknown")

        known = {str(squad.uuid) for squad in await self._squads.list()}
        unknown = [uuid for uuid in uuids if uuid not in known]
        if unknown:
            msg = f"панель не знает сквадов: {', '.join(unknown)}"
            raise ServiceError(msg, "plan_squads_unknown")


def _view(plan: Plan) -> PlanView:
    return PlanView(
        id=plan.id,
        code=plan.code,
        name=plan.name,
        description=plan.description,
        duration_days=plan.duration_days,
        price_rub=plan.price_rub,
        price_stars=plan.price_stars,
        traffic_limit_bytes=plan.traffic_limit_bytes,
        traffic_reset_strategy=plan.traffic_reset_strategy,
        hwid_device_limit=plan.hwid_device_limit,
        internal_squad_uuids=list(plan.internal_squad_uuids),
        is_trial=plan.is_trial,
        is_active=plan.is_active,
        is_visible=plan.is_visible,
        sort_order=plan.sort_order,
    )
