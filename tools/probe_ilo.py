#!/usr/bin/env python3
from __future__ import annotations

import argparse
import getpass
import json
import os
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class HttpResult:
    status: int
    headers: dict[str, str]
    body: Any
    raw: bytes


class ProbeClient:
    def __init__(
        self,
        *,
        host: str,
        username: str,
        password: str,
        verify_tls: bool,
        timeout: float,
    ) -> None:
        scheme_host = host if "://" in host else f"https://{host}"
        self.base_url = scheme_host.rstrip("/")
        self.username = username
        self.password = password
        self.timeout = timeout
        self.token: str | None = None
        self.context = None if verify_tls else ssl._create_unverified_context()

    def request(
        self,
        method: str,
        path: str,
        *,
        json_body: dict[str, Any] | None = None,
        use_session: bool = True,
        use_basic: bool = False,
    ) -> HttpResult:
        url = urllib.parse.urljoin(f"{self.base_url}/", path.lstrip("/"))
        data = None
        headers = {"Accept": "application/json"}
        if json_body is not None:
            data = json.dumps(json_body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        if use_session and self.token:
            headers["X-Auth-Token"] = self.token
        handlers: list[urllib.request.BaseHandler] = []
        if self.context is not None:
            handlers.append(urllib.request.HTTPSHandler(context=self.context))
        if use_basic:
            password_mgr = urllib.request.HTTPPasswordMgrWithDefaultRealm()
            password_mgr.add_password(None, url, self.username, self.password)
            handlers.append(urllib.request.HTTPBasicAuthHandler(password_mgr))
        opener = urllib.request.build_opener(*handlers)

        request = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with opener.open(request, timeout=self.timeout) as response:
                raw = response.read()
                return HttpResult(
                    status=response.status,
                    headers=dict(response.headers.items()),
                    body=parse_json(raw),
                    raw=raw,
                )
        except urllib.error.HTTPError as exc:
            raw = exc.read()
            return HttpResult(
                status=exc.code,
                headers=dict(exc.headers.items()),
                body=parse_json(raw),
                raw=raw,
            )

    def login_session(self) -> HttpResult:
        result = self.request(
            "POST",
            "/redfish/v1/SessionService/Sessions",
            json_body={"UserName": self.username, "Password": self.password},
            use_session=False,
        )
        token = result.headers.get("X-Auth-Token")
        if token:
            self.token = token
        return result


def parse_json(raw: bytes) -> Any:
    if not raw:
        return None
    try:
        return json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError:
        return None


def status_line(label: str, result: HttpResult) -> None:
    ok = 200 <= result.status < 300
    marker = "OK" if ok else "FAIL"
    print(f"{label}: {marker} HTTP {result.status}")


def get_path(payload: Any, *path: str) -> Any:
    current = payload
    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def list_members(payload: Any) -> list[str]:
    members = get_path(payload, "Members")
    if not isinstance(members, list):
        return []
    values: list[str] = []
    for member in members:
        if isinstance(member, dict):
            oid = member.get("@odata.id")
            if isinstance(oid, str):
                values.append(oid)
    return values


def extract_power_values(payload: Any) -> dict[str, Any]:
    values: dict[str, Any] = {}
    if not isinstance(payload, dict):
        return values

    controls = payload.get("PowerControl")
    if isinstance(controls, list):
        for index, control in enumerate(controls):
            if not isinstance(control, dict):
                continue
            prefix = f"PowerControl[{index}]"
            if "PowerConsumedWatts" in control:
                values[f"{prefix}.PowerConsumedWatts"] = control["PowerConsumedWatts"]
            metrics = control.get("PowerMetrics")
            if isinstance(metrics, dict):
                for key in (
                    "AverageConsumedWatts",
                    "MinConsumedWatts",
                    "MaxConsumedWatts",
                    "IntervalInMin",
                ):
                    if key in metrics:
                        values[f"{prefix}.PowerMetrics.{key}"] = metrics[key]

    supplies = payload.get("PowerSupplies")
    if isinstance(supplies, list):
        for index, supply in enumerate(supplies):
            if not isinstance(supply, dict):
                continue
            for key in ("PowerCapacityWatts", "LastPowerOutputWatts", "LineInputVoltage"):
                if key in supply:
                    values[f"PowerSupplies[{index}].{key}"] = supply[key]
    return values


def probe_chassis_power(client: ProbeClient, chassis_path: str, *, use_basic: bool) -> None:
    power_path = f"{chassis_path.rstrip('/')}/Power"
    power = client.request("GET", power_path, use_basic=use_basic)
    status_line(f"Power endpoint {power_path}", power)
    values = extract_power_values(power.body)
    if values:
        print("Power values:")
        for key, value in values.items():
            print(f"  - {key}: {value}")
    else:
        print("Power values: none found")


def main() -> int:
    parser = argparse.ArgumentParser(description="Probe HPE iLO Redfish power endpoints.")
    parser.add_argument("--host", required=True, help="iLO host or URL")
    parser.add_argument("--user", default=os.getenv("ILO_USER"), help="iLO username")
    parser.add_argument("--password-env", default="ILO_PASSWORD", help="Env var containing password")
    parser.add_argument("--timeout", type=float, default=10)
    parser.add_argument("--verify-tls", action="store_true")
    parser.add_argument("--basic-only", action="store_true")
    parser.add_argument("--dump-json", action="store_true")
    args = parser.parse_args()

    username = args.user or input("iLO username: ")
    password = os.getenv(args.password_env)
    if not password:
        password = getpass.getpass("iLO password: ")

    client = ProbeClient(
        host=args.host,
        username=username,
        password=password,
        verify_tls=args.verify_tls,
        timeout=args.timeout,
    )

    print(f"Target: {client.base_url}")
    print(f"TLS verify: {args.verify_tls}")

    use_basic = args.basic_only
    if not args.basic_only:
        session = client.login_session()
        status_line("Redfish session login", session)
        if client.token:
            print("Session token: received")
        else:
            print("Session token: not received; falling back to Basic Auth")
            use_basic = True

    root = client.request("GET", "/redfish/v1/", use_basic=use_basic)
    status_line("Redfish root /redfish/v1/", root)
    if isinstance(root.body, dict):
        print(f"RedfishVersion: {root.body.get('RedfishVersion', 'unknown')}")
        print(f"Product: {root.body.get('Product', 'unknown')}")

    chassis_collection = client.request("GET", "/redfish/v1/Chassis", use_basic=use_basic)
    status_line("Chassis collection /redfish/v1/Chassis", chassis_collection)
    chassis_paths = list_members(chassis_collection.body)
    if not chassis_paths:
        chassis_paths = ["/redfish/v1/Chassis/1"]
        print("Chassis members: none found; trying /redfish/v1/Chassis/1")
    else:
        print("Chassis members:")
        for path in chassis_paths:
            print(f"  - {path}")

    for chassis_path in chassis_paths:
        probe_chassis_power(client, chassis_path, use_basic=use_basic)

    if args.dump_json:
        print("Root JSON:")
        print(json.dumps(root.body, indent=2, ensure_ascii=False))
        print("Chassis JSON:")
        print(json.dumps(chassis_collection.body, indent=2, ensure_ascii=False))

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (TimeoutError, urllib.error.URLError) as exc:
        print(f"Probe failed: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
