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
