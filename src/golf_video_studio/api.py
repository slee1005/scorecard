from __future__ import annotations

import argparse
import csv
import io
import json
import os
import shutil
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, Request, UploadFile, Query
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ValidationError, SecretStr, Field

from . import rendering, storage, course_api, snapshots, history, purge
from .graphics import png
from .models import Course, Hole, Project, Tee, Video, Style, Overlay, totals, uid
from typing import Literal

WEB = Path(__file__).parent/'web'


@asynccontextmanager
async def lifespan(app):
    purge.cleanup()
    storage.migrate_snapshots()
    rendering.recover()
    yield


app = FastAPI(title="Golf Video Studio", version="0.1.0", lifespan=lifespan)


@app.middleware('http')
async def local_only(request: Request, call_next):
    # No unauthenticated network listener: DNS rebinding and cross-origin writes are rejected.
    if request.url.hostname not in ('127.0.0.1','localhost','testserver'):
        return Response('Local access only',403)
    origin = request.headers.get('origin')
    if origin and origin != f'{request.url.scheme}://{request.headers.get("host")}':
        return Response('Origin rejected',403)
    response = await call_next(request)
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Referrer-Policy'] = 'same-origin'
    response.headers['Content-Security-Policy'] = "default-src 'self'; img-src 'self' blob: data:; media-src 'self' blob:; script-src 'self'; style-src 'self' 'unsafe-inline'; frame-ancestors 'none'; object-src 'none'"
    return response


def summary(p: Project) -> dict:
    return {'history':history.status(p.id), 'project':p.model_dump(), 'overrides':round_overrides(p), 'totals':{'front':totals(p.round.holes[:9]), 'back':totals(p.round.holes[9:]), 'all':totals(p.round.holes)}}


def round_overrides(p: Project) -> list[str]:
    r = p.round
    if not r.reference:
        return []
    tee = next((t for t in r.reference.tees if t.id == r.reference_tee_id), None)
    if not tee:
        return []
    result = [key for key, current, original in (
        ('course', r.course, r.reference.name), ('tee', r.tee, tee.name),
        ('category', r.category, tee.category), ('rating', r.rating, tee.rating),
        ('slope', r.slope, tee.slope), ('total_par', r.total_par, tee.par),
        ('total_yardage', r.total_yardage, tee.yardage)) if current != original]
    for h, original in zip(r.holes, tee.holes):
        for key in ('par', 'yardage', 'handicap'):
            if getattr(h, key) != getattr(original, key):
                result.append(f'holes.{h.number}.{key}')
    return result


@app.get('/api/v1/health')
def health():
    return {'status':'ok','ffmpeg':bool(shutil.which('ffmpeg')),'ffprobe':bool(shutil.which('ffprobe'))}


@app.get('/api/v1/projects')
def list_projects():
    return [dict(id=p.id,name=p.name,updated_at=p.updated_at,video=p.video.model_dump() if p.video else None) for p in storage.projects()]


class NewProject(BaseModel):
    name: str = 'Untitled round'


@app.post('/api/v1/projects',status_code=201)
def create_project(body: NewProject):
    return summary(storage.create(Project(name=body.name)))


class ProjectRemoval(BaseModel):
    revision: int = Field(ge=0)
    confirm_delete: bool = False


class ProjectRevision(BaseModel):
    revision: int = Field(ge=0)


class HistoryAction(ProjectRevision):
    scope: Literal['round','shot','design']
    action: Literal['undo','redo','reset']
    confirm_reset: bool = False


@app.get('/api/v1/projects-trash')
def list_trash():
    return storage.trash_projects()


class TrashTarget(BaseModel):
    id: str = Field(pattern=r'^[a-f0-9]{32}$')
    revision: int = Field(ge=0)


class EmptyTrash(BaseModel):
    projects: list[TrashTarget] = Field(max_length=10000)
    confirm_permanent_delete: bool = False


@app.get('/api/v1/projects-trash/cleanup-status')
def trash_cleanup_status():
    return {'pending':purge.pending()}


class SelectedTrash(EmptyTrash):
    projects: list[TrashTarget] = Field(min_length=1,max_length=10000)


def _purge_trash(body: EmptyTrash, *, selected_only: bool = False):
    if not body.confirm_permanent_delete:
        raise HTTPException(409,'trash_confirm_empty')
    expected = {p.id:p.revision for p in body.projects}
    if len(expected) != len(body.projects):
        raise HTTPException(422,'trash_changed')
    return purge.empty(expected,selected_only=selected_only)


@app.post('/api/v1/projects-trash/empty')
def empty_trash(body: EmptyTrash):
    return _purge_trash(body)


@app.post('/api/v1/projects-trash/delete-selected')
def delete_selected_trash(body: SelectedTrash):
    return _purge_trash(body,selected_only=True)


@app.delete('/api/v1/projects/{pid}')
def delete_project(pid: str, body: ProjectRemoval):
    if not body.confirm_delete:
        raise HTTPException(409,'project_confirm_delete')
    p = storage.trash(pid,body.revision)
    return {'id':p.id,'revision':p.revision,'trashed':True}


@app.post('/api/v1/projects/{pid}/restore')
def restore_project(pid: str, body: ProjectRevision):
    return summary(storage.trash(pid,body.revision,restore=True))


@app.post('/api/v1/projects/{pid}/history')
def edit_history(pid: str, body: HistoryAction):
    if body.action == 'reset' and not body.confirm_reset:
        raise HTTPException(409,'history_confirm_reset')
    return summary(history.perform(pid,body.revision,body.scope,body.action))


@app.get('/api/v1/projects/{pid}')
def get_project(pid: str):
    return summary(storage.load(pid))


@app.put('/api/v1/projects/{pid}')
def put_project(pid: str, body: Project):
    old = storage.load(pid)
    if body.revision != old.revision:
        raise HTTPException(409, 'snapshot_stale_project')
    if body.snapshots != old.snapshots:
        raise HTTPException(422, 'snapshot_read_only')
    old_cards = {o.id:o for o in old.overlays if o.type in ('full','front','back')}
    for overlay in body.overlays:
        if overlay.type in ('full','front','back'):
            previous = old_cards.get(overlay.id)
            if previous is None or overlay.snapshot_id != previous.snapshot_id:
                raise HTTPException(422, 'snapshot_use_capture_action')
    if (pid != body.id or body.video != old.video or body.reference_file != old.reference_file
            or body.created_at != old.created_at or body.round.reference != old.round.reference
            or body.round.reference_tee_id != old.round.reference_tee_id):
        raise HTTPException(422,'Server-managed fields cannot be changed')
    return summary(storage.save(body))


class SnapshotPreview(BaseModel):
    revision: int = Field(ge=0)
    timeline_position: float = Field(ge=0, le=86400)
    current_hole: int | None = Field(default=None, ge=1, le=18)


class SnapshotInsert(SnapshotPreview):
    type: Literal['full','front','back'] = 'full'
    duration: float = Field(default=5,gt=0,le=86400)
    style: Style | None = None


class SnapshotReplace(BaseModel):
    revision: int = Field(ge=0)
    overlay_id: str
    current_hole: int | None = Field(default=None,ge=1,le=18)
    confirm_replace: bool = False


def _capture_project(pid: str, revision: int) -> Project:
    p = storage.load(pid)
    if p.revision != revision:
        raise HTTPException(409,'snapshot_stale_project')
    return p


def _snapshot_capacity(p: Project):
    if len(p.snapshots) >= 1000:
        raise HTTPException(422,'snapshot_history_limit')


@app.post('/api/v1/projects/{pid}/scorecard-snapshots/preview')
def preview_snapshot(pid: str, body: SnapshotPreview):
    p = _capture_project(pid,body.revision)
    if not p.video or body.timeline_position >= p.video.duration:
        raise HTTPException(422,'snapshot_invalid_time')
    return snapshots.capture(p,body.timeline_position,body.current_hole)


@app.post('/api/v1/projects/{pid}/scorecard-snapshots',status_code=201)
def insert_snapshot(pid: str, body: SnapshotInsert):
    p = _capture_project(pid,body.revision)
    if not p.video or body.timeline_position >= p.video.duration:
        raise HTTPException(422,'snapshot_invalid_time')
    _snapshot_capacity(p)
    snap = snapshots.capture(p,body.timeline_position,body.current_hole)
    overlay = Overlay(type=body.type,snapshot_id=snap.id,start=body.timeline_position,
        end=min(body.timeline_position+body.duration,p.video.duration),style=body.style or snapshots.card_style(p,body.type))
    p.snapshots[snap.id] = snap
    p.overlays.append(overlay)
    try:
        p = Project.model_validate(p.model_dump())
    except ValidationError:
        raise HTTPException(422,'snapshot_layout_collision') from None
    result = summary(storage.save(p))
    return {**result,'created_overlay_id':overlay.id,'created_snapshot_id':snap.id}


@app.post('/api/v1/projects/{pid}/scorecard-snapshots/{snapshot_id}/replace')
def replace_snapshot(pid: str, snapshot_id: str, body: SnapshotReplace):
    p = _capture_project(pid,body.revision)
    if not body.confirm_replace:
        raise HTTPException(409,'snapshot_confirm_replace')
    overlay = next((o for o in p.overlays if o.id == body.overlay_id and o.snapshot_id == snapshot_id),None)
    old = p.snapshots.get(snapshot_id)
    if overlay is None or old is None:
        raise HTTPException(404,'snapshot_not_found')
    _snapshot_capacity(p)
    snap = snapshots.capture(p,overlay.start,body.current_hole,previous=old)
    p.snapshots[snap.id] = snap
    overlay.snapshot_id = snap.id
    p = Project.model_validate(p.model_dump())
    return {**summary(storage.save(p)),'created_snapshot_id':snap.id,'created_overlay_id':overlay.id}


@app.post('/api/v1/projects/{pid}/video')
async def upload_video(pid: str, file: UploadFile = File(...)):
    p = storage.load(pid)
    if p.video:
        raise HTTPException(409,'Create a new project for another video')
    ext = Path(file.filename or '').suffix.lower()
    if ext not in ('.mp4','.mov','.webm'):
        raise HTTPException(422,'Use MP4, MOV or WebM')
    root = storage.directory(pid)
    size = 0
    path = root/f'upload-{uid()}'
    try:
        with path.open('wb') as out:
            while chunk := await file.read(1024*1024):
                size += len(chunk)
                if size > int(os.environ.get('GVS_MAX_UPLOAD_MB','8192'))*1024*1024:
                    raise HTTPException(413,'Video exceeds configured upload limit')
                out.write(chunk)
        # Probe off the async event loop.
        from starlette.concurrency import run_in_threadpool
        meta = await run_in_threadpool(rendering.probe,path)
        current = storage.load(pid)
        if current.revision != p.revision or current.video:
            raise HTTPException(409,'Project changed while uploading. Try again.')
        p.video = Video(filename=Path(file.filename).name, **meta)
        p = Project.model_validate(p.model_dump())
        # File publication and revision update share an inter-process upload lock.
        lock = root/'upload.lock'
        try:
            fd = os.open(lock, os.O_CREAT|os.O_EXCL|os.O_WRONLY)
        except FileExistsError:
            raise HTTPException(409,'Another upload is finishing')
        try:
            os.close(fd)
            if storage.load(pid).revision != p.revision:
                raise HTTPException(409,'Project changed while uploading')
            path.replace(root/'source')
            try:
                saved = storage.save(p)
            except Exception:
                (root/'source').unlink(missing_ok=True)
                raise
        finally:
            lock.unlink(missing_ok=True)
        return summary(saved)
    finally:
        path.unlink(missing_ok=True)
        await file.close()


@app.get('/api/v1/projects/{pid}/video')
def video(pid: str):
    p = storage.load(pid)
    if not p.video:
        raise HTTPException(404,'No video')
    ext = Path(p.video.filename).suffix.lower()
    return FileResponse(storage.directory(pid)/'source', media_type={'.mp4':'video/mp4','.mov':'video/quicktime','.webm':'video/webm'}[ext])


@app.get('/api/v1/projects/{pid}/overlays/{oid}.png')
def graphic(pid: str, oid: str):
    p = storage.load(pid)
    overlay = next((o for o in p.overlays if o.id == oid),None)
    if not overlay:
        raise HTTPException(404,'Overlay not found')
    return Response(png(p,overlay),media_type='image/png',headers={'Cache-Control':'no-store'})


@app.post('/api/v1/projects/{pid}/holes-csv')
async def import_holes(pid: str, revision: int, file: UploadFile = File(...)):
    p = storage.load(pid)
    if p.revision != revision:
        raise HTTPException(409,'Reload before importing')
    data = await file.read(100001)
    if len(data)>100000:
        raise HTTPException(413,'CSV too large')
    try:
        rows = list(csv.DictReader(io.StringIO(data.decode('utf-8-sig'))))
        if not rows or len(rows)>18:
            raise ValueError('Use 1–18 rows')
        updates = {}
        for row in rows:
            n = int(row['hole'])
            if n in updates:
                raise ValueError('Duplicate hole')
            value = p.round.holes[n-1].model_dump() if 1 <= n <=18 else {'number':n}
            for key in ('par','yardage','score','handicap'):
                if key in row:
                    value[key] = int(row[key]) if row[key].strip() else None
            updates[n] = Hole.model_validate(value)
        p.round.holes = [updates.get(h.number,h) for h in p.round.holes]
    except (ValueError,KeyError,UnicodeError,IndexError) as exc:
        raise HTTPException(422,f'Invalid CSV: {exc}') from exc
    return summary(storage.save(p))


@app.post('/api/v1/projects/{pid}/reference')
async def reference(pid: str, revision: int, file: UploadFile = File(...)):
    p = storage.load(pid)
    if p.revision != revision:
        raise HTTPException(409,'Reload before uploading')
    ext = Path(file.filename or '').suffix.lower()
    if ext not in ('.png','.jpg','.jpeg','.pdf'):
        raise HTTPException(422,'Use PNG, JPG or PDF')
    data = await file.read(15*1024*1024+1)
    if len(data)>15*1024*1024:
        raise HTTPException(413,'Reference exceeds 15 MB')
    if (ext=='.pdf' and not data.startswith(b'%PDF-')) or (ext in ('.jpg','.jpeg') and not data.startswith(b'\xff\xd8')) or (ext=='.png' and not data.startswith(b'\x89PNG')):
        raise HTTPException(422,'Invalid reference file')
    root=storage.directory(pid)
    old=p.reference_file
    p.reference_file=f'reference-{uid()}{ext}'
    path=root/p.reference_file
    path.write_bytes(data)
    try:
        saved=storage.save(p)
    except Exception:
        path.unlink(missing_ok=True)
        raise
    if old:
        (root/old).unlink(missing_ok=True)
    return summary(saved)


@app.get('/api/v1/projects/{pid}/reference')
def get_reference(pid: str):
    p=storage.load(pid)
    if not p.reference_file:
        raise HTTPException(404)
    return FileResponse(storage.directory(pid)/p.reference_file,filename=p.reference_file)


class ProviderKey(BaseModel):
    api_key: SecretStr


@app.get('/api/v1/course-provider/settings')
def provider_settings():
    return course_api.key_status()


@app.put('/api/v1/course-provider/settings')
def provider_configure(body: ProviderKey):
    return course_api.configure(body.api_key.get_secret_value())


@app.delete('/api/v1/course-provider/settings')
def provider_clear():
    return course_api.configure(None)


@app.get('/api/v1/course-provider/search')
def provider_search(q: str = Query(min_length=2, max_length=160)):
    return course_api.search(q)


@app.post('/api/v1/course-provider/courses/{course_id}/import')
def provider_import(course_id: str, refresh: bool = False):
    return course_api.import_course(course_id, refresh)


@app.get('/api/v1/courses')
def list_courses(q: str = '', offset: int = 0, limit: int = 50):
    values=storage.courses(q)
    return {'items':[c.model_dump() for c in values[max(0,offset):max(0,offset)+min(100,max(1,limit))]],'total':len(values)}


@app.post('/api/v1/courses',status_code=201)
def create_course(body: Course):
    # Imports get an internal ID, preserving external IDs in their own field.
    body.id=uid()
    return storage.save_course(body)


class Selection(BaseModel):
    course_id: str
    tee_id: str
    revision: int
    confirm_replace: bool = False


@app.post('/api/v1/projects/{pid}/course')
def select_course(pid: str, body: Selection):
    p=storage.load(pid)
    if p.revision != body.revision:
        raise HTTPException(409,'Reload before replacing course data')
    if (p.round.course or any(h.par is not None or h.yardage is not None for h in p.round.holes)) and not body.confirm_replace:
        raise HTTPException(409,'Confirm replacement of existing course values')
    course=next((c for c in storage.courses() if c.id==body.course_id),None)
    tee=next((t for t in course.tees if t.id==body.tee_id),None) if course else None
    if not tee:
        raise HTTPException(404,'Course or tee not found')
    scores={h.number:h.score for h in p.round.holes}
    p.round=p.round.model_copy(update=dict(course=course.name,tee=tee.name,category=tee.category,rating=tee.rating,slope=tee.slope,
        total_par=tee.par,total_yardage=tee.yardage,holes=[h.model_copy(update={'score':scores[h.number]}) for h in tee.holes], reference=course,reference_tee_id=tee.id))
    return summary(storage.save(p))


class Export(BaseModel):
    revision: int
    quality: str = 'high'
    resolution: str = 'source'


@app.post('/api/v1/projects/{pid}/exports',status_code=202)
def export(pid: str, body: Export):
    p=storage.load(pid)
    if body.revision != p.revision:
        raise HTTPException(409,'Save and reload before exporting')
    if body.quality not in ('draft','high','master') or body.resolution not in ('source','1080','2160'):
        raise HTTPException(422,'Unsupported export preset')
    return rendering.submit(p,body.quality,body.resolution)


@app.get('/api/v1/jobs')
def jobs():
    return storage.jobs()


@app.get('/api/v1/jobs/{jid}/download')
def download(jid: str):
    job=next((j for j in storage.jobs() if j['id']==jid),None)
    if not job or job['status']!='done':
        raise HTTPException(404,'Export unavailable')
    path=storage.directory(job['project_id'])/f'{jid}.mp4'
    if not path.is_file():
        raise HTTPException(410,'Export expired')
    return FileResponse(path,media_type='video/mp4',filename=f'Golf-Video-Studio-{jid[:8]}.mp4')


@app.get('/')
def index():
    return FileResponse(WEB/'index.html')


app.mount('/static',StaticFiles(directory=WEB),name='static')


def main():
    parser=argparse.ArgumentParser(description='Local Golf Video Studio')
    parser.add_argument('--port',type=int,default=8775)
    args=parser.parse_args()
    import uvicorn
    uvicorn.run(app,host='127.0.0.1',port=args.port)
