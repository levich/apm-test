import json
import subprocess
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from apm.agent import Agent, Confirmation, Deployment, SafetyConflict, create_agent
from apm.config import Settings
from apm.db import Job, Revision, state_get
from apm.safety import SafetyCheck, check_routes, probe, warnings
from apm.worker import Worker


@pytest.fixture
def safe_agent(config, monkeypatch):
    config.safe_apply = True
    agent = Agent(config)
    previous = Deployment(revision_id=uuid.uuid4(), configuration="previous")
    agent.stage(previous)
    agent.switch(str(previous.revision_id))
    config.root_config.write_text(f'include "{config.data_dir}/current/angie.conf";\n')
    monkeypatch.setattr(agent, "command", lambda *args: "angie: [warn] conflicting server name secret ignored")
    monkeypatch.setattr(agent, "generation", lambda: 1)
    monkeypatch.setattr(agent, "reload", lambda before: 2)
    monkeypatch.setattr("apm.agent.check_routes", lambda plans: [
        {"name": p.name, "ok": True, "reason": "passed"} for p in plans
    ])
    candidate = Deployment(revision_id=uuid.uuid4(), configuration="candidate", confirmation="manual",
                           owner_id="operator", owner_session="session")
    return agent, str(previous.revision_id), candidate


def confirmation(agent, candidate):
    return Confirmation(revision_id=candidate.revision_id, token=agent.safety(private=True)["token"])


def expire(agent):
    state = agent.read_json("apply-journal.json")
    state["deadline"] = time.time() - 1
    agent.write_journal(state)


def test_defaults_enable_safety_and_validate_limits(tmp_path):
    assert Settings(_env_file=None).safe_apply
    with pytest.raises(ValueError, match="between 30 and 600"):
        Settings(_env_file=None, safe_apply_timeout=0)
    with pytest.raises(ValueError, match="reserved"):
        Settings(_env_file=None, safe_apply_checks=[{"name": "APM", "host": "localhost", "port": 80}])


def test_warnings_are_bounded_and_never_copy_secrets():
    secret = "password-token-very-private"
    rid = str(uuid.uuid4())
    output = (f'angie: [warn] conflicting server name "{secret}" in /data/revisions/{rid}/http/app.proxy.conf:42\n'
              f'angie: [warn] unknown directive value {secret}\n'
              f'angie: [warn] protocol options redefined for {secret}\n'
              f'angie: [warn] the {secret} directive is deprecated\n')
    parsed = warnings(output)
    assert secret not in json.dumps(parsed)
    assert parsed[0]["file"] == "http/app.proxy.conf" and parsed[0]["line"] == 42
    assert [p["code"] for p in parsed] == ["conflicting_server_name", "angie_warning",
                                          "protocol_options_redefined", "deprecated_directive"]
    assert len(warnings(output * 30)) == 50


def test_warning_exit_zero_is_visible_but_nonzero_is_rejected(config, monkeypatch):
    agent = Agent(config)
    candidate = Deployment(revision_id=uuid.uuid4(), configuration="events {}")
    directory = agent.stage(candidate)
    monkeypatch.setattr("apm.agent.subprocess.run", lambda *args, **kwargs: subprocess.CompletedProcess(
        args, 0, "", "angie: [warn] unknown private-secret\nconfiguration test is successful"))
    assert agent.validate(directory)[0]["code"] == "angie_warning"
    monkeypatch.setattr("apm.agent.subprocess.run", lambda *args, **kwargs: subprocess.CompletedProcess(
        args, 1, "", "angie: [warn] unknown private-secret\n[emerg] private-secret"))
    with pytest.raises(ValueError, match="exit 1") as error:
        agent.validate(directory)
    assert "private-secret" not in str(error.value)
    assert error.value.warnings[0]["code"] == "angie_warning"


def test_trial_is_idempotent_exclusive_and_keeps_credentials_private(safe_agent):
    agent, previous, candidate = safe_agent
    first = agent.apply(candidate)
    assert first["status"] == "awaiting_confirmation"
    assert agent.current() == str(candidate.revision_id)
    assert agent.apply(candidate) == first
    assert not (agent.config.data_dir / "run/receipt.json").exists()
    assert not {"token", "owner_id", "owner_session", "plans"} & first.keys()
    with pytest.raises(SafetyConflict, match="Another revision"):
        agent.apply(Deployment(revision_id=uuid.uuid4(), configuration="other"))
    with pytest.raises(SafetyConflict, match="token"):
        agent.finish_trial(Confirmation(revision_id=candidate.revision_id, token="invalid-token" * 3))
    assert agent.current() != previous


def test_explicit_confirmation_commits_and_preserves_warnings(safe_agent):
    agent, previous, candidate = safe_agent
    agent.apply(candidate)
    result = agent.finish_trial(confirmation(agent, candidate))
    assert result["status"] == "applied"
    assert result["warnings"][0]["code"] == "conflicting_server_name"
    assert agent.read_json("receipt.json")["revision_id"] == str(candidate.revision_id)
    assert not agent.read_json("apply-journal.json")
    assert not agent.safety()["halted"]
    assert agent.apply(candidate)["status"] == "applied"


@pytest.mark.parametrize("action", ["watchdog", "late_confirm", "cancel", "restart"])
def test_trial_rollback_paths_restore_files_and_halt_new_applies(safe_agent, action):
    agent, previous, candidate = safe_agent
    agent.apply(candidate)
    token = confirmation(agent, candidate)
    if action == "watchdog":
        expire(agent)
        agent.watchdog_tick()
    elif action == "late_confirm":
        expire(agent)
        with pytest.raises(SafetyConflict, match="expired"):
            agent.finish_trial(token)
    elif action == "restart":
        with agent.lock():
            agent.recover()
    else:
        agent.finish_trial(token, rollback=True)
    assert agent.current() == previous
    assert agent.safety()["status"] == "rolled_back"
    assert agent.safety()["halted"]
    assert not agent.read_json("apply-journal.json")
    assert agent.apply(candidate)["status"] == "rolled_back"
    with pytest.raises(SafetyConflict, match="halted"):
        agent.apply(Deployment(revision_id=uuid.uuid4(), configuration="new"))


def test_health_regression_rolls_back_without_browser_or_worker(safe_agent, monkeypatch):
    agent, previous, candidate = safe_agent
    agent.apply(candidate)
    monkeypatch.setattr("apm.agent.check_routes", lambda plans: [
        {"name": p.name, "ok": agent.current() == previous, "reason": "connection_error"} for p in plans
    ])
    agent.watchdog_tick()
    agent.watchdog_tick()
    assert agent.current() == str(candidate.revision_id)
    agent.watchdog_tick()
    assert agent.current() == previous
    assert agent.safety()["reason"] == "health_failed"


def test_failed_checks_cannot_be_manually_confirmed(safe_agent, monkeypatch):
    agent, _, candidate = safe_agent
    agent.apply(candidate)
    token = confirmation(agent, candidate)
    monkeypatch.setattr("apm.agent.check_routes", lambda plans: [{"name": "APM", "ok": False}])
    with pytest.raises(SafetyConflict, match="checks"):
        agent.finish_trial(token)
    assert agent.safety()["status"] == "awaiting_confirmation"


def test_missing_status_api_does_not_prevent_restoring_files(safe_agent, monkeypatch):
    agent, previous, candidate = safe_agent
    agent.apply(candidate)
    def unavailable():
        raise OSError("status API unavailable")
    monkeypatch.setattr(agent, "generation", unavailable)
    monkeypatch.setattr(agent, "reload", lambda before: 3 if before is None and agent.current() == previous else None)
    agent.finish_trial(confirmation(agent, candidate), rollback=True)
    assert agent.current() == previous
    assert agent.safety()["rollback_generation"] == 3


def test_rollback_failure_keeps_recovery_journal_and_blocks_applies(safe_agent, monkeypatch):
    agent, previous, candidate = safe_agent
    agent.apply(candidate)
    def failed(before):
        assert agent.current() == previous
        raise ValueError("reload failed")
    monkeypatch.setattr(agent, "reload", failed)
    with pytest.raises(RuntimeError, match="rollback_failed"):
        agent.finish_trial(confirmation(agent, candidate), rollback=True)
    assert agent.current() == previous
    assert agent.read_json("apply-journal.json")["status"] == "rollback_failed"
    assert agent.safety()["halted"]


def test_cold_boot_restores_pending_files_before_starting_angie(safe_agent):
    agent, previous, candidate = safe_agent
    agent.apply(candidate)
    agent.initialize()
    assert agent.current() == previous
    assert agent.read_json("apply-journal.json")["status"] == "rolling_back"


def test_interrupted_cleanup_after_commit_does_not_undo_confirmation(safe_agent):
    agent, _, candidate = safe_agent
    agent.apply(candidate)
    journal = agent.read_json("apply-journal.json")
    agent.finish_trial(confirmation(agent, candidate))
    agent.write_journal(journal)
    agent.initialize()
    assert agent.current() == str(candidate.revision_id)
    assert not agent.read_json("apply-journal.json")


def test_confirmation_and_cancel_are_serialized(safe_agent):
    agent, previous, candidate = safe_agent
    agent.apply(candidate)
    token = confirmation(agent, candidate)
    def finish(cancel):
        try:
            return agent.finish_trial(token, rollback=cancel)["status"]
        except SafetyConflict:
            return "conflict"
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(finish, [False, True]))
    assert "conflict" in results
    status = agent.safety()["status"]
    assert agent.current() == (previous if status == "rolled_back" else str(candidate.revision_id))


def test_clock_change_cannot_extend_the_trial(safe_agent):
    agent, previous, candidate = safe_agent
    agent.apply(candidate)
    state = agent.read_json("apply-journal.json")
    state.update(deadline=time.time() + 10000, deadline_monotonic=time.monotonic() - 1)
    agent.write_journal(state)
    agent.watchdog_tick()
    assert agent.current() == previous


def test_rollback_accepts_a_confirmed_bundle_from_before_revision_headers(safe_agent, monkeypatch):
    agent, previous, candidate = safe_agent
    agent.apply(candidate)
    assert not agent.read_json("apply-journal.json")["previous_has_marker"]
    def checks(plans):
        assert all(not check.revision for check in plans)
        return [{"name": check.name, "ok": True} for check in plans]
    monkeypatch.setattr("apm.agent.check_routes", checks)
    agent.finish_trial(confirmation(agent, candidate), rollback=True)
    assert agent.current() == previous


def test_confirmation_waits_for_workers_to_serve_the_candidate(safe_agent, monkeypatch):
    agent, _, candidate = safe_agent
    agent.apply(candidate)
    count = 0
    def checks(plans):
        nonlocal count
        count += 1
        return [{"name": check.name, "ok": count > 1} for check in plans]
    monkeypatch.setattr("apm.agent.check_routes", checks)
    assert agent.finish_trial(confirmation(agent, candidate))["status"] == "applied"
    assert count == 2


def test_existing_failure_is_not_a_new_regression_but_blocks_automatic_apply(safe_agent, monkeypatch):
    agent, _, candidate = safe_agent
    agent.config.safe_apply_checks = [SafetyCheck(name="existing", host="127.0.0.1", port=80)]
    monkeypatch.setattr("apm.agent.check_routes", lambda plans: [
        {"name": p.name, "ok": p.name == "APM"} for p in plans
    ])
    with pytest.raises(SafetyConflict, match="automatic"):
        agent.apply(candidate.model_copy(update={"confirmation": "automatic"}))
    result = agent.apply(candidate)
    assert result["status"] == "awaiting_confirmation"
    assert len(result["baseline"]) == 2
    assert len(result["checks"]) == 1


def test_http_checks_use_host_expected_status_body_and_candidate_marker():
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(403 if self.path == "/denied" else 200)
            self.send_header("X-APM-Revision", "new")
            self.end_headers()
            self.wfile.write(self.headers.get("Host", "").encode())
        def log_message(self, *args):
            pass
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        target = SafetyCheck(name="route", scheme="http", host="127.0.0.1", port=server.server_port,
                             host_header="app.example", body_contains="app.example", revision="new")
        assert probe(target)["ok"]
        assert not probe(target.model_copy(update={"revision": "old"}))["ok"]
        assert not probe(target.model_copy(update={"path": "/denied"}))["ok"]
        assert not probe(target.model_copy(update={"body_contains": "other-site"}))["ok"]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_stalled_dns_or_response_cannot_hold_the_controller_forever(monkeypatch):
    release = threading.Event()
    started = threading.Event()
    def stalled(check):
        started.set()
        release.wait(2)
        return {"name": check.name, "ok": True}
    monkeypatch.setattr("apm.safety.probe", stalled)
    try:
        before = time.monotonic()
        results = check_routes([SafetyCheck(name="slow", host="localhost", port=80)], timeout=0.05)
        assert started.is_set()
        assert time.monotonic() - before < 0.5
        assert results == [{"name": "slow", "ok": False, "reason": "timeout"}]
    finally:
        release.set()


def test_reload_confirmation_has_a_total_deadline(config, monkeypatch):
    agent = Agent(config)
    monkeypatch.setattr(agent, "command", lambda *args: "")
    ticks = iter([0, 3, 6])
    monkeypatch.setattr("apm.agent.time.monotonic", lambda: next(ticks))
    monkeypatch.setattr("apm.agent.time.sleep", lambda delay: None)
    attempts = []
    def unavailable():
        attempts.append(True)
        raise httpx.ReadTimeout("status API stalled")
    monkeypatch.setattr(agent, "generation", unavailable)
    with pytest.raises(ValueError, match="not confirmed"):
        agent.reload(1)
    assert len(attempts) == 1


def bind_agent(monkeypatch, agent):
    """Use the real Unix agent API contract without a listening socket."""
    import apm.agent
    monkeypatch.setattr(apm.agent, "Agent", lambda config: agent)
    client = TestClient(create_agent(agent.config))
    monkeypatch.setattr(httpx, "HTTPTransport", lambda **kwargs: httpx.MockTransport(
        lambda request: client.request(request.method, request.url.path,
                                       content=request.content, headers=dict(request.headers))
    ))
    return client


def test_worker_api_confirmation_warnings_and_csrf(admin, safe_agent, monkeypatch):
    agent, _, _ = safe_agent
    monkeypatch.setattr(agent, "capabilities", lambda: {"available": True})
    with bind_agent(monkeypatch, agent):
        resource = admin.post("/api/v1/resources/proxy-hosts", json={
            "name": "test", "data": {"domains": ["example.com"]},
        }).json()
        worker = Worker(agent.config, admin.app.state.db)
        assert worker.tick()
        operation = admin.get("/api/v1/operations/" + resource["operation_id"]).json()
        assert operation["status"] == "awaiting_confirmation", operation
        assert operation["warnings"][0]["code"] == "conflicting_server_name"
        assert "secret" not in json.dumps(operation)
        state = admin.get("/api/v1/safety").json()
        assert state["token"] and not state["route_verified"]
        body = {"revision_id": resource["revision_id"], "token": state["token"]}
        assert admin.post("/api/v1/safety/confirm", json=body).status_code == 409
        assert admin.post("/api/v1/safety/confirm", json=body,
                          headers={"X-CSRF-Token": "wrong"}).status_code == 403
        result = admin.post("/api/v1/safety/confirm", json=body,
                            headers={"X-APM-Revision": resource["revision_id"]})
        assert result.status_code == 200, result.text
        assert result.json()["status"] == "applied"
        assert admin.get("/api/v1/operations/" + resource["operation_id"]).json()["status"] == "succeeded"
        assert "Предупреждения" in admin.get("/fragments/operations").text


def test_worker_reconciles_rollback_and_keeps_following_snapshots_paused(admin, safe_agent, monkeypatch):
    agent, previous, _ = safe_agent
    monkeypatch.setattr(agent, "capabilities", lambda: {"available": True})
    with bind_agent(monkeypatch, agent):
        first = admin.post("/api/v1/resources/proxy-hosts", json={
            "name": "one", "data": {"domains": ["one.example"]},
        }).json()
        worker = Worker(agent.config, admin.app.state.db)
        worker.tick()
        operation = admin.get("/api/v1/operations/" + first["operation_id"]).json()
        assert operation["status"] == "awaiting_confirmation", operation
        second = admin.post("/api/v1/resources/proxy-hosts", json={
            "name": "two", "data": {"domains": ["two.example"]},
        }).json()
        assert not worker.tick()
        expire(agent)
        agent.watchdog_tick()
        assert not worker.tick()
        assert agent.current() == previous
        with admin.app.state.db.session() as session:
            assert session.get(Job, first["operation_id"]).status == "failed"
            assert session.get(Job, second["operation_id"]).status == "pending"
            assert session.get(Revision, first["revision_id"]).status == "rolled_back"
            assert state_get(session, "apply_halted")["halted"]
            assert state_get(session, "applied")["revision_id"] == previous
            assert len(list(session.scalars(select(Job)))) == 2


def test_operator_confirmation_is_bound_to_the_initiating_session(admin, safe_agent, monkeypatch):
    agent, _, _ = safe_agent
    monkeypatch.setattr(agent, "capabilities", lambda: {"available": True})
    for email in ("one@example.com", "two@example.com"):
        assert admin.post("/api/v1/users", json={"email": email, "password": "test-password-12345",
                                                "role": "operator"}).status_code == 201
    def login(email):
        response = admin.post("/api/v1/auth/login", json={"email": email, "password": "test-password-12345"})
        admin.headers["X-CSRF-Token"] = response.json()["csrf_token"]
    with bind_agent(monkeypatch, agent):
        login("one@example.com")
        resource = admin.post("/api/v1/resources/proxy-hosts", json={
            "name": "operator", "data": {"domains": ["operator.example"]},
        }).json()
        Worker(agent.config, admin.app.state.db).tick()
        own = admin.get("/api/v1/safety").json()
        assert own["can_manage"] and own["token"]
        body = {"revision_id": resource["revision_id"], "token": own["token"]}
        login("two@example.com")
        other = admin.get("/api/v1/safety").json()
        assert not other["can_manage"] and "token" not in other
        assert admin.post("/api/v1/safety/rollback", json=body).status_code == 403
        login("one@example.com")
        assert not admin.get("/api/v1/safety").json()["can_manage"]
        assert admin.post("/api/v1/safety/rollback", json=body).status_code == 403


def test_local_resume_reconciles_outcome_before_cancelling_stale_snapshots(admin, safe_agent, monkeypatch):
    import apm.cli
    from apm.cli import resume_applies

    agent, _, _ = safe_agent
    monkeypatch.setattr(agent, "capabilities", lambda: {"available": True})
    with bind_agent(monkeypatch, agent):
        first = admin.post("/api/v1/resources/proxy-hosts", json={
            "name": "first", "data": {"domains": ["first.example"]},
        }).json()
        worker = Worker(agent.config, admin.app.state.db)
        worker.tick()
        second = admin.post("/api/v1/resources/proxy-hosts", json={
            "name": "second", "data": {"domains": ["second.example"]},
        }).json()
        expire(agent)
        agent.watchdog_tick()
        # No worker/manager reconciliation happened after the rollback.
        monkeypatch.setattr(apm.cli, "Settings", lambda: agent.config)
        monkeypatch.setattr(apm.cli, "database", lambda config: admin.app.state.db)
        resume_applies()
        worker.sync_safety()
        with admin.app.state.db.session() as session:
            assert not state_get(session, "apply_halted")["halted"]
            assert session.get(Job, first["operation_id"]).status == "failed"
            assert session.get(Job, second["operation_id"]).status == "failed"
        assert not agent.safety()["halted"]
