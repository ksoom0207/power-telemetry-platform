from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.encryption import decrypt_secret
from app.core.errors import ExternalApiError
from app.integrations.ilo.client import IloClient, IloPowerReading
from app.integrations.ilo.profiles import supported_profiles
from app.repositories import devices as device_repo
from app.repositories import ilo as ilo_repo
from app.repositories import settings as settings_repo

IloClientFactory = Callable[..., IloClient]


def _now_utc() -> datetime:
    return datetime.now(tz=UTC)


def _with_timestamps(values: dict[str, object], *, create: bool) -> dict[str, object]:
    now = _now_utc()
    values["updated_at"] = now
    if create:
        values["created_at"] = now
    return values


def _final_status(total_targets: int, success_count: int, failed_count: int) -> str:
    if total_targets == 0:
        return "skipped"
    if success_count == total_targets:
        return "success"
    if failed_count == total_targets:
        return "failed"
    return "partial_success"


async def get_ilo_status(session: AsyncSession) -> dict[str, object]:
    credential = await settings_repo.get_ilo_credential(session)
    targets = await device_repo.list_ilo_collection_targets(session)
    return {
        "credential_configured": bool(credential and credential.get("encrypted_password")),
        "supported_profiles": supported_profiles(),
        "target_count": len(targets),
    }


async def collect_ilo_power(
    session: AsyncSession,
    *,
    client_factory: IloClientFactory = IloClient,
    triggered_by: str = "api",
) -> dict[str, object]:
    targets = [
        target
        for target in await device_repo.list_ilo_collection_targets(session)
        if _has_ilo_target_fields(target)
    ]
    started_at = _now_utc()
    run = await ilo_repo.create_collection_run(
        session,
        _with_timestamps(
            {
                "started_at": started_at,
                "finished_at": None,
                "status": "running",
                "triggered_by": triggered_by,
                "total_targets": len(targets),
                "success_count": 0,
                "failed_count": 0,
            },
            create=True,
        ),
    )

    credential = await settings_repo.get_ilo_credential(session) if targets else None
    success_count = 0
    failed_count = 0

    for target in targets:
        try:
            if credential is None:
                raise ExternalApiError("iLO credential is not configured")
            password = decrypt_secret(str(credential["encrypted_password"]))
            reading = await _read_target_power(
                target,
                credential=credential,
                password=password,
                client_factory=client_factory,
            )
        except Exception:
            await _persist_failed_sample(session, run_id=int(run["id"]), target=target)
            failed_count += 1
            continue

        await _persist_success_sample(
            session,
            run_id=int(run["id"]),
            target=target,
            reading=reading,
        )
        success_count += 1

    finished_at = _now_utc()
    final_run = await ilo_repo.update_collection_run(
        session,
        int(run["id"]),
        _with_timestamps(
            {
                "finished_at": finished_at,
                "status": _final_status(len(targets), success_count, failed_count),
                "success_count": success_count,
                "failed_count": failed_count,
            },
            create=False,
        ),
    )
    await session.commit()
    return final_run


def _has_ilo_target_fields(target: dict[str, Any]) -> bool:
    host = target.get("ilo_host")
    profile = target.get("ilo_profile")
    return (
        isinstance(host, str)
        and bool(host.strip())
        and isinstance(profile, str)
        and bool(profile.strip())
    )


async def _read_target_power(
    target: dict[str, Any],
    *,
    credential: dict[str, Any],
    password: str,
    client_factory: IloClientFactory,
) -> IloPowerReading:
    client = client_factory(
        host=str(target["ilo_host"]),
        username=str(credential["username"]),
        password=password,
        profile=str(target["ilo_profile"]),
        tls_verify=bool(credential.get("tls_verify", False)),
        timeout_seconds=int(credential.get("timeout_seconds", 10)),
    )
    return await client.read_power()


async def _persist_success_sample(
    session: AsyncSession,
    *,
    run_id: int,
    target: dict[str, Any],
    reading: IloPowerReading,
) -> None:
    measured_at = _now_utc()
    await ilo_repo.create_power_sample(
        session,
        _with_timestamps(
            {
                "device_id": target["id"],
                "collection_run_id": run_id,
                "measured_at": measured_at,
                "average_watts": reading.average_watts,
                "status": "success",
                "quality": "collected_ilo",
                "auth_method_used": reading.auth_method_used,
                "profile_used": reading.profile_used,
            },
            create=True,
        ),
    )


async def _persist_failed_sample(
    session: AsyncSession,
    *,
    run_id: int,
    target: dict[str, Any],
) -> None:
    measured_at = _now_utc()
    await ilo_repo.create_power_sample(
        session,
        _with_timestamps(
            {
                "device_id": target["id"],
                "collection_run_id": run_id,
                "measured_at": measured_at,
                "average_watts": None,
                "status": "failed",
                "quality": "collection_failed",
                "auth_method_used": None,
                "profile_used": target.get("ilo_profile"),
            },
            create=True,
        ),
    )


async def list_ilo_samples(session: AsyncSession, *, limit: int = 100) -> list[dict[str, object]]:
    return await ilo_repo.list_power_samples(session, limit=limit)


async def list_collection_runs(
    session: AsyncSession,
    *,
    limit: int = 100,
) -> list[dict[str, object]]:
    return await ilo_repo.list_collection_runs(session, limit=limit)


async def get_collection_run(session: AsyncSession, collection_run_id: int) -> dict[str, object]:
    run = await ilo_repo.get_collection_run(session, collection_run_id)
    samples = await ilo_repo.list_power_samples(
        session,
        limit=1000,
        collection_run_id=collection_run_id,
    )
    return {**run, "samples": samples}
