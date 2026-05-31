from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

from app.core.errors import ExternalApiError

POWER_PATH = "/redfish/v1/Chassis/1/Power"
SUPPORTED_PROFILE_NAMES = (
    "ilo4-redfish",
    "ilo5-redfish",
    "ilo6-redfish",
    "legacy-hpe-rest",
)


@dataclass(frozen=True)
class IloProfile:
    name: str
    power_path: str = POWER_PATH

    def parse_average_watts(self, payload: Mapping[str, Any]) -> Decimal:
        try:
            power_controls = payload["PowerControl"]
            for control in power_controls:
                metrics = control.get("PowerMetrics", {})
                if "AverageConsumedWatts" in metrics:
                    watts = Decimal(str(metrics["AverageConsumedWatts"]))
                    if not watts.is_finite():
                        raise InvalidOperation
                    return watts
        except (AttributeError, InvalidOperation, KeyError, TypeError) as exc:
            raise ExternalApiError(
                "failed to parse iLO power response",
                {"profile": self.name, "reason": "invalid_average_consumed_watts"},
            ) from exc
        raise ExternalApiError(
            "failed to parse iLO power response",
            {"profile": self.name, "reason": "missing_average_consumed_watts"},
        )


_PROFILES = {name: IloProfile(name=name) for name in SUPPORTED_PROFILE_NAMES}


def get_profile(name: str) -> IloProfile:
    try:
        return _PROFILES[name]
    except KeyError as exc:
        raise ExternalApiError("unsupported iLO profile", {"profile": name}) from exc


def supported_profiles() -> list[str]:
    return list(SUPPORTED_PROFILE_NAMES)
