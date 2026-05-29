# Power Monitoring Dashboard Design

## 1. Goal

Build an internal web dashboard for IDC/server-room operators to monitor power usage by server, device, rack, phase, and overall facility view.

The first implementation prioritizes backend correctness and worker processing. The React frontend is intentionally simple and exists to validate real API flows and support basic operation.

## 2. Explicit Scope

Included:

- HPE iLO Redfish / iLO RESTful API power collection.
- Mixed iLO 4, iLO 5, and iLO 6 environments.
- Server, storage, and network device inventory.
- Rack-level and R/S/T phase-level manual measurements.
- Device-level manual power values.
- Rack and phase monitoring.
- Threshold evaluation for device, rack, phase, and overall values.
- Hourly, daily, and monthly aggregates.
- Monthly rack kWh.
- Measurement quality, freshness, and coverage tracking.
- Excel template import for rack and device registration/update.
- Docker Compose deployment.

Excluded from initial version:

- Login and authorization.
- Slack/Teams external notifications.
- PDU/API automatic collection.
- Electricity billing calculation.
- CSV upload.
- Rack floor-plan view.
- WebSocket/SSE push updates.

## 3. Users

Primary users are IDC/server-room operators.

The application must favor:

- Fast status checking.
- Bulk manual measurement entry.
- Rack/device maintenance.
- Clear distinction between measured, collected, estimated, and missing data.
- Clear distinction between fresh, stale, estimated, and unknown values.

## 4. System Architecture

Services:

- `backend`: FastAPI API server.
- `worker`: background worker container sharing the backend codebase.
- `frontend`: React + TypeScript frontend.
- `db`: PostgreSQL.

Deployment target:

- Docker Compose inside the IDC/server-room network.
- Backend and worker must be able to reach iLO addresses directly.

The worker is separated from the API server so iLO timeouts and aggregation work do not block dashboard requests.

## 5. Technology Stack

Backend:

- Python.
- FastAPI.
- SQLAlchemy 2.x.
- Alembic.
- Pydantic v2.
- PostgreSQL.
- pytest.

Worker:

- Same Python codebase as backend.
- Initial scheduler can be APScheduler or an equivalent single worker scheduler loop.

Frontend:

- React.
- TypeScript.
- Vite.
- React Query is recommended for API state.

## 6. Electrical Model

The facility receives R/S/T 380V three-phase power, but racks are distributed as 220V single-phase loads from one phase to neutral.

Default rack and phase-main calculation:

```text
watts = voltage * amp * power_factor
default voltage = 220V
default power_factor = 0.95
```

R/S/T phase-main input uses amp-only entry in the initial version. The app applies the configured default voltage and power factor.

Power values calculated with default voltage or default power factor must be marked as calculated values, not direct wattmeter measurements.

The three-phase formula:

```text
watts = sqrt(3) * voltage * amp * power_factor
```

is only for direct three-phase load measurement and is not the default for rack or R/S/T phase-main calculations in this system.

iLO power is treated as collected device-level telemetry, not calibrated facility meter data. Rack and phase measured values are preferred for electrical load and capacity views.

## 7. Core Data Model

### Rack

- `id`
- `name`
- `phase`: `R`, `S`, or `T`
- `voltage`
- `circuit_name`
- `capacity_amp`
- `active`

Rack names are unique. Deleting a rack from the web UI means setting `active=false`.

### Device

- `id`
- `name`
- `rack_id`
- `device_type`: `server`, `storage`, `network`, `etc`
- `u_position_start`
- `u_position_end`
- `has_ilo`
- `ilo_host`
- `ilo_profile`
- `active`

Device names are unique. Deleting a device from the web UI means setting `active=false`.

### IloCredentialSetting

- `username`
- `encrypted_password`
- `auth_mode`: `session_with_basic_fallback`
- `tls_verify`
- `timeout_seconds`

The password is encrypted in the database using an application encryption key supplied by Docker environment variable.

### IloPowerSample

- `device_id`
- `collection_run_id`
- `measured_at`
- `average_watts`
- `status`: `success` or `failed`
- `auth_method_used`
- `profile_used`
- `quality`: `collected_ilo`

Failed iLO collection attempts are stored with `average_watts=null` and `status=failed`. Aggregates and representative power calculations use only successful rows.

### CollectionRun

- `id`
- `started_at`
- `finished_at`
- `status`: `running`, `completed`, `partial_failed`, or `failed`
- `triggered_by`: `scheduler` or `manual`
- `total_targets`
- `success_count`
- `failed_count`

`CollectionRun` groups one iLO collection cycle. It lets operators distinguish device failures from a worker run that did not execute.

### MeasurementBatch

- `id`
- `client_batch_id`
- `created_at`
- `operator_name`
- `measured_at`
- `note`
- `source`: `web_bulk_input`

`MeasurementBatch` groups one frontend bulk-save operation. Rack, device, and phase measurements remain independent records.

### RackMeasurement

- `id`
- `batch_id`
- `rack_id`
- `measurement_point`: `rack_input`, `rack_pdu_input`, or `other`
- `watts`
- `voltage`
- `amp`
- `power_factor`
- `voltage_source`: `default`, `manual`, or `meter`
- `power_factor_source`: `default`, `manual`, or `meter`
- `quality`: `measured_watts`, `calculated_with_measured_pf`, or `calculated_with_default_pf`
- `measured_at`
- `operator_name`
- `note`

### ManualDevicePower

- `id`
- `batch_id`
- `device_id`
- `measurement_point`: `device_power_cord`, `rack_pdu_outlet`, or `other`
- `value_type`: `measured`, `rated`, or `estimated`
- `watts`
- `voltage`
- `amp`
- `power_factor`
- `voltage_source`: `default`, `manual`, or `meter`
- `power_factor_source`: `default`, `manual`, or `meter`
- `quality`: `measured_watts`, `calculated_with_measured_pf`, `calculated_with_default_pf`, `estimated`, or `rated`
- `measured_at`
- `operator_name`
- `note`

Device measured values keep history. Rated and estimated values keep only the latest value per device.

### PhaseMainMeasurement

- `id`
- `batch_id`
- `phase`: `R`, `S`, or `T`
- `measurement_point`: `phase_branch`, `panel_main`, or `other`
- `amp`
- `voltage_default_used`
- `power_factor_default_used`
- `voltage_source`: `default`, `manual`, or `meter`
- `power_factor_source`: `default`, `manual`, or `meter`
- `quality`: `calculated_with_measured_pf` or `calculated_with_default_pf`
- `calculated_watts`
- `measured_at`
- `operator_name`
- `note`

### Threshold

- `id`
- `target_type`: `device`, `rack`, `phase`, or `overall`
- `target_id`
- `basis`
- `warning_watts`
- `critical_watts`
- `trigger_count`
- `clear_count`
- `active`

Defaults:

- `trigger_count=1`
- `clear_count=2`

### ThresholdState

- `threshold_id`
- `current_state`: `normal`, `warning`, or `critical`
- `consecutive_trigger_count`
- `consecutive_clear_count`
- `last_evaluated_at`

### PowerAggregate

- `entity_type`: `device`, `rack`, `phase`, or `overall`
- `entity_id`
- `source_type`: `representative`, `ilo`, `rack_measured`, `device_manual`, or `phase_main`
- `period`: `hourly`, `daily`, or `monthly`
- `period_start`
- `avg_watts`
- `min_watts`
- `max_watts`
- `sample_count`
- `coverage_percent`
- `unknown_count`
- `stale_count`

### RackMonthlyKwh

- `rack_id`
- `month`
- `actual_kwh`
- `estimated_kwh`
- `coverage_percent`
- `estimated_hours`
- `carry_forward_max_hours`
- `needs_recalculation`

### RackHourlyKwh

- `rack_id`
- `hour_start`
- `actual_kwh`
- `estimated_kwh`
- `basis_source`: `rack_measured`, `device_sum`, or `carry_forward`
- `coverage_state`: `actual`, `estimated`, or `missing`

Monthly kWh is derived from `RackHourlyKwh` rows.

## 8. Representative Power Rules

Freshness defaults:

- iLO sample freshness: 30 minutes.
- Rack measurement freshness: 24 hours.
- Manual measured device power freshness: 30 days.
- Estimated and rated values do not expire automatically, but their quality remains `estimated` or `rated`.

Stale values must be displayed as stale and must not be presented as fresh current measurements.

### Device Representative Power

Priority:

```text
1. latest successful iLO average watts
2. latest manual measured watts
3. latest estimated watts
4. rated watts
5. null
```

Only fresh iLO and fresh manual measured values can satisfy priorities 1 and 2. If a value is stale, it can be shown in history but must not be used as a fresh representative value unless the query explicitly requests stale fallback.

### Rack Representative Power

Priority:

```text
1. latest rack measured watts
2. sum of device values in rack:
   - for devices with latest successful iLO: latest iLO average
   - otherwise: device representative manual fallback
3. null
```

Rack representative power must not silently include inactive devices unless the query explicitly includes inactive inventory for historical review.

Rack summaries must include:

- `known_device_count`
- `unknown_device_count`
- `stale_device_count`
- `coverage_percent`
- `representative_source`: `rack_measured`, `device_sum`, or `unknown`

### Phase Power

Display both:

- Latest phase-main measured watts.
- Sum of rack representative watts for racks assigned to that phase.

Also display:

- Difference between phase-main and rack-sum.
- Max phase minus min phase.
- Imbalance percent:

```text
(max_phase_watts - min_phase_watts) / average_phase_watts * 100
```

The default basis for phase thresholds is max of phase-main measured watts and rack representative sum for that phase. Users can override this per threshold.

Phase summaries must include rack coverage:

- `known_rack_count`
- `unknown_rack_count`
- `stale_rack_count`
- `coverage_percent`

### Overall Power

Display both:

- Sum of rack representative watts.
- Sum of latest R/S/T phase-main measured watts.

Default overall threshold basis:

```text
max(overall_rack_sum, overall_phase_main_sum)
```

Users can select:

- Rack representative sum.
- Phase-main sum.
- Max of both.

Overall summaries must include:

- `known_rack_count`
- `unknown_rack_count`
- `known_device_count`
- `unknown_device_count`
- `coverage_percent`

## 9. kWh Rules

Monthly rack kWh is based on rack representative power.

For each rack:

```text
hourly_actual_kwh = hourly_avg_representative_watts / 1000
monthly_actual_kwh = sum(hourly_actual_kwh for hours with actual data)
```

Estimated kWh may carry forward the previous representative value when an hour has no actual data.

Rules:

- `carry_forward_max_hours` default is 6 hours.
- Carry-forward must stop after the cap.
- Carry-forward hours contribute to `estimated_kwh`, not `actual_kwh`.
- `coverage_percent = hours_with_actual_representative_data / total_hours_in_month * 100`.

The UI must display `actual_kwh`, `estimated_kwh`, and `coverage_percent` so estimated usage is not mistaken for fully measured usage.

Hourly kWh rows must preserve calculation basis:

```text
basis_source = rack_measured | device_sum | carry_forward
coverage_state = actual | estimated | missing
```

Monthly kWh must be calculated from hourly rows, not directly from raw measurements. This makes recalculation deterministic and allows the UI to explain how much of the monthly value is measured versus estimated.

## 10. Manual Input Rules

Manual entry supports:

- Rack measurements.
- Device manual power values.
- R/S/T phase-main amp measurements.

Frontend UX:

- One bulk input screen.
- Rack, device, and phase sections.
- Empty cells are ignored and do not overwrite existing data.
- Operator name is required.
- Note is optional.
- Measurement time defaults to current time and can be edited.

API shape:

- Create a `MeasurementBatch`.
- Send rack, device, and phase entries to separate type-specific bulk APIs using the same `batch_id`.

Manual measurement update/delete:

- Measurements can be updated.
- Measurements can be physically deleted.
- When a manual measurement is updated or deleted, the affected month is marked for recalculation.

Validation:

```text
if amp, voltage, power_factor, and watts are all provided:
    calculated_watts = amp * voltage * power_factor
    tolerance = max(watts * 0.10, 100W)
    if abs(watts - calculated_watts) > tolerance:
        return warning
        save only when confirmed=true
```

Measurement quality assignment:

- If watts is directly entered from a meter, use `measured_watts`.
- If watts is calculated from amp, voltage, and a measured/manual power factor, use `calculated_with_measured_pf`.
- If watts is calculated using default power factor, use `calculated_with_default_pf`.
- If the value is an operational estimate, use `estimated`.
- If the value is a nameplate/spec value, use `rated`.

## 11. iLO Collection

Collection interval:

- Every 15 minutes.

Collected value:

- `PowerMetrics.AverageConsumedWatts` or equivalent profile-specific average power field.

Authentication:

- Try Redfish Session first.
- Fallback to Basic Auth.
- Store the successful auth method per sample.

iLO versions:

- iLO 4, 5, and 6 are expected.
- Device registration requires manually selecting the iLO collection profile.
- A bad profile results in collection failure only. The UI does not infer or suggest profile mismatch.

Connection behavior:

- Timeout is configurable, default 10 seconds.
- TLS verification is configurable, default false.
- Initial version has no concurrency limit.

Failure behavior:

- Store failed collection row with `average_watts=null`.
- Show failure/null on screen.
- Store detailed error only in server logs.
- Never log iLO password or token.

## 12. Worker Jobs

### iLO Collect Job

- Runs every 15 minutes.
- Collects active iLO-enabled devices.
- Creates one `CollectionRun` per cycle.
- Stores success or failure `IloPowerSample`.
- Updates `CollectionRun` counts and final status.

### Aggregate Job

- Builds hourly, daily, and monthly `PowerAggregate` rows.
- Aggregates both representative power and source-specific power.
- Uses upsert semantics keyed by `entity_type`, `entity_id`, `source_type`, `period`, and `period_start`.

### Rack kWh Job

- Calculates monthly rack actual and estimated kWh.
- Creates/upserts hourly `RackHourlyKwh` rows first.
- Applies carry-forward cap.
- Updates coverage percent.
- Upserts monthly `RackMonthlyKwh` by `rack_id` and `month`.

### Threshold Evaluation Job

- Evaluates device, rack, phase, and overall thresholds.
- Applies threshold-specific trigger and clear counts.
- Updates `ThresholdState`.
- Initial version only displays alerts in the dashboard.

### Recalculation Job

- Processes months marked `needs_recalculation`.
- Rebuilds affected aggregates and kWh.

### Idempotency Rules

- Worker jobs must be safe to rerun.
- Aggregates must be upserted, not blindly inserted.
- Monthly kWh must be upserted by rack and month.
- Hourly kWh must be upserted by rack and hour.
- iLO samples must be associated with a `CollectionRun`.
- Manual recalculation can be executed multiple times with the same final result.

Manual triggers:

- `POST /ilo/collect`
- `POST /aggregates/recalculate`

## 13. API Design

API paths use kebab-case and plural nouns.

### Overview

- `GET /overview`

Returns:

- Rack cards.
- Overall summary.
- R/S/T summary.
- Active threshold states.
- Coverage and unknown/stale counts.

### Racks

- `GET /racks`
- `POST /racks`
- `GET /racks/{rack_id}`
- `PATCH /racks/{rack_id}`
- `DELETE /racks/{rack_id}`
- `GET /racks/{rack_id}/summary`
- `GET /racks/{rack_id}/trend`
- `GET /racks/{rack_id}/devices`
- `GET /racks/{rack_id}/measurements`

`DELETE /racks/{rack_id}` sets `active=false`.

### Devices

- `GET /devices`
- `POST /devices`
- `GET /devices/{device_id}`
- `PATCH /devices/{device_id}`
- `DELETE /devices/{device_id}`
- `GET /devices/{device_id}/power`

`DELETE /devices/{device_id}` sets `active=false`.

### Measurement Batches

- `POST /measurement-batches`
- `GET /measurement-batches`
- `GET /measurement-batches/{batch_id}`

### Measurements

- `POST /rack-measurements/bulk`
- `PATCH /rack-measurements/{measurement_id}`
- `DELETE /rack-measurements/{measurement_id}`
- `POST /device-power-measurements/bulk`
- `PATCH /device-power-measurements/{measurement_id}`
- `DELETE /device-power-measurements/{measurement_id}`
- `POST /phase-main-measurements/bulk`
- `PATCH /phase-main-measurements/{measurement_id}`
- `DELETE /phase-main-measurements/{measurement_id}`

### iLO

- `GET /ilo/status`
- `POST /ilo/collect`
- `GET /ilo/samples`
- `GET /ilo/collection-runs`
- `GET /ilo/collection-runs/{collection_run_id}`

### Settings

- `GET /settings/ilo-credential`
- `PUT /settings/ilo-credential`
- `GET /settings/power-defaults`
- `PUT /settings/power-defaults`

### Thresholds

- `GET /thresholds`
- `POST /thresholds`
- `PATCH /thresholds/{threshold_id}`
- `DELETE /thresholds/{threshold_id}`
- `GET /threshold-states`

### Phases

- `GET /phases/summary`
- `GET /phases/{phase}/measurements`

### Aggregates and kWh

- `GET /aggregates`
- `POST /aggregates/recalculate`
- `GET /kwh/racks/monthly`

### Excel Import

- `GET /imports/template`
- `POST /imports/excel`
- `GET /imports/logs`

Excel import:

- Uses a fixed template.
- Has a rack sheet and a device sheet.
- Matches existing records by unique names.
- Supports create/update only.
- Does not delete.
- Does not import thresholds.
- Does not store the original file.
- Stores processing result logs.
- Does not require operator name.

Standard error response:

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Invalid measurement value",
    "details": {}
  }
}
```

## 14. Frontend Scope

Initial frontend is simple and functional.

Pages:

- Home overview.
- Rack detail.
- Bulk measurement input.
- Inventory management.
- Threshold management.
- Settings.

Home:

- Report/monitoring style.
- Rack card grid is primary.
- Rack card shows:
  - Rack name.
  - Representative watts.
  - State.
  - R/S/T phase.
  - Monthly kWh.
- Card status mode can switch between threshold state and data-confidence state.
- Clicking a card opens rack detail.

Rack detail:

- Tabs:
  - Power trend.
  - Device list.
  - Measurement history.
- Default trend period is last 7 days.
- Default trend line is representative power only.

Phase screen:

- Shows phase-main watts.
- Shows rack representative sum per phase.
- Shows difference, W imbalance, and imbalance percent.
- Shows known, unknown, and stale rack counts.

Dashboard refresh:

- Manual refresh.
- Auto refresh every 1 minute.

## 15. Time and Numeric Rules

Time:

- Only timezone-aware datetimes are allowed in application code.
- Store DB timestamps in UTC.
- Display local time in the frontend.

Decimal:

- Use `Decimal` for amp, volt, power factor, watts, and kWh.

Rounding:

- Store watts and kWh with Decimal precision.
- Display watts rounded to 1 decimal place unless integer display is requested by the screen.
- Display kWh rounded to 3 decimal places.
- Internal calculations must not round intermediate values unless persisted aggregate precision requires it.

## 16. Code Conventions

Python:

- Type hints are required.
- Router must not access the database directly.
- Use `router -> service -> repository`.
- Business logic belongs in services.
- Calculation functions should be pure functions where possible.
- Only timezone-aware datetimes are allowed.
- Store DB datetimes in UTC.
- Use `Decimal` for amp, volt, power factor, watts, and kWh.
- Rounding policy must be explicit.
- Convert external API failures into typed exceptions.
- Never log iLO passwords or tokens.

Naming:

- DB tables: snake_case plural.
- Python functions and variables: snake_case.
- Pydantic schemas: PascalCase.
- API paths: kebab-case plus plural nouns.

Testing:

- Prioritize unit tests for calculation logic.
- Test representative power priority.
- Test manual input tolerance.
- Test kWh actual/estimated/carry-forward cap.
- Test threshold trigger/clear behavior.
- Test iLO client through mocks.

Suggested layout:

```text
backend/
  app/
    api/
    core/
    integrations/ilo/
    models/
    repositories/
    schemas/
    services/
    workers/
  tests/
frontend/
  src/
    api/
    components/
    pages/
    types/
```

## 17. Implementation Planning Notes

These are implementation choices, not unresolved requirements:

- Choose APScheduler or a simple worker loop during implementation planning.
- Choose exact SQLAlchemy relationship loading strategy during implementation.
- Decide whether frontend all-save button calls the three measurement bulk APIs sequentially or concurrently.
- Define exact Excel template columns in implementation plan.
- Define iLO profile path mappings during implementation with tests.
