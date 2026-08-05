# Сгенерировано tools/gen_remnawave_models.py. Не редактировать вручную.

from __future__ import annotations

from enum import StrEnum
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, EmailStr, Field


class Status(StrEnum):
    ACTIVE = 'ACTIVE'
    DISABLED = 'DISABLED'
    LIMITED = 'LIMITED'
    EXPIRED = 'EXPIRED'


class TrafficLimitStrategy(StrEnum):
    NO_RESET = 'NO_RESET'
    DAY = 'DAY'
    WEEK = 'WEEK'
    MONTH = 'MONTH'
    MONTH_ROLLING = 'MONTH_ROLLING'


class ActiveInternalSquad(BaseModel):
    uuid: UUID
    name: str


class UserTraffic(BaseModel):
    usedTrafficBytes: float
    lifetimeUsedTrafficBytes: float
    onlineAt: AwareDatetime
    firstConnectedAt: AwareDatetime
    lastConnectedNodeUuid: UUID


class Response(BaseModel):
    uuid: UUID
    id: float
    shortUuid: str
    username: str
    status: Status | None = 'ACTIVE'
    trafficLimitBytes: float | None = 0
    trafficLimitStrategy: TrafficLimitStrategy | None = Field(
        'NO_RESET', description='Available reset periods'
    )
    expireAt: AwareDatetime
    telegramId: int
    email: EmailStr
    description: str
    tag: str
    hwidDeviceLimit: int
    externalSquadUuid: UUID
    trojanPassword: str
    vlessUuid: UUID
    ssPassword: str
    lastTriggeredThreshold: int | None = 0
    subRevokedAt: AwareDatetime
    lastTrafficResetAt: AwareDatetime
    createdAt: AwareDatetime
    updatedAt: AwareDatetime
    subscriptionUrl: str
    activeInternalSquads: list[ActiveInternalSquad]
    userTraffic: UserTraffic


class GetUserByUuidResponseDto(BaseModel):
    response: Response
