"""Schema snapshot v8: same-Run durable, sequential team orchestration."""

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    ForeignKeyConstraint,
    Integer,
    MetaData,
    String,
    Table,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from . import schema_v7 as v7

metadata = MetaData(naming_convention=v7.metadata.naming_convention)
for original in v7.metadata.tables.values():
    original.to_metadata(metadata)
for name, original in vars(v7).items():
    if isinstance(original, Table):
        globals()[name] = metadata.tables[original.name]


def base():
    return [
        Column("org_id", Uuid, nullable=False),
        Column("id", Uuid, primary_key=True),
        Column("created_at", DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")),
        UniqueConstraint("org_id", "id"),
    ]


run_teams = Table(
    "aio_run_teams",
    metadata,
    *base(),
    Column("run_id", Uuid, nullable=False),
    Column("stage", String(24), nullable=False),
    Column("current_step", Integer, nullable=False, server_default="0"),
    Column("initial_checkpoint_seq", Integer, nullable=False),
    Column("plan_checkpoint_seq", Integer),
    Column("plan", JSONB),
    Column("plan_digest", String(64)),
    Column("finished_at", DateTime(timezone=True)),
    UniqueConstraint("org_id", "run_id"),
    ForeignKeyConstraint(["org_id", "run_id"], ["aio_runs.org_id", "aio_runs.id"]),
    ForeignKeyConstraint(
        ["org_id", "run_id", "initial_checkpoint_seq"],
        ["aio_checkpoints.org_id", "aio_checkpoints.run_id", "aio_checkpoints.seq"],
    ),
    ForeignKeyConstraint(
        ["org_id", "run_id", "plan_checkpoint_seq"],
        ["aio_checkpoints.org_id", "aio_checkpoints.run_id", "aio_checkpoints.seq"],
    ),
    CheckConstraint("stage IN ('planning','step','synthesis','completed','stopped')", name="stage"),
    CheckConstraint("current_step BETWEEN 0 AND 6", name="cursor"),
    CheckConstraint(
        "(plan IS NULL) = (plan_digest IS NULL) AND (plan IS NULL) = (plan_checkpoint_seq IS NULL)", name="plan_binding"
    ),
)
run_steps = Table(
    "aio_run_steps",
    metadata,
    *base(),
    Column("run_id", Uuid, nullable=False),
    Column("ordinal", Integer, nullable=False),
    Column("definition", JSONB, nullable=False),
    Column("definition_digest", String(64), nullable=False),
    Column("state", String(24), nullable=False, server_default="pending"),
    Column("input_checkpoint_seq", Integer),
    Column("output_checkpoint_seq", Integer),
    Column("started_round", Integer),
    Column("finished_round", Integer),
    Column("result", JSONB),
    Column("started_at", DateTime(timezone=True)),
    Column("finished_at", DateTime(timezone=True)),
    UniqueConstraint("org_id", "run_id", "id"),
    UniqueConstraint("org_id", "run_id", "ordinal"),
    ForeignKeyConstraint(["org_id", "run_id"], ["aio_run_teams.org_id", "aio_run_teams.run_id"]),
    ForeignKeyConstraint(
        ["org_id", "run_id", "input_checkpoint_seq"],
        ["aio_checkpoints.org_id", "aio_checkpoints.run_id", "aio_checkpoints.seq"],
    ),
    ForeignKeyConstraint(
        ["org_id", "run_id", "output_checkpoint_seq"],
        ["aio_checkpoints.org_id", "aio_checkpoints.run_id", "aio_checkpoints.seq"],
    ),
    CheckConstraint("ordinal BETWEEN 1 AND 6", name="ordinal"),
    CheckConstraint(
        "state IN ('pending','running','succeeded','failed','denied','skipped','cancelled','timed_out','recovery_required')",
        name="state",
    ),
    CheckConstraint("started_round IS NULL OR started_round BETWEEN 0 AND 32", name="start_round"),
    CheckConstraint("finished_round IS NULL OR finished_round BETWEEN started_round AND 32", name="finish_round"),
)

for name in ("aio_model_calls", "aio_invocations"):
    table = metadata.tables[name]
    table.append_column(Column("team_step_id", Uuid))
    table.append_constraint(
        ForeignKeyConstraint(
            ["org_id", "run_id", "team_step_id"],
            ["aio_run_steps.org_id", "aio_run_steps.run_id", "aio_run_steps.id"],
            name="fk_" + name + "_team_step",
        )
    )
metadata.tables["aio_model_calls"].append_column(Column("team_stage", String(24)))
metadata.tables["aio_model_calls"].append_constraint(
    CheckConstraint(
        "(team_stage IS NULL AND team_step_id IS NULL) OR "
        "(team_stage IS NOT NULL AND ((team_stage IN ('planning','synthesis') AND team_step_id IS NULL) OR "
        "(team_stage = 'step' AND team_step_id IS NOT NULL)))",
        name="team_binding",
    )
)

BOOTSTRAP_TABLES = v7.BOOTSTRAP_TABLES
TENANT_TABLES = tuple(t for t in metadata.tables.values() if t.name not in BOOTSTRAP_TABLES)
