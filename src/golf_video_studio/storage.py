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
    CREATE TABLE IF NOT EXISTS project_trash (id TEXT PRIMARY KEY, deleted_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS edit_history (seq INTEGER PRIMARY KEY AUTOINCREMENT, pid TEXT NOT NULL, scope TEXT NOT NULL, data TEXT NOT NULL, applied INTEGER NOT NULL);
    CREATE INDEX IF NOT EXISTS history_project_scope ON edit_history(pid,scope,seq);
    CREATE TABLE IF NOT EXISTS courses (id TEXT PRIMARY KEY, data TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, data TEXT NOT NULL);
    """)
    return db


def projects() -> list[Project]:
    with connect() as db:
        ids = [row[0] for row in db.execute('SELECT id FROM projects WHERE id NOT IN (SELECT id FROM project_trash)')]
    return sorted([load(pid) for pid in ids], key=lambda p:p.updated_at, reverse=True)


def load(pid: str, *, include_deleted: bool = False) -> Project:
    for _ in range(3):
        with connect() as db:
            if not include_deleted and db.execute('SELECT 1 FROM project_trash WHERE id=?',(pid,)).fetchone():
                raise HTTPException(404,'project_in_trash')
            row = db.execute('SELECT data FROM projects WHERE id=?',(pid,)).fetchone()
            if not row:
                raise HTTPException(404,'Project not found')
            raw = row[0]
            data = json.loads(raw)
            p = Project.model_validate(data)
            migrate = any(o.get('type') in ('full','front','back') and not o.get('snapshot_id') for o in data.get('overlays',[]))
            if not migrate:
                return p
            expected = p.revision
            p.revision += 1
            # A lease on both revision and original JSON prevents a read migration
            # from overwriting another window's score edit or a competing migration.
            result = db.execute('UPDATE projects SET revision=?,data=? WHERE id=? AND revision=? AND data=?',
                (p.revision,p.model_dump_json(),pid,expected,raw))
            if result.rowcount == 1:
                return p
    raise HTTPException(409,'Project changed while upgrading scorecards. Reload.')


def migrate_snapshots():
    projects()


def create(p: Project) -> Project:
    p.created_at = p.updated_at = now()
    with connect() as db:
        db.execute("INSERT INTO projects VALUES (?,?,?)", (p.id, p.revision, p.model_dump_json()))
    return p


def save(p: Project) -> Project:
    from . import history
    expected = p.revision
    old = load(p.id)
    p.revision += 1
    p.updated_at = now()
    with connect() as db:
        cursor = db.execute("UPDATE projects SET revision=?,data=? WHERE id=? AND revision=? AND NOT EXISTS (SELECT 1 FROM project_trash WHERE id=?)", (p.revision, p.model_dump_json(), p.id, expected, p.id))
        if cursor.rowcount != 1:
            raise HTTPException(409, "Project changed elsewhere. Reload before saving; your edits have not overwritten newer data.")
        history.record(db, old, p)
    return p


def trash_projects() -> list[dict]:
    with connect() as db:
        rows = db.execute('SELECT p.data,t.deleted_at FROM projects p JOIN project_trash t ON p.id=t.id ORDER BY t.deleted_at DESC').fetchall()
    return [dict(id=p.id,name=p.name,revision=p.revision,deleted_at=row['deleted_at'])
        for row in rows for p in [Project.model_validate_json(row['data'])]]


def trash(pid: str, revision: int, *, restore: bool = False) -> Project:
    p = load(pid, include_deleted=restore)
    if p.revision != revision:
        raise HTTPException(409, 'snapshot_stale_project')
    p.revision += 1
    p.updated_at = now()
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        if not restore:
            # Serialize this check with job creation so a queued export cannot lose its project.
            active = [json.loads(r[0]) for r in db.execute('SELECT data FROM jobs')]
            if any(j['project_id']==pid and j['status'] in ('queued','running') for j in active):
                raise HTTPException(409,'project_export_active')
        cursor = db.execute('UPDATE projects SET revision=?,data=? WHERE id=? AND revision=?', (p.revision,p.model_dump_json(),pid,revision))
        if cursor.rowcount != 1:
            raise HTTPException(409,'snapshot_stale_project')
        if restore:
            if db.execute('DELETE FROM project_trash WHERE id=?',(pid,)).rowcount != 1:
                raise HTTPException(409,'project_not_in_trash')
        else:
            db.execute('INSERT INTO project_trash VALUES (?,?)',(pid,now()))
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
