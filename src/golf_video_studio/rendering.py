from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from fastapi import HTTPException
from . import storage
from .graphics import panel
from .models import Project, uid

POOL = ThreadPoolExecutor(max_workers=1, thread_name_prefix="gvs-render")
GUARD = threading.Lock()


def binary(name: str) -> str:
    path = shutil.which(name)
    if not path:
        raise HTTPException(503, f"{name} is required. Install FFmpeg and restart.")
    return path


def probe(path: Path) -> dict:
    try:
        result = subprocess.run([binary("ffprobe"), "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)], capture_output=True, text=True, timeout=30, check=True)
        info = json.loads(result.stdout)
        v = next(s for s in info['streams'] if s['codec_type'] == 'video' and not s.get('disposition', {}).get('attached_pic'))
        a, b = v.get('avg_frame_rate', '30/1').split('/')
        rotation = next((abs(int(s.get('rotation', 0))) for s in v.get('side_data_list', []) if 'rotation' in s), 0)
        w, h = int(v['width']), int(v['height'])
        if rotation % 180 == 90:
            w, h = h, w
        result = dict(duration=float(info['format']['duration']), width=w, height=h, fps=float(a)/float(b), has_audio=any(s['codec_type'] == 'audio' for s in info['streams']))
        if not (0 < result['duration'] <= 86400 and 0 < result['fps'] <= 240 and max(w,h) <= 8192):
            raise ValueError("Unsupported video metadata")
        return result
    except (ValueError, KeyError, StopIteration, ZeroDivisionError, subprocess.SubprocessError) as exc:
        raise HTTPException(422, "Cannot read video metadata. Use a valid MP4, MOV or WebM video (max 24 hours / 8K / 240fps).") from exc


def submit(p: Project, quality: str, resolution: str) -> dict:
    binary("ffmpeg")
    if not p.video:
        raise HTTPException(422, "Upload a video first")
    with GUARD:
        if sum(j['status'] in ('queued','running') for j in storage.jobs()) >= 3:
            raise HTTPException(429, "Render queue is full")
        job = dict(id=uid(), project_id=p.id, name=p.name, status="queued", progress=0, error=None,
                   created_at=storage.now(), quality=quality, resolution=resolution, revision=p.revision)
        # Queue publication shares SQLite's writer lock with project trashing.
        # Whichever wins either protects the active job or rejects the stale export.
        with storage.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT revision FROM projects WHERE id=? AND id NOT IN (SELECT id FROM project_trash)', (p.id,)).fetchone()
            if not row or row[0] != p.revision:
                raise HTTPException(409,'snapshot_stale_project')
            db.execute('INSERT INTO jobs VALUES (?,?)', (job['id'], json.dumps(job)))
        POOL.submit(run, p.model_copy(deep=True), job)
    return job


def run(p: Project, job: dict):
    root = storage.directory(p.id)
    output = root / f"{job['id']}.mp4"
    job.update(status="running")
    storage.job_put(job)
    try:
        with tempfile.TemporaryDirectory(prefix="render-", dir=root) as tmp:
            v = p.video
            limit = 1920 if job['resolution'] == '1080' else 3840 if job['resolution'] == '2160' else max(v.width,v.height)
            scale = min(1, limit / max(v.width,v.height))
            w,h = max(2, int(v.width*scale)//2*2), max(2, int(v.height*scale)//2*2)
            cmd = [binary('ffmpeg'), '-hide_banner', '-y', '-i', str(root/'source')]
            overlays = [o for o in p.overlays if o.visible]
            for n,o in enumerate(overlays):
                img = panel(p,o).resize((max(1, round(o.style.width*w)), max(1, round(o.style.height*h))))
                file = Path(tmp)/f'{n}.png'
                img.save(file)
                cmd += ['-i', str(file)]
            filters = [f'[0:v]scale={w}:{h},setsar=1[v0]']
            for n,o in enumerate(overlays):
                s = o.style
                # Half-open intervals match preview, including exact cut boundaries.
                filters.append(f"[v{n}][{n+1}:v]overlay=x={round(s.x*w)}:y={round(s.y*h)}:enable='gte(t,{o.start})*lt(t,{o.end})'[v{n+1}]")
            cmd += ['-filter_complex_threads','1','-filter_complex',';'.join(filters),'-map',f'[v{len(overlays)}]','-map','0:a:0?',
                    '-c:v','libx264','-preset','fast','-crf',{'draft':'26','high':'18','master':'15'}[job['quality']],
                    '-pix_fmt','yuv420p','-c:a','aac','-b:a','192k','-movflags','+faststart','-t',str(v.duration),
                    '-progress','pipe:1','-nostats', str(output)]
            # stderr goes to a file so FFmpeg cannot block on a full pipe.
            with (Path(tmp)/'ffmpeg.log').open('w+') as log:
                with subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=log, text=True) as proc:
                    last_write = 0
                    for line in proc.stdout:
                        if line.startswith('out_time_us='):
                            try:
                                job['progress'] = min(.99, max(0, int(line.split('=')[1])/1e6/v.duration))
                            except ValueError:
                                continue
                            if time.monotonic()-last_write > .3:
                                storage.job_put(job)
                                last_write = time.monotonic()
                    proc.wait()
                    if proc.returncode:
                        log.seek(0)
                        raise RuntimeError(log.read()[-2000:])
            job.update(status="done",progress=1, finished_at=storage.now())
    except Exception as exc:
        output.unlink(missing_ok=True)
        job.update(status="error",error=str(exc)[-2000:])
    storage.job_put(job)


def recover():
    """Interrupted work fails explicitly; never leave a permanent spinning job."""
    for job in storage.jobs():
        if job['status'] in ('queued','running'):
            job.update(status='error', error='Server restarted. Submit the export again.')
            storage.job_put(job)
        elif job['status'] == 'done':
            path = storage.home()/'projects'/job['project_id']/f"{job['id']}.mp4"
            if path.exists() and time.time()-path.stat().st_mtime > 86400:
                path.unlink()
                job.update(status='expired')
                storage.job_put(job)
