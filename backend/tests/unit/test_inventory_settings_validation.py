from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.core.encryption import decrypt_secret, encrypt_secret
from app.core.errors import ValidationAppError
from app.schemas.devices import DeviceCreate
from app.schemas.racks import RackCreate
from app.schemas.settings import IloCredentialRead, IloCredentialUpsert
from app.services import settings as settings_service


def test_rack_create_requires_valid_phase() -> None:
    with pytest.raises(ValidationError):
        RackCreate(name="Rack 01", phase="X", voltage=Decimal("220"))


def test_device_create_requires_valid_u_range() -> None:
    with pytest.raises(ValidationError):
        DeviceCreate(
            name="Switch 01",
            rack_id=1,
            device_type="network",
            u_position_start=20,
            u_position_end=10,
        )


def test_device_create_requires_ilo_fields_when_has_ilo() -> None:
    with pytest.raises(ValidationError):
        DeviceCreate(
            name="Server 01",
            rack_id=1,
            device_type="server",
            has_ilo=True,
        )


def test_encrypt_secret_round_trip() -> None:
    encrypted = encrypt_secret("secret-password")

    assert encrypted != "secret-password"
    assert decrypt_secret(encrypted) == "secret-password"


def test_ilo_credential_read_does_not_expose_password() -> None:
    payload = IloCredentialRead(
        id=1,
        username="Administrator",
        auth_mode="session_with_basic_fallback",
        tls_verify=False,
        timeout_seconds=10,
        password_configured=True,
    )

    assert "password" not in payload.model_dump()


@pytest.mark.asyncio
async def test_upsert_ilo_credential_requires_password_on_first_create(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_get_ilo_credential(_session: object) -> None:
        return None

    monkeypatch.setattr(
        settings_service.settings_repo,
        "get_ilo_credential",
        fake_get_ilo_credential,
    )

    with pytest.raises(ValidationAppError, match="password is required"):
        await settings_service.upsert_ilo_credential(
            object(),
            IloCredentialUpsert(username="Administrator", password=None),
        )
