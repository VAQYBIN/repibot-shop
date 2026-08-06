# Сгенерировано tools/gen_remnawave_models.py. Не редактировать вручную.

from __future__ import annotations

from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, EmailStr, Field, confloat, conint, constr


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


class CreateUserBodyDto(BaseModel):
    username: constr(pattern=r'^[a-zA-Z0-9_-]+$', min_length=3, max_length=36) = Field(
        ...,
        description='Unique username for the user. Required. Must be 3-36 characters long and contain only letters, numbers, underscores and dashes.',
    )
    status: Status = Field(
        'ACTIVE', description='Optional. User account status. Defaults to ACTIVE.'
    )
    shortUuid: str | None = Field(
        None, description='Optional. Short UUID identifier for the user.'
    )
    trojanPassword: constr(min_length=8, max_length=32) | None = Field(
        None,
        description='Optional. Password for Trojan protocol. Must be 8-32 characters.',
    )
    vlessUuid: UUID | None = Field(
        None,
        description='Optional. UUID for VLESS protocol. Must be a valid UUID format.',
    )
    ssPassword: constr(min_length=8, max_length=32) | None = Field(
        None,
        description='Optional. Password for Shadowsocks protocol. Must be 8-32 characters.',
    )
    trafficLimitBytes: confloat(ge=0.0) | None = Field(
        None,
        description='Optional. Traffic limit in bytes. Set to 0 for unlimited traffic.',
    )
    trafficLimitStrategy: TrafficLimitStrategy = Field(
        'NO_RESET', description='Available reset periods'
    )
    expireAt: AwareDatetime = Field(
        ...,
        description='Account expiration date. Required. Format: 2025-01-17T15:38:45.065Z',
    )
    createdAt: AwareDatetime | None = Field(
        None,
        description='Optional. Account creation date. Format: 2025-01-17T15:38:45.065Z',
    )
    lastTrafficResetAt: AwareDatetime | None = Field(
        None,
        description='Optional. Date of last traffic reset. Format: 2025-01-17T15:38:45.065Z',
    )
    description: str | None = Field(
        None,
        description='Optional. Additional notes or description for the user account.',
    )
    tag: constr(pattern=r'^[A-Z0-9_]+$', max_length=16) | None = Field(
        None,
        description='Optional. User tag for categorization. Max 16 characters, uppercase letters, numbers and underscores only.',
    )
    telegramId: float | None = Field(
        None,
        description='Optional. Telegram user ID for notifications. Must be an integer.',
    )
    email: EmailStr | None = Field(
        None, description='Optional. User email address. Must be a valid email format.'
    )
    hwidDeviceLimit: conint(ge=0, le=9007199254740991) | None = Field(
        None,
        description='Optional. Maximum number of hardware devices allowed. Must be a positive integer.',
    )
    activeInternalSquads: list[UUID] | None = Field(
        None,
        description='Optional. Array of UUIDs representing enabled internal squads.',
    )
    externalSquadUuid: UUID | None = Field(
        None, description='Optional. External squad UUID.'
    )


class DeleteUserHwidDeviceBodyDto(BaseModel):
    userId: float
    hwid: str


class Info(BaseModel):
    membersCount: float
    inboundsCount: float


class Inbound(BaseModel):
    uuid: UUID
    profileUuid: UUID
    tag: str
    type: str
    network: str | None = Field(...)
    security: str | None = Field(...)
    port: float | None = Field(...)
    rawInbound: Any | None = Field(...)


class InternalSquad(BaseModel):
    uuid: UUID
    viewPosition: conint(ge=-9007199254740991, le=9007199254740991)
    name: str
    info: Info
    inbounds: list[Inbound]
    createdAt: AwareDatetime
    updatedAt: AwareDatetime


class Response(BaseModel):
    total: float
    internalSquads: list[InternalSquad]


class GetInternalSquadsResponseDto(BaseModel):
    response: Response


class TopNode(BaseModel):
    uuid: UUID
    color: str
    name: str
    countryCode: str
    total: float


class Series(BaseModel):
    uuid: UUID
    name: str
    color: str
    countryCode: str
    total: float
    data: list[float]


class Response1(BaseModel):
    categories: list[str]
    sparklineData: list[float]
    topNodes: list[TopNode]
    series: list[Series]


class GetStatsUserUsageResponseDto(BaseModel):
    response: Response1


class Device(BaseModel):
    hwid: str
    userId: float
    platform: str | None = Field(...)
    osVersion: str | None = Field(...)
    deviceModel: str | None = Field(...)
    userAgent: str | None = Field(...)
    requestIp: str | None = Field(...)
    createdAt: AwareDatetime
    updatedAt: AwareDatetime


class Response2(BaseModel):
    total: float
    devices: list[Device]


class GetUserHwidDevicesResponseDto(BaseModel):
    response: Response2


class ResolveUserBodyDto(BaseModel):
    id: float | None = None
    shortUuid: str | None = None
    username: str | None = None


class Status1(StrEnum):
    ACTIVE = 'ACTIVE'
    DISABLED = 'DISABLED'


class UpdateUserBodyDto(BaseModel):
    username: str | None = Field(None, description='Username of the user')
    id: float | None = Field(None, description='ID of the user')
    status: Status1 | None = None
    trafficLimitBytes: confloat(ge=0.0) | None = Field(
        None, description='Traffic limit in bytes. 0 - unlimited'
    )
    trafficLimitStrategy: TrafficLimitStrategy | None = Field(
        'NO_RESET', description='Traffic limit reset strategy'
    )
    expireAt: AwareDatetime | None = Field(
        None, description='Expiration date: 2025-01-17T15:38:45.065Z'
    )
    description: str | None = None
    tag: constr(pattern=r'^[A-Z0-9_]+$', max_length=16) | None = None
    telegramId: float | None = None
    email: EmailStr | None = None
    hwidDeviceLimit: conint(ge=0, le=9007199254740991) | None = None
    activeInternalSquads: list[UUID] | None = None
    externalSquadUuid: UUID | None = Field(
        None, description='Optional. External squad UUID.'
    )


class Status2(StrEnum):
    ACTIVE = 'ACTIVE'
    DISABLED = 'DISABLED'
    LIMITED = 'LIMITED'
    EXPIRED = 'EXPIRED'


class ActiveInternalSquad(BaseModel):
    uuid: UUID
    name: str


class UserTraffic(BaseModel):
    usedTrafficBytes: float
    lifetimeUsedTrafficBytes: float
    onlineAt: AwareDatetime | None = Field(...)
    firstConnectedAt: AwareDatetime | None = Field(...)
    lastConnectedNodeUuid: UUID | None = Field(...)


class Response3(BaseModel):
    id: float
    shortUuid: str
    username: str
    status: Status2
    trafficLimitBytes: float
    trafficLimitStrategy: TrafficLimitStrategy = Field(
        ..., description='Available reset periods'
    )
    expireAt: AwareDatetime
    telegramId: float | None = Field(...)
    email: EmailStr | None = Field(...)
    description: str | None = Field(...)
    tag: str | None = Field(...)
    hwidDeviceLimit: conint(ge=-9007199254740991, le=9007199254740991) | None = Field(
        ...
    )
    externalSquadUuid: UUID | None = Field(...)
    trojanPassword: str
    vlessUuid: UUID
    ssPassword: str
    lastTriggeredThreshold: conint(ge=-9007199254740991, le=9007199254740991)
    subRevokedAt: AwareDatetime | None = Field(...)
    lastTrafficResetAt: AwareDatetime | None = Field(...)
    createdAt: AwareDatetime
    updatedAt: AwareDatetime
    subscriptionUrl: str
    activeInternalSquads: list[ActiveInternalSquad]
    userTraffic: UserTraffic


class UserResponseDto(BaseModel):
    response: Response3
