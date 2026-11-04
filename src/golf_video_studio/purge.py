"""Permanently remove only the exact trash set approved in a confirmation dialog."""
from __future__ import annotations

import json
import shutil
import sqlite3

from fastapi import HTTPException

from . import storage


def pending() -> int:
    with storage.connect() as db:
        return db.execute('SELECT COUNT(*) FROM purge_queue').fetchone()[0]


def cleanup() -> int:
    # The queue is durable: a crash or OS file lock never silently strands large videos.
    with storage.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        root = storage.home()/'projects'
        for row in db.execute('SELECT id FROM purge_queue').fetchall():
            # A reused identity must never allow cleanup to touch a current project.
            if db.execute('SELECT 1 FROM projects WHERE id=?',(row['id'],)).fetchone():
                continue
            target = root/row['id']
            try:
                if root.is_symlink():
                    continue
                if target.is_symlink():
                    target.unlink()  # never follow a project symlink outside the data home
                elif target.exists():
                    shutil.rmtree(target)
            except OSError:
                continue
            db.execute('DELETE FROM purge_queue WHERE id=?',(row['id'],))
        return db.execute('SELECT COUNT(*) FROM purge_queue').fetchone()[0]


def empty(expected: dict[str, int], *, selected_only: bool = False) -> dict:
    try:
        with storage.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            actual = dict(db.execute('SELECT p.id,p.revision FROM projects p JOIN project_trash t ON p.id=t.id').fetchall())
            if selected_only:
                if not expected or any(actual.get(pid) != revision for pid,revision in expected.items()):
                    raise HTTPException(409,'trash_changed')
            elif actual != expected:
                raise HTTPException(409,'trash_changed')
            jobs = [json.loads(row[0]) for row in db.execute('SELECT data FROM jobs')]
            if any(j['project_id'] in expected and j['status'] in ('queued','running') for j in jobs):
                raise HTTPException(409,'project_export_active')
            # Commit metadata removal and its cleanup queue together before touching
            # files. A crash at any point leaves either recoverable trash or a durable,
            # explicitly approved deletion to resume; no directory can be stranded.
            for pid in expected:
                db.execute('INSERT INTO purge_queue VALUES (?)',(pid,))
                db.execute('DELETE FROM edit_history WHERE pid=?',(pid,))
                db.execute('DELETE FROM project_trash WHERE id=?',(pid,))
                db.execute('DELETE FROM projects WHERE id=?',(pid,))
            for job in jobs:
                if job['project_id'] in actual:
                    db.execute('DELETE FROM jobs WHERE id=?',(job['id'],))
    except sqlite3.Error:
        raise HTTPException(500,'trash_storage_failure') from None
    return {'deleted_count':len(expected),'pending_cleanup':cleanup()}
