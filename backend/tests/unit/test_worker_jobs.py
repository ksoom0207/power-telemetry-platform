import pytest

from app.workers import jobs


@pytest.mark.asyncio
async def test_run_threshold_evaluation_job_calls_service(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = object()
    called_with: list[object] = []

    async def fake_evaluate_active_thresholds(received_session: object) -> dict[str, object]:
        called_with.append(received_session)
        return {"status": "success", "processed_count": 3, "skipped_count": 1}

    monkeypatch.setattr(
        jobs.threshold_service,
        "evaluate_active_thresholds",
        fake_evaluate_active_thresholds,
    )

    result = await jobs.run_threshold_evaluation_job(session)  # type: ignore[arg-type]

    assert called_with == [session]
    assert result == {"status": "success", "processed_count": 3, "skipped_count": 1}


@pytest.mark.asyncio
async def test_run_kwh_job_calls_refresh_service(monkeypatch: pytest.MonkeyPatch) -> None:
    session = object()
    called_with: list[object] = []
    called_kwargs: list[dict[str, object]] = []

    async def fake_refresh_kwh_for_range(
        received_session: object,
        **kwargs: object,
    ) -> dict[str, object]:
        called_with.append(received_session)
        called_kwargs.append(kwargs)
        return {"status": "success", "rack_count": 2}

    monkeypatch.setattr(
        jobs.kwh_service,
        "refresh_kwh_for_range",
        fake_refresh_kwh_for_range,
    )

    result = await jobs.run_kwh_job(session)  # type: ignore[arg-type]

    assert called_with == [session]
    assert called_kwargs == [{}]
    assert result == {"status": "success", "rack_count": 2}


@pytest.mark.asyncio
async def test_run_recalculation_job_calls_recalculation_service(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = object()
    called_with: list[object] = []
    called_kwargs: list[dict[str, object]] = []

    async def fake_process_kwh_recalculations(
        received_session: object,
        **kwargs: object,
    ) -> dict[str, object]:
        called_with.append(received_session)
        called_kwargs.append(kwargs)
        return {"status": "success", "processed_count": 3}

    monkeypatch.setattr(
        jobs.kwh_service,
        "process_kwh_recalculations",
        fake_process_kwh_recalculations,
    )

    result = await jobs.run_recalculation_job(session)  # type: ignore[arg-type]

    assert called_with == [session]
    assert called_kwargs == [{}]
    assert result == {"status": "success", "processed_count": 3}
