from dataclasses import dataclass, field
from datetime import UTC
from decimal import Decimal
from typing import Any

import pytest

from app.integrations.ilo.client import IloPowerReading
from app.services import ilo_collection


@dataclass
class FakeIloRepo:
    runs: list[dict[str, Any]] = field(default_factory=list)
    samples: list[dict[str, Any]] = field(default_factory=list)
    next_run_id: int = 1

    async def create_collection_run(
        self,
        _session: object,
        values: dict[str, object],
    ) -> dict[str, Any]:
        row = {"id": self.next_run_id, **values}
        self.next_run_id += 1
        self.runs.append(row)
        return row

    async def update_collection_run(
        self,
        _session: object,
        collection_run_id: int,
        values: dict[str, object],
    ) -> dict[str, Any]:
        row = next(run for run in self.runs if run["id"] == collection_run_id)
        row.update(values)
        return row

    async def create_power_sample(
        self,
        _session: object,
        values: dict[str, object],
    ) -> dict[str, Any]:
        row = {"id": len(self.samples) + 1, **values}
        self.samples.append(row)
        return row

    async def list_power_samples(
        self,
        _session: object,
        *,
        limit: int = 100,
        collection_run_id: int | None = None,
    ) -> list[dict[str, Any]]:
        rows = self.samples
        if collection_run_id is not None:
            rows = [row for row in rows if row["collection_run_id"] == collection_run_id]
        return rows[:limit]

    async def get_collection_run(
        self,
        _session: object,
        collection_run_id: int,
    ) -> dict[str, Any]:
        return next(run for run in self.runs if run["id"] == collection_run_id)


class FakeSession:
    def __init__(self) -> None:
        self.commits = 0

    async def commit(self) -> None:
        self.commits += 1


def _target(device_id: int, *, profile: str = "ilo5-redfish") -> dict[str, object]:
    return {
        "id": device_id,
        "name": f"server-{device_id}",
        "ilo_host": f"ilo-{device_id}.example.test",
        "ilo_profile": profile,
    }


def _credential() -> dict[str, object]:
    return {
        "username": "Administrator",
        "encrypted_password": "encrypted-secret",
        "tls_verify": False,
        "timeout_seconds": 10,
    }


def _install_repo_fakes(
    monkeypatch: pytest.MonkeyPatch,
    *,
    targets: list[dict[str, object]],
    repo: FakeIloRepo,
) -> None:
    async def list_targets(_session: object) -> list[dict[str, object]]:
        return targets

    async def get_credential(_session: object) -> dict[str, object]:
        return _credential()

    monkeypatch.setattr(ilo_collection.device_repo, "list_ilo_collection_targets", list_targets)
    monkeypatch.setattr(ilo_collection.settings_repo, "get_ilo_credential", get_credential)
    monkeypatch.setattr(ilo_collection, "ilo_repo", repo)
    monkeypatch.setattr(ilo_collection, "decrypt_secret", lambda value: "secret-password")


@pytest.mark.asyncio
async def test_collect_persists_failed_sample_and_continues_next_device(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = FakeIloRepo()
    _install_repo_fakes(
        monkeypatch,
        targets=[_target(1, profile="ilo5-redfish"), _target(2, profile="ilo6-redfish")],
        repo=repo,
    )

    class FakeClient:
        def __init__(self, **kwargs: object) -> None:
            self.kwargs = kwargs

        async def read_power(self) -> IloPowerReading:
            if self.kwargs["host"] == "ilo-1.example.test":
                raise RuntimeError("boom secret-password token-123")
            return IloPowerReading(
                average_watts=Decimal("77.7"),
                auth_method_used="session",
                profile_used=str(self.kwargs["profile"]),
            )

    result = await ilo_collection.collect_ilo_power(
        FakeSession(),
        client_factory=FakeClient,
    )

    assert result["status"] == "partial_success"
    assert repo.samples[0]["device_id"] == 1
    assert repo.samples[0]["average_watts"] is None
    assert repo.samples[0]["status"] == "failed"
    assert repo.samples[0]["quality"] == "collection_failed"
    assert repo.samples[0]["profile_used"] == "ilo5-redfish"
    assert repo.samples[1]["device_id"] == 2
    assert repo.samples[1]["average_watts"] == Decimal("77.7")
    assert repo.samples[1]["quality"] == "collected_ilo"
    assert "secret-password" not in str(result)
    assert "token-123" not in str(result)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("outcomes", "expected_status"),
    [
        ([Decimal("10"), Decimal("20")], "success"),
        ([Decimal("10"), RuntimeError("denied")], "partial_success"),
        ([RuntimeError("denied"), RuntimeError("timeout")], "failed"),
        ([], "skipped"),
    ],
)
async def test_collect_sets_run_statuses(
    monkeypatch: pytest.MonkeyPatch,
    outcomes: list[Decimal | Exception],
    expected_status: str,
) -> None:
    repo = FakeIloRepo()
    _install_repo_fakes(
        monkeypatch,
        targets=[_target(index + 1) for index, _outcome in enumerate(outcomes)],
        repo=repo,
    )

    class FakeClient:
        calls = 0

        def __init__(self, **_kwargs: object) -> None:
            self.index = FakeClient.calls
            FakeClient.calls += 1

        async def read_power(self) -> IloPowerReading:
            outcome = outcomes[self.index]
            if isinstance(outcome, Exception):
                raise outcome
            return IloPowerReading(
                average_watts=outcome,
                auth_method_used="basic",
                profile_used="ilo5-redfish",
            )

    result = await ilo_collection.collect_ilo_power(
        FakeSession(),
        client_factory=FakeClient,
    )

    assert result["status"] == expected_status
    assert result["started_at"].tzinfo == UTC
    assert result["finished_at"].tzinfo == UTC
    assert all(sample["measured_at"].tzinfo == UTC for sample in repo.samples)


@pytest.mark.asyncio
async def test_collect_passes_decrypted_password_only_to_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = FakeIloRepo()
    _install_repo_fakes(monkeypatch, targets=[_target(1)], repo=repo)
    seen_client_kwargs: dict[str, object] = {}

    class FakeClient:
        def __init__(self, **kwargs: object) -> None:
            seen_client_kwargs.update(kwargs)

        async def read_power(self) -> IloPowerReading:
            return IloPowerReading(
                average_watts=Decimal("42"),
                auth_method_used="session",
                profile_used="ilo5-redfish",
            )

    result = await ilo_collection.collect_ilo_power(
        FakeSession(),
        client_factory=FakeClient,
    )

    assert seen_client_kwargs["password"] == "secret-password"
    assert "secret-password" not in str(result)
    assert "secret-password" not in str(repo.runs)
    assert "secret-password" not in str(repo.samples)


@pytest.mark.asyncio
async def test_collect_records_failed_samples_when_credential_decrypt_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = FakeIloRepo()
    _install_repo_fakes(monkeypatch, targets=[_target(1), _target(2)], repo=repo)
    monkeypatch.setattr(
        ilo_collection,
        "decrypt_secret",
        lambda _value: (_ for _ in ()).throw(RuntimeError("secret-password token-123")),
    )

    result = await ilo_collection.collect_ilo_power(FakeSession())

    assert result["status"] == "failed"
    assert result["failed_count"] == 2
    assert [sample["status"] for sample in repo.samples] == ["failed", "failed"]
    assert "secret-password" not in str(result)
    assert "token-123" not in str(result)


@pytest.mark.asyncio
async def test_collect_does_not_convert_success_sample_persistence_failure_to_device_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FailingSuccessRepo(FakeIloRepo):
        async def create_power_sample(
            self,
            _session: object,
            values: dict[str, object],
        ) -> dict[str, Any]:
            if values["status"] == "success":
                raise RuntimeError("db unavailable")
            return await super().create_power_sample(_session, values)

    repo = FailingSuccessRepo()
    _install_repo_fakes(monkeypatch, targets=[_target(1)], repo=repo)

    class FakeClient:
        def __init__(self, **_kwargs: object) -> None:
            pass

        async def read_power(self) -> IloPowerReading:
            return IloPowerReading(
                average_watts=Decimal("42"),
                auth_method_used="session",
                profile_used="ilo5-redfish",
            )

    with pytest.raises(RuntimeError, match="db unavailable"):
        await ilo_collection.collect_ilo_power(FakeSession(), client_factory=FakeClient)

    assert repo.samples == []


@pytest.mark.asyncio
async def test_collect_skips_blank_ilo_targets(monkeypatch: pytest.MonkeyPatch) -> None:
    repo = FakeIloRepo()
    _install_repo_fakes(
        monkeypatch,
        targets=[
            _target(1),
            {**_target(2), "ilo_host": ""},
            {**_target(3), "ilo_host": "   "},
            {**_target(4), "ilo_profile": ""},
        ],
        repo=repo,
    )

    class FakeClient:
        def __init__(self, **kwargs: object) -> None:
            self.kwargs = kwargs

        async def read_power(self) -> IloPowerReading:
            return IloPowerReading(
                average_watts=Decimal("42"),
                auth_method_used="session",
                profile_used=str(self.kwargs["profile"]),
            )

    result = await ilo_collection.collect_ilo_power(FakeSession(), client_factory=FakeClient)

    assert result["total_targets"] == 1
    assert result["status"] == "success"
    assert [sample["device_id"] for sample in repo.samples] == [1]


@pytest.mark.asyncio
async def test_get_collection_run_returns_samples_for_that_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = FakeIloRepo()
    repo.runs.append(
        {
            "id": 10,
            "started_at": None,
            "finished_at": None,
            "status": "partial_success",
            "triggered_by": "api",
            "total_targets": 2,
            "success_count": 1,
            "failed_count": 1,
        }
    )
    repo.samples.extend(
        [
            {"id": 1, "collection_run_id": 10, "device_id": 1, "status": "success"},
            {"id": 2, "collection_run_id": 11, "device_id": 2, "status": "success"},
            {"id": 3, "collection_run_id": 10, "device_id": 3, "status": "failed"},
        ]
    )
    monkeypatch.setattr(ilo_collection, "ilo_repo", repo)

    result = await ilo_collection.get_collection_run(FakeSession(), 10)

    assert [sample["id"] for sample in result["samples"]] == [1, 3]
