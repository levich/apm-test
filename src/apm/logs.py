"""Bounded, read-only queries over Angie's current access and error logs."""

import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, model_validator

MAX_BYTES = 4 * 1024 * 1024
MAX_LINES = 10000
ERROR_LINE = re.compile(
    r"^(?P<time>\d{4}/\d{2}/\d{2} \d{2}:\d{2}:\d{2}) "
    r"\[(?P<level>emerg|alert|crit|error|warn|notice|info|debug)\] (?P<message>.*)$"
)


class LogQuery(BaseModel):
    q: str = Field(default="", max_length=500)
    host: str = Field(default="", max_length=255)
    ip: str = Field(default="", max_length=255)
    method: str = Field(default="", max_length=30, pattern=r"^[A-Za-z-]*$")
    status: str = Field(default="", pattern=r"^(?:[1-5](?:[0-9]{2}|xx))?$")
    level: Literal["", "emerg", "alert", "crit", "error", "warn", "notice", "info", "debug"] = ""
    since: datetime | None = None
    until: datetime | None = None
    limit: int = Field(default=200, ge=1, le=500)
    offset: int = Field(default=0, ge=0, le=MAX_LINES)

    @model_validator(mode="after")
    def time_range(self):
        if self.since and self.until and self.since.timestamp() > self.until.timestamp():
            raise ValueError("The start time must not be after the end time")
        return self


def parse_entry(line: str, kind: str) -> dict:
    if kind == "access":
        try:
            entry = json.loads(line)
            if isinstance(entry, dict):
                return entry
        except ValueError:
            pass
    else:
        match = ERROR_LINE.match(line)
        if match:
            entry = match.groupdict()
            for key, pattern in (
                ("host", r'(?:^|, )host: "([^"]*)"'),
                ("ip", r"(?:^|, )client: ([^, ]+)"),
                ("method", r'(?:^|, )request: "([A-Z-]+) '),
            ):
                value = re.search(pattern, entry["message"])
                if value:
                    entry[key] = value[1]
            return entry
    return {"message": line}


def entry_timestamp(entry: dict, kind: str) -> float | None:
    try:
        value = str(entry.get("time", ""))
        parsed = (datetime.strptime(value, "%Y/%m/%d %H:%M:%S") if kind == "error"
                  else datetime.fromisoformat(value))
        return parsed.timestamp()
    except (ValueError, OverflowError, OSError):
        return None


def query_logs(path: Path, kind: str, filters: LogQuery) -> dict:
    result = {
        "entries": [], "exists": False, "scanned": 0, "matched": 0,
        "offset": filters.offset, "limit": filters.limit, "has_more": False, "truncated": False,
    }
    try:
        with path.open("rb") as stream:
            size = os.fstat(stream.fileno()).st_size
            start = max(0, size - MAX_BYTES)
            stream.seek(start)
            block = stream.read(min(size, MAX_BYTES))
    except FileNotFoundError:
        return result
    result["exists"] = True
    if start:
        # The first bytes can belong to a record that starts outside this window.
        block = block.partition(b"\n")[2]
    lines = block.splitlines()
    result["truncated"] = bool(start or len(lines) > MAX_LINES)
    since = filters.since.timestamp() if filters.since else None
    until = filters.until.timestamp() if filters.until else None
    search = filters.q.casefold()
    for raw in reversed(lines[-MAX_LINES:]):
        if not raw.strip():
            continue
        result["scanned"] += 1
        line = raw.decode("utf-8", errors="replace")
        entry = parse_entry(line, kind)
        if search and search not in line.casefold() and search not in json.dumps(entry, ensure_ascii=False).casefold():
            continue
        if any(value.casefold() not in str(entry.get(key, "")).casefold()
               for key, value in (("host", filters.host), ("ip", filters.ip)) if value):
            continue
        if filters.method and str(entry.get("method", "")).upper() != filters.method.upper():
            continue
        status = str(entry.get("status", ""))
        if filters.status and not (
            len(status) == 3 and (status.startswith(filters.status[0]) if filters.status.endswith("xx")
                                else status == filters.status)
        ):
            continue
        if filters.level and entry.get("level") != filters.level:
            continue
        if since is not None or until is not None:
            timestamp = entry_timestamp(entry, kind)
            if timestamp is None or (since is not None and timestamp < since) or (
                until is not None and timestamp > until
            ):
                continue
        index = result["matched"]
        result["matched"] += 1
        if filters.offset <= index < filters.offset + filters.limit:
            result["entries"].append(entry)
    result["has_more"] = result["matched"] > filters.offset + filters.limit
    return result
