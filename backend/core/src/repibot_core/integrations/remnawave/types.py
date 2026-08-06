"""Устойчивые имена для сгенерированных моделей панели.

Генератор называет вложенные безымянные объекты по порядку — Response,
Response1, Status2. Порядок меняется от состава корневых схем, поэтому код
ссылается на псевдонимы отсюда, а не на номерные классы напрямую. Тест
test_remnawave_types проверяет, что псевдоним всё ещё указывает на нужный тип.
"""

from __future__ import annotations

from repibot_core.integrations.remnawave import models

PanelUser = models.Response1
PanelSquad = models.InternalSquad
PanelStatus = models.Status2
PanelTrafficStrategy = models.TrafficLimitStrategy

CreateUserBody = models.CreateUserBodyDto
UpdateUserBody = models.UpdateUserBodyDto
ResolveUserBody = models.ResolveUserBodyDto

__all__ = [
    "CreateUserBody",
    "PanelSquad",
    "PanelStatus",
    "PanelTrafficStrategy",
    "PanelUser",
    "ResolveUserBody",
    "UpdateUserBody",
]
