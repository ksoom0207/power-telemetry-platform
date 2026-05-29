"""create initial schema

Revision ID: 20260529_0001
Revises:
Create Date: 2026-05-29 00:00:00

"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "20260529_0001"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def timestamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    ]


def upgrade() -> None:
    op.create_table(
        "racks",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("phase", sa.String(length=1), nullable=False),
        sa.Column("voltage", sa.Numeric(10, 3), nullable=False),
        sa.Column("circuit_name", sa.String(length=255), nullable=True),
        sa.Column("capacity_amp", sa.Numeric(10, 3), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False),
        *timestamps(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_table(
        "collection_runs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("triggered_by", sa.String(length=30), nullable=False),
        sa.Column("total_targets", sa.Integer(), nullable=False),
        sa.Column("success_count", sa.Integer(), nullable=False),
        sa.Column("failed_count", sa.Integer(), nullable=False),
        *timestamps(),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "measurement_batches",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("client_batch_id", sa.String(length=64), nullable=False),
        sa.Column("operator_name", sa.String(length=255), nullable=False),
        sa.Column("measured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("note", sa.String(length=1000), nullable=True),
        sa.Column("source", sa.String(length=50), nullable=False),
        *timestamps(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("client_batch_id"),
    )
    op.create_table(
        "ilo_credential_settings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("username", sa.String(length=255), nullable=False),
        sa.Column("encrypted_password", sa.String(length=2048), nullable=False),
        sa.Column("auth_mode", sa.String(length=50), nullable=False),
        sa.Column("tls_verify", sa.Boolean(), nullable=False),
        sa.Column("timeout_seconds", sa.Integer(), nullable=False),
        *timestamps(),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "power_default_settings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("default_voltage", sa.Numeric(10, 3), nullable=False),
        sa.Column("default_power_factor", sa.Numeric(6, 4), nullable=False),
        sa.Column("carry_forward_max_hours", sa.Integer(), nullable=False),
        *timestamps(),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "thresholds",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("target_type", sa.String(length=30), nullable=False),
        sa.Column("target_id", sa.Integer(), nullable=True),
        sa.Column("basis", sa.String(length=50), nullable=False),
        sa.Column("warning_watts", sa.Numeric(14, 3), nullable=True),
        sa.Column("critical_watts", sa.Numeric(14, 3), nullable=True),
        sa.Column("trigger_count", sa.Integer(), nullable=False),
        sa.Column("clear_count", sa.Integer(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        *timestamps(),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "import_logs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("file_name", sa.String(length=255), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_count", sa.Integer(), nullable=False),
        sa.Column("updated_count", sa.Integer(), nullable=False),
        sa.Column("failed_count", sa.Integer(), nullable=False),
        sa.Column("failure_summary", sa.String(length=4000), nullable=True),
        *timestamps(),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "power_aggregates",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("entity_type", sa.String(length=30), nullable=False),
        sa.Column("entity_id", sa.Integer(), nullable=True),
        sa.Column("source_type", sa.String(length=50), nullable=False),
        sa.Column("period", sa.String(length=20), nullable=False),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("avg_watts", sa.Numeric(14, 3), nullable=True),
        sa.Column("min_watts", sa.Numeric(14, 3), nullable=True),
        sa.Column("max_watts", sa.Numeric(14, 3), nullable=True),
        sa.Column("sample_count", sa.Integer(), nullable=False),
        sa.Column("coverage_percent", sa.Numeric(6, 3), nullable=False),
        sa.Column("unknown_count", sa.Integer(), nullable=False),
        sa.Column("stale_count", sa.Integer(), nullable=False),
        *timestamps(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("entity_type", "entity_id", "source_type", "period", "period_start"),
    )
    op.create_table(
        "rack_hourly_kwh",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("rack_id", sa.Integer(), nullable=False),
        sa.Column("hour_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actual_kwh", sa.Numeric(14, 6), nullable=False),
        sa.Column("estimated_kwh", sa.Numeric(14, 6), nullable=False),
        sa.Column("basis_source", sa.String(length=30), nullable=False),
        sa.Column("coverage_state", sa.String(length=30), nullable=False),
        *timestamps(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("rack_id", "hour_start"),
    )
    op.create_table(
        "rack_monthly_kwh",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("rack_id", sa.Integer(), nullable=False),
        sa.Column("month", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actual_kwh", sa.Numeric(14, 6), nullable=False),
        sa.Column("estimated_kwh", sa.Numeric(14, 6), nullable=False),
        sa.Column("coverage_percent", sa.Numeric(6, 3), nullable=False),
        sa.Column("estimated_hours", sa.Numeric(10, 3), nullable=False),
        sa.Column("carry_forward_max_hours", sa.Integer(), nullable=False),
        sa.Column("needs_recalculation", sa.Boolean(), nullable=False),
        *timestamps(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("rack_id", "month"),
    )
    op.create_table(
        "devices",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("rack_id", sa.Integer(), nullable=False),
        sa.Column("device_type", sa.String(length=50), nullable=False),
        sa.Column("u_position_start", sa.Integer(), nullable=True),
        sa.Column("u_position_end", sa.Integer(), nullable=True),
        sa.Column("has_ilo", sa.Boolean(), nullable=False),
        sa.Column("ilo_host", sa.String(length=255), nullable=True),
        sa.Column("ilo_profile", sa.String(length=50), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False),
        *timestamps(),
        sa.ForeignKeyConstraint(["rack_id"], ["racks.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_table(
        "threshold_states",
        sa.Column("threshold_id", sa.Integer(), nullable=False),
        sa.Column("current_state", sa.String(length=30), nullable=False),
        sa.Column("consecutive_trigger_count", sa.Integer(), nullable=False),
        sa.Column("consecutive_clear_count", sa.Integer(), nullable=False),
        sa.Column("last_evaluated_at", sa.DateTime(timezone=True), nullable=True),
        *timestamps(),
        sa.ForeignKeyConstraint(["threshold_id"], ["thresholds.id"]),
        sa.PrimaryKeyConstraint("threshold_id"),
    )
    op.create_table(
        "ilo_power_samples",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("device_id", sa.Integer(), nullable=False),
        sa.Column("collection_run_id", sa.Integer(), nullable=False),
        sa.Column("measured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("average_watts", sa.Numeric(14, 3), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("auth_method_used", sa.String(length=30), nullable=True),
        sa.Column("profile_used", sa.String(length=50), nullable=True),
        sa.Column("quality", sa.String(length=50), nullable=False),
        *timestamps(),
        sa.ForeignKeyConstraint(["collection_run_id"], ["collection_runs.id"]),
        sa.ForeignKeyConstraint(["device_id"], ["devices.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "rack_measurements",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("batch_id", sa.Integer(), nullable=False),
        sa.Column("rack_id", sa.Integer(), nullable=False),
        sa.Column("measurement_point", sa.String(length=50), nullable=False),
        sa.Column("watts", sa.Numeric(14, 3), nullable=False),
        sa.Column("voltage", sa.Numeric(10, 3), nullable=True),
        sa.Column("amp", sa.Numeric(10, 3), nullable=True),
        sa.Column("power_factor", sa.Numeric(6, 4), nullable=True),
        sa.Column("voltage_source", sa.String(length=30), nullable=False),
        sa.Column("power_factor_source", sa.String(length=30), nullable=False),
        sa.Column("quality", sa.String(length=50), nullable=False),
        sa.Column("measured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("operator_name", sa.String(length=255), nullable=False),
        sa.Column("note", sa.String(length=1000), nullable=True),
        *timestamps(),
        sa.ForeignKeyConstraint(["batch_id"], ["measurement_batches.id"]),
        sa.ForeignKeyConstraint(["rack_id"], ["racks.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "manual_device_powers",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("batch_id", sa.Integer(), nullable=True),
        sa.Column("device_id", sa.Integer(), nullable=False),
        sa.Column("measurement_point", sa.String(length=50), nullable=False),
        sa.Column("value_type", sa.String(length=30), nullable=False),
        sa.Column("watts", sa.Numeric(14, 3), nullable=False),
        sa.Column("voltage", sa.Numeric(10, 3), nullable=True),
        sa.Column("amp", sa.Numeric(10, 3), nullable=True),
        sa.Column("power_factor", sa.Numeric(6, 4), nullable=True),
        sa.Column("voltage_source", sa.String(length=30), nullable=False),
        sa.Column("power_factor_source", sa.String(length=30), nullable=False),
        sa.Column("quality", sa.String(length=50), nullable=False),
        sa.Column("measured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("operator_name", sa.String(length=255), nullable=False),
        sa.Column("note", sa.String(length=1000), nullable=True),
        *timestamps(),
        sa.ForeignKeyConstraint(["batch_id"], ["measurement_batches.id"]),
        sa.ForeignKeyConstraint(["device_id"], ["devices.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "phase_main_measurements",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("batch_id", sa.Integer(), nullable=False),
        sa.Column("phase", sa.String(length=1), nullable=False),
        sa.Column("measurement_point", sa.String(length=50), nullable=False),
        sa.Column("amp", sa.Numeric(10, 3), nullable=False),
        sa.Column("voltage_default_used", sa.Numeric(10, 3), nullable=False),
        sa.Column("power_factor_default_used", sa.Numeric(6, 4), nullable=False),
        sa.Column("voltage_source", sa.String(length=30), nullable=False),
        sa.Column("power_factor_source", sa.String(length=30), nullable=False),
        sa.Column("quality", sa.String(length=50), nullable=False),
        sa.Column("calculated_watts", sa.Numeric(14, 3), nullable=False),
        sa.Column("measured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("operator_name", sa.String(length=255), nullable=False),
        sa.Column("note", sa.String(length=1000), nullable=True),
        *timestamps(),
        sa.ForeignKeyConstraint(["batch_id"], ["measurement_batches.id"]),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("phase_main_measurements")
    op.drop_table("manual_device_powers")
    op.drop_table("rack_measurements")
    op.drop_table("ilo_power_samples")
    op.drop_table("threshold_states")
    op.drop_table("devices")
    op.drop_table("rack_monthly_kwh")
    op.drop_table("rack_hourly_kwh")
    op.drop_table("power_aggregates")
    op.drop_table("import_logs")
    op.drop_table("thresholds")
    op.drop_table("power_default_settings")
    op.drop_table("ilo_credential_settings")
    op.drop_table("measurement_batches")
    op.drop_table("collection_runs")
    op.drop_table("racks")
