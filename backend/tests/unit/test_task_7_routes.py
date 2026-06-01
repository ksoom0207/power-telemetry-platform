from app.main import app


def test_task_7_routes_are_registered() -> None:
    paths = {route.path for route in app.routes}

    assert "/aggregates" in paths
    assert "/rack-hourly-kwh" in paths
    assert "/rack-monthly-kwh" in paths
    assert "/thresholds" in paths
    assert "/thresholds/{threshold_id}" in paths
    assert "/threshold-states" in paths
