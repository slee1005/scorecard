"""Persist small field deltas so independent editor sections do not overwrite each other."""
from __future__ import annotations

import copy
import json
from typing import Literal

from fastapi import HTTPException
from pydantic import ValidationError

from .models import Project, Round, Style, default_style

Scope = Literal['round', 'shot', 'design']
LIMIT = 100


def state(p: Project) -> dict:
    r = p.round.model_dump(mode='json')
    r['holes'] = {str(h['number']): h for h in r['holes']}
    return {'round': r, 'shots': {s.id: s.model_dump(mode='json') for s in p.shots},
        'shot_order': [s.id for s in p.shots],
        'overlays': {o.id: o.model_dump(mode='json') for o in p.overlays},
        'presets': {k: v.model_dump(mode='json') for k, v in p.presets.items()}}


def delta(before: dict, after: dict, path: list | None = None) -> list:
    changes = []
    for key in sorted(before.keys() | after.keys()):
        here = (path or []) + [key]
        if key in before and key in after and isinstance(before[key], dict) and isinstance(after[key], dict):
            changes.extend(delta(before[key], after[key], here))
        elif key not in before or key not in after or before[key] != after[key]:
            changes.append([here, key in before, before.get(key), key in after, after.get(key)])
    return changes


def apply(values: dict, changes: list, undo: bool) -> dict:
    result = copy.deepcopy(values)
    for path, had_before, before, had_after, after in changes:
        expected_exists, expected, target_exists, target = (had_after, after, had_before, before) if undo else (had_before, before, had_after, after)
        parent = result
        for key in path[:-1]:
            if key not in parent or not isinstance(parent[key], dict):
                raise HTTPException(409, 'history_dependency')
            parent = parent[key]
        key = path[-1]
        if (key in parent) != expected_exists or (expected_exists and parent[key] != expected):
            raise HTTPException(409, 'history_dependency')
        if target_exists:
            parent[key] = copy.deepcopy(target)
        else:
            parent.pop(key, None)
    return result


def project_from_state(p: Project, values: dict) -> Project:
    raw = p.model_dump(mode='json')
    r = copy.deepcopy(values['round'])
    r['holes'] = list(r['holes'].values())
    raw.update(round=r, shots=[values['shots'][key] for key in values['shot_order']],
        overlays=list(values['overlays'].values()), presets=values['presets'])
    try:
        return Project.model_validate(raw)
    except (ValidationError, KeyError):
        raise HTTPException(409, 'history_dependency') from None


def record(db, before: Project, after: Project, scope: Scope | None = None):
    changes = delta(state(before), state(after))
    if not changes:
        return
    groups: dict[str, list] = {}
    old_shots = {s.id:s for s in before.shots}
    new_shots = {s.id:s for s in after.shots}
    overlays = {o.id:o for o in before.overlays + after.overlays}
    for change in changes:
        path = change[0]
        group = scope
        if group is None:
            group = 'round' if path[0] == 'round' else 'shot' if path[0] in ('shots','shot_order') else 'design'
            if path[0] == 'overlays':
                overlay = overlays.get(path[1])
                sid = overlay.shot_id if overlay else None
                # Shot CRUD/timing carries its dependent popup. Styling remains design history,
                # even if a mobile outbox sync batches round, shot and style edits together.
                if sid and old_shots.get(sid) != new_shots.get(sid) and (len(path)==2 or path[2] in ('start','end')):
                    group = 'shot'
        groups.setdefault(group, []).append(change)
    for group, patch in groups.items():
        db.execute('DELETE FROM edit_history WHERE pid=? AND scope=? AND applied=0', (after.id, group))
        db.execute('INSERT INTO edit_history(pid,scope,data,applied) VALUES (?,?,?,1)', (after.id, group, json.dumps(patch)))
        db.execute('DELETE FROM edit_history WHERE pid=? AND scope=? AND seq NOT IN (SELECT seq FROM edit_history WHERE pid=? AND scope=? ORDER BY seq DESC LIMIT ?)',
            (after.id, group, after.id, group, LIMIT))


def status(pid: str) -> dict:
    from . import storage
    with storage.connect() as db:
        rows = db.execute('SELECT scope,applied,COUNT(*) FROM edit_history WHERE pid=? GROUP BY scope,applied', (pid,)).fetchall()
    result = {scope: {'undo': 0, 'redo': 0} for scope in ('round', 'shot', 'design')}
    for scope, applied, count in rows:
        result[scope]['undo' if applied else 'redo'] = count
    return result


def reset(p: Project, scope: Scope) -> Project:
    result = p.model_copy(deep=True)
    if scope == 'round':
        old = p.round
        result.round = Round(reference=old.reference, reference_tee_id=old.reference_tee_id)
        tee = next((t for t in old.reference.tees if t.id == old.reference_tee_id), None) if old.reference else None
        if tee:
            result.round.course = old.reference.name
            result.round.tee, result.round.category = tee.name, tee.category
            result.round.rating, result.round.slope = tee.rating, tee.slope
            result.round.total_par, result.round.total_yardage = tee.par, tee.yardage
            result.round.holes = [h.model_copy(deep=True) for h in tee.holes]
    elif scope == 'shot':
        result.shots = []
        result.overlays = [o for o in result.overlays if o.type not in ('shot', 'minimal')]
    else:
        from .snapshots import card_style
        for o in result.overlays:
            o.style = card_style(result, o.type) if o.type in ('full', 'front', 'back') else shot_style(result)
    try:
        return Project.model_validate(result.model_dump())
    except ValidationError:
        raise HTTPException(409, 'history_reset_collision') from None


def shot_style(p: Project) -> Style:
    return default_style('shot')


def perform(pid: str, revision: int, scope: Scope, action: Literal['undo','redo','reset']) -> Project:
    from . import storage
    p = storage.load(pid)
    if p.revision != revision:
        raise HTTPException(409, 'snapshot_stale_project')
    with storage.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        row = db.execute('SELECT revision FROM projects WHERE id=? AND NOT EXISTS (SELECT 1 FROM project_trash WHERE id=?)', (pid,pid)).fetchone()
        if not row or row[0] != revision:
            raise HTTPException(409, 'snapshot_stale_project')
        if action == 'reset':
            updated = reset(p, scope)
            record(db, p, updated, scope)
        else:
            sql = 'SELECT seq,data FROM edit_history WHERE pid=? AND scope=? AND applied=? ORDER BY seq ' + ('DESC' if action == 'undo' else 'ASC') + ' LIMIT 1'
            entry = db.execute(sql, (pid,scope,int(action == 'undo'))).fetchone()
            if not entry:
                raise HTTPException(409, 'history_empty')
            updated = project_from_state(p, apply(state(p), json.loads(entry['data']), action == 'undo'))
            db.execute('UPDATE edit_history SET applied=? WHERE seq=?', (int(action == 'redo'),entry['seq']))
        updated.revision += 1
        updated.updated_at = storage.now()
        db.execute('UPDATE projects SET revision=?,data=? WHERE id=?', (updated.revision,updated.model_dump_json(),pid))
    return updated
