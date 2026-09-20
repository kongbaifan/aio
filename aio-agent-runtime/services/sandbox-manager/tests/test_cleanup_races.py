"""Real Docker deletion races: cleanup must confirm absence, never merely suppress errors."""

from concurrent.futures import ThreadPoolExecutor
import threading

import pytest
from requests import Response
from docker.errors import APIError, NotFound
from docker.models.containers import Container
from docker.models.volumes import Volume

from aio_sandbox_manager.contracts import ManagerError
import aio_sandbox_manager.docker_backend as backend_module
from test_docker_isolation import cell


def conflict():
    response = Response()
    response.status_code = 409
    return APIError("Synthetic concurrent deletion", response=response)


def test_delete_conflict_requires_and_accepts_independently_confirmed_absence(managed, monkeypatch):
    manager, _, profile = managed
    spec = cell(profile)
    ready = manager.ensure(spec)
    original = Container.remove
    raced = []

    def deleted_elsewhere(container, *args, **kwargs):
        if container.id == ready["container_id"] and not raced:
            raced.append(True)
            original(container, *args, **kwargs)
            raise conflict()
        return original(container, *args, **kwargs)

    monkeypatch.setattr(Container, "remove", deleted_elsewhere)
    assert manager.stop(spec)["state"] == "destroyed" and raced == [True]
    assert manager.backend.checked(spec, ready["container_id"]) is None
    with pytest.raises(NotFound):
        manager.backend.client.volumes.get(manager.backend.volume_name(spec))


def test_cleanup_is_serialized_per_binding_without_blocking_another_cell(managed, monkeypatch):
    manager, _, profile = managed
    spec, other = cell(profile), cell(profile)
    ready = manager.ensure(spec)
    manager.ensure(other)
    backend = manager.backend
    original_remove, original_lock = Container.remove, backend._cleanup_lock
    entered, release, peer_attempted = threading.Event(), threading.Event(), threading.Event()
    local = threading.local()
    deletes = []

    def observed_lock(binding):
        lock = original_lock(binding)
        if binding == spec.binding_id and getattr(local, "peer", False):
            peer_attempted.set()
        return lock

    def held_remove(container, *args, **kwargs):
        if container.id == ready["container_id"]:
            deletes.append(container.id)
            entered.set()
            assert release.wait(5), "Synthetic removal barrier was not released"
        return original_remove(container, *args, **kwargs)

    def clean(peer):
        local.peer = peer
        return manager.stop(spec)

    monkeypatch.setattr(backend, "_cleanup_lock", observed_lock)
    monkeypatch.setattr(Container, "remove", held_remove)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(clean, False)
        try:
            assert entered.wait(3)
            second = pool.submit(clean, True)
            assert peer_attempted.wait(3)
            assert not second.done() and len(deletes) == 1
            # Not a global lock and not an execution/RPC lock.
            assert manager.stop(other)["state"] == "destroyed"
        finally:
            release.set()
        assert first.result(timeout=5)["state"] == second.result(timeout=5)["state"] == "destroyed"
    assert len(deletes) == 1


@pytest.mark.parametrize("mode", ["finishes", "stuck", "running"])
def test_removal_conflict_observes_owned_progress_without_retrying_delete(managed, monkeypatch, mode):
    manager, _, profile = managed
    spec = cell(profile)
    ready = manager.ensure(spec)
    backend = manager.backend
    original_remove, original_checked = Container.remove, backend.checked
    error = conflict()
    deletes, observations = [], []

    def in_progress(container, *args, **kwargs):
        if container.id == ready["container_id"]:
            deletes.append(container.id)
            raise error
        return original_remove(container, *args, **kwargs)

    def observe(target, container_id):
        current = original_checked(target, container_id)
        if current is not None and deletes:
            if mode == "finishes" and observations:
                original_remove(current, force=True, v=True)
                return original_checked(target, container_id)
            current.attrs["State"]["Status"] = "removing"
            current.attrs["State"]["Running"] = mode == "running"
            observations.append(True)
        return current

    with monkeypatch.context() as patch:
        patch.setattr(Container, "remove", in_progress)
        patch.setattr(backend, "checked", observe)
        if mode == "stuck":
            patch.setattr(backend_module, "CLEANUP_CONFIRM_SECONDS", 0)
        if mode == "finishes":
            assert manager.stop(spec)["state"] == "destroyed"
        elif mode == "stuck":
            with pytest.raises(ManagerError) as caught:
                manager.stop(spec)
            assert caught.value.code == "CLEANUP_UNCONFIRMED"
        else:
            with pytest.raises(APIError) as caught:
                manager.stop(spec)
            assert caught.value is error
        assert len(deletes) == 1 and observations
        if mode != "finishes":
            assert manager.journal.cell(spec.binding_id)["state"] != "destroyed"
    assert manager.stop(spec)["state"] == "destroyed"


def test_concurrent_owned_container_delete_is_idempotent_after_stop(managed, monkeypatch):
    manager, _, profile = managed
    spec = cell(profile)
    ready = manager.ensure(spec)
    backend = manager.backend
    original_stop = backend.stop

    def stopped_elsewhere(target, container_id):
        original_stop(target, container_id)
        # A second cleanup actor actually removes this exact, already checked
        # container before the first actor reaches its own DELETE request.
        backend.client.containers.get(container_id).remove(force=True, v=True)

    monkeypatch.setattr(backend, "stop", stopped_elsewhere)
    assert manager.stop(spec)["state"] == "destroyed"
    assert manager.journal.cell(spec.binding_id)["state"] == "destroyed"
    assert backend.checked(spec, ready["container_id"]) is None
    with pytest.raises(NotFound):
        backend.client.volumes.get(backend.volume_name(spec))


def test_concurrent_owned_volume_delete_is_confirmed_idempotently(managed, monkeypatch):
    manager, _, profile = managed
    spec = cell(profile)
    ready = manager.ensure(spec)
    backend = manager.backend
    name = backend.volume_name(spec)
    original = Volume.remove
    raced = []

    def removed_elsewhere(volume, **kwargs):
        if volume.name == name and not raced:
            raced.append(True)
            original(volume, **kwargs)
        return original(volume, **kwargs)

    monkeypatch.setattr(Volume, "remove", removed_elsewhere)
    assert manager.stop(spec)["state"] == "destroyed" and raced == [True]
    assert manager.stop(spec)["state"] == "destroyed"
    assert backend.checked(spec, ready["container_id"]) is None
    with pytest.raises(NotFound):
        backend.client.volumes.get(name)


@pytest.mark.parametrize("stage", ["reload", "kill", "unpause"])
def test_owned_container_disappearing_during_stop_is_not_a_runtime_failure(managed, monkeypatch, stage):
    manager, _, profile = managed
    spec = cell(profile)
    ready = manager.ensure(spec)
    backend = manager.backend
    if stage == "unpause":
        backend.checked(spec, ready["container_id"]).pause()
    original = getattr(Container, stage)
    remove = Container.remove
    raced = []

    def disappeared(container, *args, **kwargs):
        if container.id == ready["container_id"] and not raced:
            raced.append(True)
            if stage == "unpause":
                original(container, *args, **kwargs)
            remove(container, force=True, v=True)
        return original(container, *args, **kwargs)

    monkeypatch.setattr(Container, stage, disappeared)
    assert manager.stop(spec)["state"] == "destroyed" and raced == [True]
    assert manager.journal.cell(spec.binding_id)["state"] == "destroyed"
    assert backend.checked(spec, ready["container_id"]) is None


def test_already_unpaused_owned_container_can_still_be_stopped(managed, monkeypatch):
    manager, _, profile = managed
    spec = cell(profile)
    ready = manager.ensure(spec)
    backend = manager.backend
    backend.checked(spec, ready["container_id"]).pause()
    original = Container.unpause
    raced = []

    def unpaused_elsewhere(container, *args, **kwargs):
        if container.id == ready["container_id"] and not raced:
            raced.append(True)
            original(container, *args, **kwargs)
        return original(container, *args, **kwargs)

    monkeypatch.setattr(Container, "unpause", unpaused_elsewhere)
    assert manager.stop(spec)["state"] == "destroyed" and raced == [True]
    assert backend.checked(spec, ready["container_id"]) is None


@pytest.mark.parametrize("kind", ["container", "volume"])
@pytest.mark.parametrize("response", ["not_found_but_present", "conflict_but_present", "server_failure"])
def test_cleanup_does_not_suppress_false_absence_or_other_docker_failures(managed, monkeypatch, kind, response):
    manager, _, profile = managed
    spec = cell(profile)
    ready = manager.ensure(spec)
    backend = manager.backend
    target = Container if kind == "container" else Volume
    original = target.remove
    error = {
        "not_found_but_present": NotFound("synthetic missing response"),
        "conflict_but_present": conflict(),
        "server_failure": APIError("synthetic failure"),
    }[response]

    def failed_delete(resource, *args, **kwargs):
        matches = (
            resource.id == ready["container_id"] if kind == "container" else resource.name == backend.volume_name(spec)
        )
        if matches:
            raise error
        return original(resource, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(target, "remove", failed_delete)
        if response == "not_found_but_present":
            with pytest.raises(ManagerError) as caught:
                manager.stop(spec)
            assert caught.value.code == "CLEANUP_UNCONFIRMED"
        else:
            with pytest.raises(APIError) as caught:
                manager.stop(spec)
            assert caught.value is error
        assert manager.journal.cell(spec.binding_id)["state"] != "destroyed"
        if kind == "container":
            assert backend.checked(spec, ready["container_id"]) is not None
        else:
            assert backend.client.volumes.get(backend.volume_name(spec)) is not None
    assert manager.stop(spec)["state"] == "destroyed"
