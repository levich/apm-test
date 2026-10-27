import subprocess
import uuid
from pathlib import Path

import pytest
from pydantic import ValidationError

from apm.agent import Agent, Deployment
from apm.compiler import Compiler
from apm.config import Settings
from apm.schemas import Route, Runtime, Stream


@pytest.fixture
def existing(tmp_path):
    root = tmp_path / "angie.conf"
    data = tmp_path / "data"
    root.write_text(
        "pid /run/angie.pid;\nevents {}\nhttp {\ninclude mime.types;\n"
        'server { listen 80 default_server; return 200 "legacy"; }\n'
        f'include "{data}/current/http.conf"; # APM\n}}\n'
        f"stream {{\ninclude {data}/current/stream.conf;\n}}\n"
    )
    config = Settings(
        _env_file=None, data_dir=data, angie_mode="existing", angie_config=root, angie_prefix=tmp_path,
        safe_apply=False,
    )
    agent = Agent(config)
    agent.initialize()
    return agent


def deployment(agent, resources=None):
    revision = uuid.uuid4()
    bundle = Compiler(agent.config, {}, agent.config.data_dir / "revisions" / str(revision)).compile(
        resources or []
    )
    return Deployment(revision_id=revision, configuration=bundle.config, files=bundle.files)


def test_existing_requires_explicit_absolute_paths(tmp_path):
    with pytest.raises(ValidationError, match="APM_ANGIE_CONFIG"):
        Settings(_env_file=None, angie_mode="existing", data_dir=tmp_path)
    with pytest.raises(ValidationError, match="APM_DATA_DIR"):
        Settings(_env_file=None, angie_mode="existing", data_dir=Path("relative"))
    with pytest.raises(ValidationError, match="APM_ANGIE_PREFIX"):
        Settings(_env_file=None, angie_mode="existing", data_dir=tmp_path, angie_config=tmp_path / "main")


def test_bootstrap_preserves_existing_root_and_is_idempotent(existing):
    source = existing.config.root_config.read_bytes()
    stat = existing.config.root_config.stat()
    current = existing.current()
    existing.initialize()
    assert existing.current() == current
    assert existing.config.root_config.read_bytes() == source
    assert existing.config.root_config.stat().st_mtime_ns == stat.st_mtime_ns
    assert (existing.config.data_dir / "current/http.conf").is_file()
    assert (existing.config.data_dir / "current/stream.conf").is_file()


def test_bootstrap_refuses_missing_existing_root(existing):
    existing.config.root_config.unlink()
    with pytest.raises(ValueError, match="does not exist"):
        existing.initialize()
    assert not existing.config.root_config.exists()


def test_existing_compiler_scopes_policies_to_apm_hosts(existing):
    resources = [
        {"id": "route", "kind": "proxy-hosts", "data": Route(domains=["apm.test"]).model_dump()},
        {"id": "runtime", "kind": "runtime", "data": Runtime(access_logs=True).model_dump()},
        {
            "id": "tcp",
            "kind": "streams",
            "data": Stream(listen_port=19080, host="127.0.0.1", port=8080).model_dump(),
        },
    ]
    bundle = deployment(existing, resources)
    http = bundle.files["http.conf"]
    globals = http
    server = bundle.files["http/route.proxy.conf"]
    assert "access_log" not in globals
    assert "ssl_protocols" not in globals
    assert "server_tokens" not in globals
    assert "error_log" not in globals
    assert "server_tokens off;" in server
    assert "ssl_protocols TLSv1.2 TLSv1.3;" in server
    assert 'logs/access.log" apm;' in server
    assert f'error_log "{existing.config.data_dir}/logs/error.log" warn;' in server
    assert "server_name apm.test;" in server
    assert "default_server" not in http
    assert "18081" not in http
    assert "bootstrap" not in http
    assert "load_module" not in bundle.configuration
    assert "pid " not in bundle.configuration
    assert bundle.files["stream/tcp.stream.conf"].startswith("server {\naccess_log off;\n")
    assert 'stream/tcp.stream.conf";' in bundle.files["stream.conf"]


def test_validation_uses_full_config_without_switching_current(existing, monkeypatch):
    previous = existing.current()
    source = existing.config.root_config.read_bytes()
    directory = existing.stage(deployment(existing))
    paths = []

    def command(*args):
        assert args[:2] == ("-t", "-c")
        path = Path(args[2])
        paths.append(path)
        assert path.parent == existing.config.root_config.parent
        text = path.read_text()
        assert f'include "{directory}/http.conf"; # APM' in text
        assert f'include "{directory}/stream.conf";' in text
        assert 'return 200 "legacy";' in text
        assert "include mime.types;" in text
        assert existing.current() == previous
        assert existing.config.root_config.read_bytes() == source

    monkeypatch.setattr(existing, "command", command)
    existing.validate(directory)
    assert not paths[0].exists()


@pytest.mark.parametrize("duplicate", [False, True])
def test_validation_requires_unambiguous_root_includes(existing, monkeypatch, duplicate):
    root = existing.config.root_config
    line = f'include "{existing.config.data_dir}/current/http.conf"; # APM'
    root.write_text(root.read_text().replace(line, line + "\n" + line if duplicate else "# removed"))
    monkeypatch.setattr(existing, "command", lambda *args: pytest.fail("Must fail before angie -t"))
    with pytest.raises(ValueError, match="exactly one standalone include"):
        existing.validate(existing.stage(deployment(existing)))


def test_rejected_existing_candidate_never_switches_or_reloads(existing, monkeypatch):
    previous = existing.current()
    source = existing.config.root_config.read_bytes()

    def reject(*args):
        assert args[:2] == ("-t", "-c")
        raise ValueError("invalid legacy or APM directive")

    monkeypatch.setattr(existing, "command", reject)
    monkeypatch.setattr(existing, "reload", lambda _: pytest.fail("Must not reload"))
    with pytest.raises(ValueError, match="invalid legacy or APM directive"):
        existing.apply(deployment(existing))
    assert existing.current() == previous
    assert existing.config.root_config.read_bytes() == source
    assert not list(existing.config.root_config.parent.glob(".apm-validate-*"))


def test_existing_reload_failure_restores_only_apm_revision(existing, monkeypatch):
    previous = existing.current()
    source = existing.config.root_config.read_bytes()
    candidate = deployment(existing)
    monkeypatch.setattr(existing, "command", lambda *args: "valid")
    monkeypatch.setattr(existing, "generation", lambda: 1)
    attempts = []

    def reload(before):
        attempts.append(existing.current())
        if len(attempts) == 1:
            raise ValueError("reload failed")
        return 2

    monkeypatch.setattr(existing, "reload", reload)
    with pytest.raises(ValueError, match="previous revision restored"):
        existing.apply(candidate)
    assert attempts == [str(candidate.revision_id), previous]
    assert existing.current() == previous
    assert existing.config.root_config.read_bytes() == source
    assert not (existing.config.data_dir / "run/apply-journal.json").exists()


def test_commands_use_existing_prefix(existing, monkeypatch):
    calls = []

    def run(args, **kwargs):
        calls.append(args)
        return subprocess.CompletedProcess(args, 0, "ok", "")

    monkeypatch.setattr("apm.agent.subprocess.run", run)
    existing.command("-s", "reload", "-c", str(existing.config.root_config))
    assert calls == [
        [
            existing.config.angie_binary,
            "-p",
            str(existing.config.angie_prefix),
            "-s",
            "reload",
            "-c",
            str(existing.config.root_config),
        ]
    ]
