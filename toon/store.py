"""Tiny JSON state: which ideas were used and every job (script, render, upload). One file, one lock."""
import json
import threading
import time

from . import config

PATH = config.DATA / "state.json"
_LOCK = threading.RLock()


def _load() -> dict:
    try:
        return json.loads(PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"used_ideas": [], "jobs": {}}


def _save(d: dict):
    tmp = PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(PATH)


def used_ideas() -> set:
    with _LOCK:
        return set(_load()["used_ideas"])


def mark_used(idea: str):
    with _LOCK:
        d = _load()
        if idea not in d["used_ideas"]:
            d["used_ideas"].append(idea)
        _save(d)


def job(job_id: str) -> dict:
    with _LOCK:
        return _load()["jobs"].get(job_id, {})


def jobs() -> dict:
    with _LOCK:
        return _load()["jobs"]


def update(job_id: str, **fields) -> dict:
    with _LOCK:
        d = _load()
        j = d["jobs"].setdefault(job_id, {"created": time.strftime("%Y-%m-%d %H:%M:%S")})
        j.update(fields)
        j["updated"] = time.strftime("%Y-%m-%d %H:%M:%S")
        _save(d)
        return dict(j)
