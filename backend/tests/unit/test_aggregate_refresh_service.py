from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.services import aggregates


class FakeSession:
    def __init__(self) -> None:
        self.commits = 0

    async def commit(self) -> None:
        self.commits += 1


def _by_key(rows: list[dict[str, object]]) -> dict[tuple[str, int, str], dict[str, object]]:
    return {
        (
            str(row["entity_type"]),
            int(row["entity_id"]),
            str(row["source_type"]),
        ): row
        for row in rows
    }


def test_build_representative_power_results_counts_inactive_devices_as_skipped() -> None:
    now = datetime(2026, 6, 2, 14, tzinfo=UTC)

    results = aggregates.build_representative_power_results(
        now=now,
        racks=[{"id": 1, "phase": "R", "active": True}],
        devices=[
            {"id": 10, "rack_id": 1, "active": True},
            {"id": 11, "rack_id": 1, "active": False},
        ],
        ilo_by_device={},
        manual_device_by_device={},
        rack_measurements_by_rack={},
        phase_main_by_phase={},
    )

    rack = next(
        result
        for result in results
        if result.entity_type == "rack" and result.entity_id == 1
    )
    assert rack.skipped_count == 1


def test_build_representative_power_results_counts_stale_rejected_candidates() -> None:
    now = datetime(2026, 6, 2, 14, tzinfo=UTC)

    results = aggregates.build_representative_power_results(
        now=now,
        racks=[{"id": 1, "phase": "R", "active": True}],
        devices=[{"id": 10, "rack_id": 1, "active": True}],
        ilo_by_device={
            10: {
                "device_id": 10,
                "average_watts": Decimal("100"),
                "measured_at": now - timedelta(hours=2),
                "quality": "collected_ilo",
            }
        },
        manual_device_by_device={},
        rack_measurements_by_rack={},
        phase_main_by_phase={},
    )

    device = next(
        result
        for result in results
        if result.entity_type == "device" and result.entity_id == 10
    )
    rack = next(
        result
        for result in results
        if result.entity_type == "rack" and result.entity_id == 1
    )
    assert device.stale is True
    assert device.stale_count == 1
    assert rack.stale_count == 1


@pytest.mark.asyncio
async def test_refresh_power_aggregates_upserts_current_hour_representatives(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = FakeSession()
    now = datetime(2026, 6, 2, 14, 45, 33, tzinfo=UTC)
    upserted: list[dict[str, object]] = []

    async def fake_list_racks(_session: object) -> list[dict[str, object]]:
        return [
            {"id": 1, "name": "rack-a", "phase": "R", "active": True},
            {"id": 2, "name": "rack-b", "phase": "S", "active": True},
            {"id": 3, "name": "rack-empty", "phase": "T", "active": True},
        ]

    async def fake_list_devices(_session: object) -> list[dict[str, object]]:
        return [
            {"id": 10, "rack_id": 1, "active": True},
            {"id": 11, "rack_id": 1, "active": True},
            {"id": 12, "rack_id": 2, "active": True},
            {"id": 13, "rack_id": 2, "active": False},
        ]

    async def fake_ilo(_session: object, measured_at_to: datetime) -> dict[int, dict[str, object]]:
        assert measured_at_to == now
        return {
            10: {
                "device_id": 10,
                "average_watts": Decimal("150.5"),
                "measured_at": now - timedelta(minutes=5),
                "quality": "collected_ilo",
            }
        }

    async def fake_manual_device(
        _session: object,
        measured_at_to: datetime,
    ) -> dict[int, dict[str, object]]:
        assert measured_at_to == now
        return {
            10: {
                "device_id": 10,
                "watts": Decimal("120"),
                "measured_at": now - timedelta(minutes=10),
                "quality": "manual",
            },
            11: {
                "device_id": 11,
                "watts": Decimal("30"),
                "measured_at": now - timedelta(days=1),
                "quality": "manual",
            },
        }

    async def fake_rack_measurements(
        _session: object,
        measured_at_to: datetime,
    ) -> dict[int, dict[str, object]]:
        assert measured_at_to == now
        return {
            2: {
                "rack_id": 2,
                "watts": Decimal("500"),
                "measured_at": now - timedelta(days=1),
                "quality": "manual",
            }
        }

    async def fake_phase_main(
        _session: object,
        measured_at_to: datetime,
    ) -> dict[str, dict[str, object]]:
        assert measured_at_to == now
        return {
            "R": {
                "phase": "R",
                "calculated_watts": Decimal("140"),
                "measured_at": now - timedelta(minutes=20),
                "quality": "manual",
            },
            "S": {
                "phase": "S",
                "calculated_watts": Decimal("700"),
                "measured_at": now - timedelta(minutes=20),
                "quality": "manual",
            },
            "T": {
                "phase": "T",
                "calculated_watts": Decimal("10"),
                "measured_at": now - timedelta(minutes=20),
                "quality": "manual",
            },
        }

    async def fake_upsert(_session: object, values: dict[str, object]) -> dict[str, object]:
        upserted.append(values)
        return values

    monkeypatch.setattr(aggregates.rack_repo, "list_racks", fake_list_racks)
    monkeypatch.setattr(aggregates.device_repo, "list_devices", fake_list_devices)
    monkeypatch.setattr(
        aggregates.ilo_repo,
        "list_latest_power_samples_by_device",
        fake_ilo,
    )
    monkeypatch.setattr(
        aggregates.measurement_repo,
        "list_latest_manual_device_power_by_device",
        fake_manual_device,
    )
    monkeypatch.setattr(
        aggregates.measurement_repo,
        "list_latest_rack_measurements_by_rack",
        fake_rack_measurements,
    )
    monkeypatch.setattr(
        aggregates.measurement_repo,
        "list_latest_phase_main_measurements_by_phase",
        fake_phase_main,
    )
    monkeypatch.setattr(aggregates.aggregate_repo, "upsert_power_aggregate", fake_upsert)

    summary = await aggregates.refresh_power_aggregates(session, now=now)

    period_start = datetime(2026, 6, 2, 14, tzinfo=UTC)
    rows = _by_key(upserted)
    assert session.commits == 1
    assert summary == {
        "status": "success",
        "period": "hour",
        "period_start": period_start,
        "upserted_count": 10,
        "unknown_count": 2,
        "stale_count": 0,
        "skipped_count": 0,
    }
    assert rows[("device", 10, "ilo")]["avg_watts"] == Decimal("150.5")
    assert rows[("device", 11, "device_manual")]["avg_watts"] == Decimal("30")
    assert rows[("device", 12, "representative")]["unknown_count"] == 1
    assert rows[("rack", 1, "representative")]["avg_watts"] == Decimal("180.5")
    assert rows[("rack", 2, "rack_measured")]["avg_watts"] == Decimal("500")
    assert rows[("rack", 3, "representative")]["unknown_count"] == 1
    assert rows[("phase", 1, "representative")]["avg_watts"] == Decimal("180.5")
    assert rows[("phase", 2, "phase_main")]["avg_watts"] == Decimal("700")
    assert rows[("overall", 0, "phase_main")]["avg_watts"] == Decimal("850")
    assert all(row["period_start"] == period_start for row in upserted)
    assert all(row["created_at"].tzinfo is UTC for row in upserted)
    assert all(row["updated_at"].tzinfo is UTC for row in upserted)


@pytest.mark.asyncio
async def test_refresh_power_aggregates_rejects_naive_now() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        await aggregates.refresh_power_aggregates(FakeSession(), now=datetime(2026, 6, 2, 14))


@pytest.mark.asyncio
async def test_refresh_power_aggregates_converts_aware_now_to_utc_hour(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = FakeSession()
    seen_to: list[datetime] = []
    upserted: list[dict[str, object]] = []

    async def empty_list(_session: object) -> list[dict[str, object]]:
        return []

    async def empty_by_device(
        _session: object,
        measured_at_to: datetime,
    ) -> dict[int, dict[str, object]]:
        seen_to.append(measured_at_to)
        return {}

    async def empty_by_rack(
        _session: object,
        measured_at_to: datetime,
    ) -> dict[int, dict[str, object]]:
        seen_to.append(measured_at_to)
        return {}

    async def empty_by_phase(
        _session: object,
        measured_at_to: datetime,
    ) -> dict[str, dict[str, object]]:
        seen_to.append(measured_at_to)
        return {}

    async def fake_upsert(_session: object, values: dict[str, object]) -> dict[str, object]:
        upserted.append(values)
        return values

    monkeypatch.setattr(aggregates.rack_repo, "list_racks", empty_list)
    monkeypatch.setattr(aggregates.device_repo, "list_devices", empty_list)
    monkeypatch.setattr(
        aggregates.ilo_repo,
        "list_latest_power_samples_by_device",
        empty_by_device,
    )
    monkeypatch.setattr(
        aggregates.measurement_repo,
        "list_latest_manual_device_power_by_device",
        empty_by_device,
    )
    monkeypatch.setattr(
        aggregates.measurement_repo,
        "list_latest_rack_measurements_by_rack",
        empty_by_rack,
    )
    monkeypatch.setattr(
        aggregates.measurement_repo,
        "list_latest_phase_main_measurements_by_phase",
        empty_by_phase,
    )
    monkeypatch.setattr(aggregates.aggregate_repo, "upsert_power_aggregate", fake_upsert)

    summary = await aggregates.refresh_power_aggregates(
        session,
        now=datetime(2026, 6, 3, 0, 15, tzinfo=timezone(timedelta(hours=9))),
    )

    expected_now = datetime(2026, 6, 2, 15, 15, tzinfo=UTC)
    assert seen_to == [expected_now, expected_now, expected_now, expected_now]
    assert summary["period_start"] == datetime(2026, 6, 2, 15, tzinfo=UTC)
    assert summary["upserted_count"] == 4
    assert session.commits == 1
    assert {
        (row["entity_type"], row["entity_id"], row["source_type"])
        for row in upserted
    } == {
        ("phase", 1, "representative"),
        ("phase", 2, "representative"),
        ("phase", 3, "representative"),
        ("overall", 0, "representative"),
    }
