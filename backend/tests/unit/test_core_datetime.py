from datetime import UTC, datetime

import pytest

from app.core.datetime import ensure_aware, to_utc


def test_ensure_aware_rejects_naive_datetime() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        ensure_aware(datetime(2026, 5, 29, 12, 0, 0))


def test_to_utc_converts_aware_datetime() -> None:
    value = datetime(2026, 5, 29, 3, 0, 0, tzinfo=UTC)

    assert to_utc(value) == datetime(2026, 5, 29, 3, 0, 0, tzinfo=UTC)
