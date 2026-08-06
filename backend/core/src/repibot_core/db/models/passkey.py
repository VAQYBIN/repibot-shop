"""Passkey: публичный ключ аутентификатора и счётчик его подписей."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, LargeBinary, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from repibot_core.db.base import Base, TimestampMixin


class PasskeyCredential(TimestampMixin, Base):
    __tablename__ = "passkey_credentials"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)

    # Идентификатор и ключ хранятся байтами: библиотека отдаёт и принимает их
    # в таком виде, а перекодировка в base64url туда-обратно на каждом входе —
    # лишний способ ошибиться в дополнении «=».
    credential_id: Mapped[bytes] = mapped_column(LargeBinary, unique=True)
    public_key: Mapped[bytes] = mapped_column(LargeBinary)

    # Счётчик подписей аутентификатора. Многие passkey держат его нулевым, и
    # это допустимо: правило «новый больше сохранённого» проверяется только
    # тогда, когда счётчик вообще используется.
    sign_count: Mapped[int] = mapped_column(Integer, default=0)

    transports: Mapped[list[str] | None] = mapped_column(JSONB)
    name: Mapped[str] = mapped_column(String(64))
    # Тот же тип, что у остальных отметок времени: без timezone Postgres хранит
    # момент без смещения, и сравнение с aware-datetime из кода падает.
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
