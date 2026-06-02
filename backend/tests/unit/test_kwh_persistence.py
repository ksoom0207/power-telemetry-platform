from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.services import kwh as kwh_service
from app.services.kwh import HourlyKwhResult, HourlyPowerPoint, build_hourly_kwh


def test_monthly_summary_uses_hourly_rows_for_actual_estimated_split() -> None:
    start = datetime(2026, 5, 1, tzinfo=UTC)
    rows = [
        HourlyKwhResult(
            hour_start=start,
            actual_kwh=Decimal("1.5"),
            estimated_kwh=Decimal("0"),
            basis_source="rack_measured",
            coverage_state="actual",
        ),
        HourlyKwhResult(
            hour_start=start + timedelta(hours=1),
            actual_kwh=Decimal("0"),
            estimated_kwh=Decimal("1.5"),
            basis_source="carry_forward",
            coverage_state="estimated",
        ),
        HourlyKwhResult(
            hour_start=start + timedelta(hours=2),
            actual_kwh=Decimal("0"),
            estimated_kwh=Decimal("0"),
            basis_source="carry_forward",
            coverage_state="missing",
        ),
    ]

    summary = kwh_service.build_monthly_kwh_summary(
        rack_id=7,
        month=start,
        hourly_rows=rows,
        total_hours=3,
        carry_forward_max_hours=1,
    )

    assert summary["actual_kwh"] == Decimal("1.5")
    assert summary["estimated_kwh"] == Decimal("3.0")
    assert summary["coverage_percent"] == Decimal("33.333")
    assert summary["estimated_hours"] == Decimal("1")


def test_carry_forward_cap_missing_rows_do_not_create_estimated_kwh_beyond_cap() -> None:
    start = datetime(2026, 5, 1, tzinfo=UTC)

    hourly = build_hourly_kwh(
        start=start,
        hours=4,
        actual_points=[
            HourlyPowerPoint(
                hour_start=start,
                watts=Decimal("1000"),
                basis_source="rack_measured",
            )
        ],
        carry_forward_max_hours=1,
    )
    summary = kwh_service.build_monthly_kwh_summary(
        rack_id=7,
        month=start,
        hourly_rows=hourly,
        total_hours=4,
        carry_forward_max_hours=1,
    )

    assert [row.coverage_state for row in hourly] == ["actual", "estimated", "missing", "missing"]
    assert summary["actual_kwh"] == Decimal("1")
    assert summary["estimated_kwh"] == Decimal("2")
    assert summary["estimated_hours"] == Decimal("1")


class FakeSession:
    def __init__(self) -> None:
        self.commits = 0

    async def commit(self) -> None:
        self.commits += 1


@pytest.mark.asyncio
async def test_refresh_rack_kwh_for_range_builds_hourly_rows_from_power_aggregates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = FakeSession()
    start = datetime(2026, 5, 1, tzinfo=UTC)
    end = start + timedelta(hours=4)
    aggregate_rows = [
        {
            "entity_id": 7,
            "period_start": start,
            "source_type": "ilo",
            "avg_watts": Decimal("900"),
            "sample_count": 1,
        },
        {
            "entity_id": 7,
            "period_start": start,
            "source_type": "rack_measured",
            "avg_watts": Decimal("1000"),
            "sample_count": 1,
        },
        {
            "entity_id": 7,
            "period_start": start + timedelta(hours=2),
            "source_type": "representative",
            "avg_watts": Decimal("2000"),
            "sample_count": 2,
        },
        {
            "entity_id": 7,
            "period_start": start + timedelta(hours=3),
            "source_type": "rack_measured",
            "avg_watts": None,
            "sample_count": 2,
        },
        {
            "entity_id": 7,
            "period_start": start + timedelta(hours=3),
            "source_type": "representative",
            "avg_watts": Decimal("3000"),
            "sample_count": 0,
        },
    ]
    persisted_rows: list[dict[str, object]] = []
    monthly_rows: list[dict[str, object]] = []

    async def fake_list_aggregates(*args: object, **kwargs: object) -> list[dict[str, object]]:
        assert args == (session,)
        assert kwargs == {
            "period_start_from": start,
            "period_start_to": end,
            "rack_id": 7,
            "limit": None,
        }
        return aggregate_rows

    async def fake_upsert_hourly(*args: object, **kwargs: object) -> list[dict[str, object]]:
        assert args == (session,)
        rows = kwargs["rows"]
        persisted_rows.extend(rows)
        return rows

    async def fake_list_hourly(*args: object, **kwargs: object) -> list[dict[str, object]]:
        assert args == (session,)
        assert kwargs == {
            "rack_id": 7,
            "hour_start_from": start,
            "hour_start_to": datetime(2026, 6, 1, tzinfo=UTC),
            "limit": 744,
        }
        return [
            {
                "rack_id": row["rack_id"],
                "hour_start": row["hour_start"],
                "actual_kwh": row["actual_kwh"],
                "estimated_kwh": row["estimated_kwh"],
                "basis_source": row["basis_source"],
                "coverage_state": row["coverage_state"],
            }
            for row in persisted_rows
        ]

    async def fake_upsert_monthly(*args: object, **kwargs: object) -> dict[str, object]:
        assert args == (session,)
        monthly_rows.append(kwargs["values"])
        return kwargs["values"]

    monkeypatch.setattr(
        kwh_service.aggregates_repo,
        "list_rack_hourly_power_aggregates",
        fake_list_aggregates,
    )
    monkeypatch.setattr(kwh_service.kwh_repo, "upsert_rack_hourly_kwh_rows", fake_upsert_hourly)
    monkeypatch.setattr(kwh_service.kwh_repo, "list_rack_hourly_kwh", fake_list_hourly)
    monkeypatch.setattr(kwh_service.kwh_repo, "upsert_rack_monthly_kwh", fake_upsert_monthly)

    result = await kwh_service.refresh_rack_kwh_for_range(
        session, rack_id=7, start=start, end=end, carry_forward_max_hours=1
    )

    assert result == {"rack_id": 7, "hourly_count": 4, "monthly_count": 1}
    assert [row["coverage_state"] for row in persisted_rows] == [
        "actual",
        "estimated",
        "actual",
        "estimated",
    ]
    assert persisted_rows[0]["basis_source"] == "rack_measured"
    assert persisted_rows[0]["actual_kwh"] == Decimal("1")
    assert persisted_rows[1]["estimated_kwh"] == Decimal("1")
    assert persisted_rows[2]["actual_kwh"] == Decimal("2")
    assert persisted_rows[3]["estimated_kwh"] == Decimal("2")
    assert monthly_rows[0]["actual_kwh"] == Decimal("3")
    assert monthly_rows[0]["estimated_kwh"] == Decimal("6")
    assert session.commits == 1


@pytest.mark.asyncio
async def test_refresh_rack_kwh_for_range_rejects_non_hour_boundary_range(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called = False

    async def fake_list_aggregates(*args: object, **kwargs: object) -> list[dict[str, object]]:
        nonlocal called
        called = True
        return []

    monkeypatch.setattr(
        kwh_service.aggregates_repo,
        "list_rack_hourly_power_aggregates",
        fake_list_aggregates,
    )

    with pytest.raises(ValueError, match="hour boundaries"):
        await kwh_service.refresh_rack_kwh_for_range(
            FakeSession(),
            rack_id=7,
            start=datetime(2026, 5, 1, 0, 30, tzinfo=UTC),
            end=datetime(2026, 5, 1, 2, tzinfo=UTC),
            carry_forward_max_hours=1,
        )

    assert called is False


@pytest.mark.asyncio
async def test_refresh_kwh_for_range_processes_invalid_only_racks_as_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = FakeSession()
    start = datetime(2026, 5, 1, tzinfo=UTC)
    end = start + timedelta(hours=2)
    aggregate_calls = 0
    persisted_rows: list[dict[str, object]] = []

    async def fake_list_aggregates(*args: object, **kwargs: object) -> list[dict[str, object]]:
        nonlocal aggregate_calls
        aggregate_calls += 1
        assert args == (session,)
        assert kwargs == {
            "period_start_from": start,
            "period_start_to": end,
            "rack_id": None,
            "limit": None,
        }
        return [
            {
                "entity_id": 7,
                "period_start": start,
                "source_type": "rack_measured",
                "avg_watts": None,
                "sample_count": 0,
            }
        ]

    async def fake_upsert_hourly(*args: object, **kwargs: object) -> list[dict[str, object]]:
        rows = kwargs["rows"]
        persisted_rows.extend(rows)
        return rows

    async def fake_list_hourly(*args: object, **kwargs: object) -> list[dict[str, object]]:
        return [
            {
                "rack_id": row["rack_id"],
                "hour_start": row["hour_start"],
                "actual_kwh": row["actual_kwh"],
                "estimated_kwh": row["estimated_kwh"],
                "basis_source": row["basis_source"],
                "coverage_state": row["coverage_state"],
            }
            for row in persisted_rows
        ]

    async def fake_upsert_monthly(*args: object, **kwargs: object) -> dict[str, object]:
        return kwargs["values"]

    monkeypatch.setattr(
        kwh_service.aggregates_repo,
        "list_rack_hourly_power_aggregates",
        fake_list_aggregates,
    )
    monkeypatch.setattr(kwh_service.kwh_repo, "upsert_rack_hourly_kwh_rows", fake_upsert_hourly)
    monkeypatch.setattr(kwh_service.kwh_repo, "list_rack_hourly_kwh", fake_list_hourly)
    monkeypatch.setattr(kwh_service.kwh_repo, "upsert_rack_monthly_kwh", fake_upsert_monthly)

    result = await kwh_service.refresh_kwh_for_range(
        session,
        start=start,
        end=end,
        carry_forward_max_hours=1,
    )

    assert result["rack_count"] == 1
    assert aggregate_calls == 1
    assert [row["coverage_state"] for row in persisted_rows] == ["missing", "missing"]


@pytest.mark.asyncio
async def test_refresh_monthly_kwh_from_persisted_hourly_uses_stored_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = FakeSession()
    month = datetime(2026, 5, 1, tzinfo=UTC)
    persisted_hourly = [
        {
            "rack_id": 7,
            "hour_start": month,
            "actual_kwh": Decimal("1"),
            "estimated_kwh": Decimal("0"),
            "basis_source": "rack_measured",
            "coverage_state": "actual",
        },
        {
            "rack_id": 7,
            "hour_start": month + timedelta(hours=1),
            "actual_kwh": Decimal("0"),
            "estimated_kwh": Decimal("1"),
            "basis_source": "carry_forward",
            "coverage_state": "estimated",
        },
    ]
    monthly_values: list[dict[str, object]] = []

    async def fake_list_hourly(*args: object, **kwargs: object) -> list[dict[str, object]]:
        assert kwargs["hour_start_from"] == month
        assert kwargs["hour_start_to"] == datetime(2026, 6, 1, tzinfo=UTC)
        assert kwargs["limit"] == 744
        return persisted_hourly

    async def fake_upsert_monthly(*args: object, **kwargs: object) -> dict[str, object]:
        monthly_values.append(kwargs["values"])
        return kwargs["values"]

    monkeypatch.setattr(kwh_service.kwh_repo, "list_rack_hourly_kwh", fake_list_hourly)
    monkeypatch.setattr(kwh_service.kwh_repo, "upsert_rack_monthly_kwh", fake_upsert_monthly)

    result = await kwh_service.refresh_monthly_kwh_from_persisted_hourly(
        session,
        rack_id=7,
        month=month,
        carry_forward_max_hours=1,
    )

    assert result["actual_kwh"] == Decimal("1")
    assert result["estimated_kwh"] == Decimal("2")
    assert result["coverage_percent"] == Decimal("0.134")
    assert monthly_values == [result]
    assert session.commits == 1


@pytest.mark.asyncio
async def test_process_kwh_recalculations_refreshes_flagged_months_and_clears_flags(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = FakeSession()
    month = datetime(2026, 5, 1, tzinfo=UTC)
    cleared: list[tuple[int, datetime]] = []

    async def fake_list_months(*args: object, **kwargs: object) -> list[dict[str, object]]:
        assert kwargs == {"limit": 10}
        return [{"rack_id": 7, "month": month}]

    async def fake_refresh(*args: object, **kwargs: object) -> dict[str, object]:
        assert args == (session,)
        assert kwargs == {"rack_id": 7, "month": month, "carry_forward_max_hours": 2}
        await session.commit()
        return {"rack_id": 7, "month": month}

    async def fake_clear(*args: object, **kwargs: object) -> None:
        cleared.append((kwargs["rack_id"], kwargs["month"]))

    monkeypatch.setattr(kwh_service.kwh_repo, "list_months_needing_recalculation", fake_list_months)
    monkeypatch.setattr(kwh_service, "refresh_monthly_kwh_from_persisted_hourly", fake_refresh)
    monkeypatch.setattr(kwh_service.kwh_repo, "clear_month_recalculation", fake_clear)

    result = await kwh_service.process_kwh_recalculations(
        session, limit=10, carry_forward_max_hours=2
    )

    assert result == {"status": "success", "processed_count": 1}
    assert cleared == [(7, month)]
    assert session.commits == 2
