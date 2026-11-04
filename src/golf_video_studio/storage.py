from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from fastapi import HTTPException
from .models import Course, Project


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def home() -> Path:
    root = Path(os.environ.get("GVS_HOME", Path.home() / ".golf-video-studio"))
    root.mkdir(parents=True, exist_ok=True)
    return root


def connect():
    db = sqlite3.connect(home() / "studio.sqlite", timeout=30)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    db.executescript("""
    CREATE TABLE IF NOT EXISTS projects (id TEXT PRIMARY KEY, revision INTEGER NOT NULL, data TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS courses (id TEXT PRIMARY KEY, data TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, data TEXT NOT NULL);
    """)
    return db


def projects() -> list[Project]:
    with connect() as db:
        return sorted([Project.model_validate_json(r[0]) for r in db.execute("SELECT data FROM projects")], key=lambda p: p.updated_at, reverse=True)


def load(pid: str) -> Project:
    with connect() as db:
        row = db.execute("SELECT data FROM projects WHERE id=?", (pid,)).fetchone()
    if not row:
        raise HTTPException(404, "Project not found")
    return Project.model_validate_json(row[0])


def create(p: Project) -> Project:
    p.created_at = p.updated_at = now()
    with connect() as db:
        db.execute("INSERT INTO projects VALUES (?,?,?)", (p.id, p.revision, p.model_dump_json()))
    return p


def save(p: Project) -> Project:
    expected = p.revision
    p.revision += 1
    p.updated_at = now()
    with connect() as db:
        cursor = db.execute("UPDATE projects SET revision=?,data=? WHERE id=? AND revision=?", (p.revision, p.model_dump_json(), p.id, expected))
        if cursor.rowcount != 1:
            raise HTTPException(409, "Project changed elsewhere. Reload before saving; your edits have not overwritten newer data.")
    return p


def directory(pid: str) -> Path:
    # Only called with a validated, existing project ID.
    load(pid)
    path = home() / "projects" / pid
    path.mkdir(parents=True, exist_ok=True)
    return path


def courses(query: str = "") -> list[Course]:
    with connect() as db:
        values = [Course.model_validate_json(r[0]) for r in db.execute("SELECT data FROM courses")]
    words = query.casefold().split()
    return [c for c in values if all(w in f"{c.name} {c.club} {c.city} {c.state} {c.zip_code}".casefold() for w in words)]


def save_course(c: Course) -> Course:
    c.updated_at = now()
    with connect() as db:
        # Saved versions are immutable. Each import/save gets a new identity.
        db.execute("INSERT INTO courses VALUES (?,?)", (c.id, c.model_dump_json()))
    return c


def job_put(job: dict):
    with connect() as db:
        db.execute("INSERT OR REPLACE INTO jobs VALUES (?,?)", (job["id"], json.dumps(job)))


def jobs() -> list[dict]:
    with connect() as db:
        return [json.loads(r[0]) for r in db.execute("SELECT data FROM jobs ORDER BY rowid DESC LIMIT 100")]


def provider_cache_get(key: str) -> dict | None:
    with connect() as db:
        db.execute("CREATE TABLE IF NOT EXISTS provider_cache (key TEXT PRIMARY KEY, data TEXT NOT NULL)")
        row = db.execute("SELECT data FROM provider_cache WHERE key=?", (key,)).fetchone()
    return json.loads(row[0]) if row else None


def provider_cache_put(key: str, value: dict):
    import time
    with connect() as db:
        db.execute("CREATE TABLE IF NOT EXISTS provider_cache (key TEXT PRIMARY KEY, data TEXT NOT NULL)")
        db.execute("INSERT OR REPLACE INTO provider_cache VALUES (?,?)", (key, json.dumps({"time": time.time(), "data": value})))
