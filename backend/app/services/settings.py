from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings as app_settings
from app.core.encryption import encrypt_secret
from app.core.errors import ValidationAppError
from app.repositories import settings as settings_repo
from app.schemas.settings import IloCredentialRead, IloCredentialUpsert, PowerDefaultsUpsert


def _now_utc() -> datetime:
    return datetime.now(tz=UTC)


def _with_timestamps(values: dict[str, object], *, create: bool) -> dict[str, object]:
    now = _now_utc()
    values["updated_at"] = now
    if create:
        values["created_at"] = now
    return values


def _credential_read(row: dict[str, object] | None) -> dict[str, object]:
    if row is None:
        return IloCredentialRead(password_configured=False).model_dump()
    return IloCredentialRead(
        id=row["id"],
        username=row["username"],
        auth_mode=row["auth_mode"],
        tls_verify=row["tls_verify"],
        timeout_seconds=row["timeout_seconds"],
        password_configured=bool(row.get("encrypted_password")),
    ).model_dump()


async def get_ilo_credential(session: AsyncSession) -> dict[str, object]:
    row = await settings_repo.get_ilo_credential(session)
    return _credential_read(row)


async def upsert_ilo_credential(
    session: AsyncSession,
    payload: IloCredentialUpsert,
) -> dict[str, object]:
    current = await settings_repo.get_ilo_credential(session)
    values = payload.model_dump(exclude={"password"})
    if payload.password is not None:
        values["encrypted_password"] = encrypt_secret(payload.password)
    elif current is not None:
        values["encrypted_password"] = current["encrypted_password"]
    else:
        raise ValidationAppError("password is required when creating iLO credential")
    row = await settings_repo.upsert_ilo_credential(
        session,
        _with_timestamps(values, create=current is None),
    )
    await session.commit()
    return _credential_read(row)


async def get_power_defaults(session: AsyncSession) -> dict[str, object]:
    row = await settings_repo.get_power_defaults(session)
    if row is not None:
        return row
    return {
        "id": None,
        "default_voltage": app_settings.default_voltage,
        "default_power_factor": app_settings.default_power_factor,
        "carry_forward_max_hours": app_settings.carry_forward_max_hours,
    }


async def upsert_power_defaults(
    session: AsyncSession,
    payload: PowerDefaultsUpsert,
) -> dict[str, object]:
    current = await settings_repo.get_power_defaults(session)
    row = await settings_repo.upsert_power_defaults(
        session,
        _with_timestamps(payload.model_dump(), create=current is None),
    )
    await session.commit()
    return row


def default_power_settings_payload() -> PowerDefaultsUpsert:
    return PowerDefaultsUpsert(
        default_voltage=Decimal(app_settings.default_voltage),
        default_power_factor=Decimal(app_settings.default_power_factor),
        carry_forward_max_hours=app_settings.carry_forward_max_hours,
    )
