"""Bounded checks of published routes and secret-free Angie diagnostics."""

import http.client
import re
import socket
import ssl
import time
from concurrent.futures import ThreadPoolExecutor, wait
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class SafetyCheck(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=100)
    scheme: Literal["http", "https", "tcp", "tls"] = "https"
    host: str = Field(min_length=1, max_length=253, pattern=r"^[A-Za-z0-9_.:\[\]-]+$")
    port: int = Field(ge=1, le=65535)
    path: str = Field(default="/", max_length=2048, pattern=r"^/[^\r\n\x00 ]*$")
    server_name: str = Field(default="", max_length=253, pattern=r"^[A-Za-z0-9_.:-]*$")
    host_header: str = Field(default="", max_length=300, pattern=r"^[A-Za-z0-9_.:\[\]-]*$")
    expected_statuses: list[int] = Field(default=[200], min_length=1, max_length=20)
    body_contains: str = Field(default="", max_length=1000)
    verify: bool = True
    ca_file: str | None = None
    revision: str = ""


def probe(check):
    started = time.monotonic()
    result = {"name": check.name, "ok": False, "reason": "connection_error"}
    sock = connection = None
    try:
        sock = socket.create_connection((check.host, check.port), timeout=3)
        if check.scheme in ("https", "tls"):
            context = ssl.create_default_context(cafile=check.ca_file)
            if not check.verify:
                context.check_hostname = False
                context.verify_mode = ssl.CERT_NONE
            sock.settimeout(max(0.01, 3 - (time.monotonic() - started)))
            sock = context.wrap_socket(sock, server_hostname=check.server_name or check.host)
        if check.scheme in ("http", "https"):
            sock.settimeout(max(0.01, 3 - (time.monotonic() - started)))
            connection = http.client.HTTPConnection(check.host, check.port)
            connection.sock = sock
            connection.putrequest("GET", check.path, skip_host=True, skip_accept_encoding=True)
            connection.putheader("Host", check.host_header or check.server_name or check.host)
            connection.putheader("Connection", "close")
            connection.putheader("User-Agent", "APM-Safe-Apply/1")
            connection.endheaders()
            response = connection.getresponse()
            ok = response.status in check.expected_statuses
            result.update(http_status=response.status, reason="http_status")
            if ok and check.revision:
                ok = response.getheader("X-APM-Revision") == check.revision
                result["reason"] = "revision_mismatch"
            if ok and check.body_contains:
                ok = check.body_contains.encode() in response.read(65536)
                result["reason"] = "body_mismatch"
            result["ok"] = ok
        else:
            result["ok"] = True
        if result["ok"]:
            result["reason"] = "passed"
    except ssl.SSLError:
        result["reason"] = "tls_error"
    except (TimeoutError, socket.timeout):
        result["reason"] = "timeout"
    except (OSError, ValueError, http.client.HTTPException):
        pass
    finally:
        if connection:
            connection.close()
        if sock:
            sock.close()
    return result


def check_routes(checks, timeout=None):
    if not checks:
        return []
    pool = ThreadPoolExecutor(max_workers=8)
    futures = [pool.submit(probe, check) for check in checks]
    try:
        # Socket timeouts do not bound DNS resolution or a slowly streamed response.
        # Never let these retain the controller lock indefinitely.
        done, _ = wait(futures, timeout=timeout if timeout is not None else 3 * ((len(checks) + 7) // 8) + 1)
        return [future.result() if future in done else {"name": check.name, "ok": False, "reason": "timeout"}
                for check, future in zip(checks, futures)]
    finally:
        pool.shutdown(wait=False, cancel_futures=True)


WARNING_MESSAGES = {
    "conflicting_server_name": "Conflicting server name; a virtual host may be ignored.",
    "protocol_options_redefined": "Protocol options were redefined for a listener.",
    "deprecated_directive": "The configuration uses a deprecated directive.",
    "angie_warning": "Angie reported a warning; inspect the local error log for details.",
}


def warnings(output):
    # Never copy arbitrary stderr: directive arguments and paths can contain secrets.
    result = []
    for line in (output or "").splitlines():
        if "[warn]" not in line:
            continue
        code = next((key for key, marker in (
            ("conflicting_server_name", "conflicting server name"),
            ("protocol_options_redefined", "protocol options redefined"),
            ("deprecated_directive", "deprecated"),
        ) if marker in line), "angie_warning")
        item = {"code": code, "message": WARNING_MESSAGES[code]}
        location = re.search(r"/revisions/[0-9a-f-]{36}/([A-Za-z0-9_./-]+\.conf):(\d+)\s*$", line)
        if location:
            item.update(file=location[1], line=int(location[2]))
        result.append(item)
        if len(result) == 50:
            break
    return result
