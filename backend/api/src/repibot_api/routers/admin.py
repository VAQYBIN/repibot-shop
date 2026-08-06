"""Административные маршруты.

Пока здесь только проверка гейта: страницы админки появятся в подпроекте 5.
Гейт написан и покрыт тестом сразу, чтобы к моменту появления страниц не
пришлось решать вопрос доступа задним числом.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from repibot_api.deps import AuthContext, require_role
from repibot_core.db.models import UserRole

router = APIRouter(prefix="/api/admin", tags=["admin"])


class WhoAmIResponse(BaseModel):
    id: int
    role: str


@router.get("/whoami", response_model=WhoAmIResponse)
async def whoami(
    context: Annotated[AuthContext, Depends(require_role(UserRole.admin, UserRole.support))],
) -> WhoAmIResponse:
    return WhoAmIResponse(id=context.principal.user_id, role=context.principal.role.value)
