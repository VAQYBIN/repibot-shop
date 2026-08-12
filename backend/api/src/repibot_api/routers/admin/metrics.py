"""Сводка админки: числа за период по нашей базе.

Схема ответа объявлена здесь, а не в общем `schemas.py`: предметы админки
наполняются одновременно, и общий файл стал бы местом их столкновения.
Прецедент — `WhoAmIResponse` в корне пакета.

Роли support здесь нет: сводка — это выручка, а поддержка разбирается с
обращениями. Гейт стоит на маршруте, а не на скрытой кнопке в интерфейсе.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from repibot_api.deps import AuthContext, db_session, require_role
from repibot_core.db.models import UserRole
from repibot_core.services.admin_metrics import MetricsPeriod, collect_metrics

# Без префикса: он стоит на общем роутере пакета.
router = APIRouter()


class AdminMetricsResponse(BaseModel):
    revenue_rub: str
    payments: int
    new_subscriptions: int
    renewals: int
    active_subscriptions: int
    tickets_waiting: int


# Период — перечисление, поэтому опечатка в нём даёт 422 от самого FastAPI, а не
# пустую сводку, неотличимую от неудачного дня. Значение по умолчанию совпадает
# с тем, что открыто на экране первым: сводка без параметра остаётся сводкой.
@router.get("/metrics", response_model=AdminMetricsResponse)
async def read_metrics(
    session: Annotated[AsyncSession, Depends(db_session)],
    _: Annotated[AuthContext, Depends(require_role(UserRole.admin))],
    period: MetricsPeriod = MetricsPeriod.today,
) -> AdminMetricsResponse:
    metrics = await collect_metrics(session, period)
    return AdminMetricsResponse(
        # Строкой, а не числом: JSON не различает 199.50 и ближайшее к нему
        # двоичное приближение, и копейки терялись бы по дороге в браузер.
        revenue_rub=str(metrics.revenue_rub),
        payments=metrics.payments,
        new_subscriptions=metrics.new_subscriptions,
        renewals=metrics.renewals,
        active_subscriptions=metrics.active_subscriptions,
        tickets_waiting=metrics.tickets_waiting,
    )
