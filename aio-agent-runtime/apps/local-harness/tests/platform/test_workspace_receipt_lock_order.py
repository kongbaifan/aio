"""Real stopped Docker writer + pending PG acknowledgement, with concurrent Worker locks."""

import pytest
from sqlalchemy import update

from app.db import schema as s
from app.platform_errors import PlatformError
from lock_fixtures import resource_before_run
from team_fixtures import rows
from test_sandbox_pipeline import pipeline as pipeline, run_pipeline
from test_workspace_handoff import scenario


@pytest.mark.parametrize("pipeline", ["team"], indirect=True)
@pytest.mark.parametrize("revoked", [False, True])
@pytest.mark.parametrize("receipt", ["checkpoint_ack", "compute_stop"])
def test_checkpoint_acknowledgement_obeys_resource_before_run_order(pipeline, monkeypatch, revoked, receipt):
    t = pipeline
    models, sink = scenario(t)
    checkpoints = t["store"].workspace

    def lost_receipt(*args):
        raise PlatformError("SYNTHETIC_RECEIPT_LOST", "Synthetic acknowledgement loss", 503)

    with monkeypatch.context() as patch:
        patch.setattr(checkpoints, "mark_acknowledged", lost_receipt)
        assert run_pipeline(t, models=models, sink=sink)["state"] == "waiting_approval"
    saved = rows(t, s.workspace_checkpoints)[0]
    old = rows(t, s.sandbox_leases)[0]
    assert saved["state"] == "ready" and not saved["manager_acknowledged"]
    assert old["state"] == "destroyed" and old["spec"] is not None
    assert not t["manager"].backend.client.containers.list(
        all=True, filters={"label": "aio.manager=" + t["manager"].journal.installation_id}
    )
    if revoked:
        with t["admin"].begin() as connection:
            connection.execute(update(s.organizations).where(s.organizations.c.id == t["org"]).values(active=False))
    callback = (
        (lambda: checkpoints.mark_acknowledged(t["org"], saved["id"]))
        if receipt == "checkpoint_ack"
        else (lambda: t["coordinator"].observed(old["spec"], "destroyed"))
    )
    resource_before_run(t, monkeypatch, t["run_id"], callback)
    assert rows(t, s.sandbox_leases)[0]["state"] == "destroyed"
    if receipt == "checkpoint_ack":
        assert rows(t, s.workspace_checkpoints)[0]["manager_acknowledged"]
        assert rows(t, s.sandbox_leases)[0]["spec"] is None
    else:
        # Observing the physical stop is not a receipt for a different lifecycle fact.
        assert not rows(t, s.workspace_checkpoints)[0]["manager_acknowledged"]
        assert rows(t, s.sandbox_leases)[0]["spec"] == old["spec"]
    assert not sink.requests
