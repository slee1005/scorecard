from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from golf_video_studio.api import app
from golf_video_studio import purge, storage
from golf_video_studio.models import Project


@pytest.fixture
def client(tmp_path,monkeypatch):
    monkeypatch.setenv('GVS_HOME',str(tmp_path/'home'))
    with TestClient(app) as c:
        yield c


def trashed(name='Trash'):
    p=storage.create(Project(name=name))
    root=storage.directory(p.id)
    (root/'source').write_bytes(b'video')
    (root/'output.mp4').write_bytes(b'output')
    p.round.player='Edited';p=storage.save(p)
    storage.job_put({'id':p.id,'project_id':p.id,'status':'done'})
    p=storage.trash(p.id,p.revision)
    return p,root


def empty(c,projects,confirm=True):
    return c.post('/api/v1/projects-trash/empty',json={'projects':[{'id':p.id,'revision':p.revision} for p in projects], 'confirm_permanent_delete':confirm})


def test_empty_removes_only_approved_trash_media_history_and_jobs(client):
    active=storage.create(Project(name='Keep'))
    keep=storage.directory(active.id);(keep/'source').write_bytes(b'keep video')
    p,root=trashed();q,other=trashed('Other')
    assert empty(client,[p,q],False).status_code==409
    assert root.exists() and storage.trash_projects()
    r=empty(client,[p,q]);assert r.status_code==200,r.text
    assert r.json()=={'deleted_count':2,'pending_cleanup':0}
    assert not root.exists() and not other.exists()
    assert client.get('/api/v1/projects-trash').json()==[]
    assert storage.load(active.id).id==active.id and (keep/'source').read_bytes()==b'keep video'
    assert client.post(f'/api/v1/projects/{p.id}/restore',json={'revision':p.revision}).status_code==404
    assert storage.jobs()==[]
    with storage.connect() as db:
        assert db.execute('SELECT COUNT(*) FROM edit_history WHERE pid IN (?,?)',(p.id,q.id)).fetchone()[0]==0
        assert db.execute('SELECT COUNT(*) FROM projects').fetchone()[0]==1
    assert empty(client,[]).json()=={'deleted_count':0,'pending_cleanup':0}


def test_stale_or_restored_trash_and_injected_paths_rejected(client):
    p,root=trashed();q,other=trashed('Added later')
    assert empty(client,[p]).status_code==409
    assert root.exists() and other.exists()
    storage.trash(q.id,q.revision,restore=True)
    assert empty(client,[p,q]).status_code==409
    assert root.exists() and storage.load(q.id).id==q.id
    r=client.post('/api/v1/projects-trash/empty',json={'projects':[{'id':'../../secret','revision':0}],'confirm_permanent_delete':True})
    assert r.status_code==422
    assert empty(client,[p,p]).status_code==422


def test_locked_files_remain_queued_and_can_be_retried(client,monkeypatch):
    p,root=trashed()
    real=purge.shutil.rmtree
    def locked(_):raise PermissionError('synthetic lock')
    monkeypatch.setattr(purge.shutil,'rmtree',locked)
    r=empty(client,[p]);assert r.status_code==200
    assert r.json()['pending_cleanup']==1 and root.exists()
    assert (root/'source').read_bytes()==b'video'
    assert client.get('/api/v1/projects-trash/cleanup-status').json()=={'pending':1}
    monkeypatch.setattr(purge.shutil,'rmtree',real)
    assert empty(client,[]).json()=={'deleted_count':0,'pending_cleanup':0}
    assert not root.exists()


def test_database_failure_rolls_back_entire_trash_set_before_files_change(client):
    p,root=trashed();q,other=trashed('Other')
    with storage.connect() as db:
        db.execute(f"CREATE TRIGGER block_delete BEFORE DELETE ON projects WHEN OLD.id='{q.id}' BEGIN SELECT RAISE(ABORT,'synthetic database failure'); END")
    assert empty(client,[p,q]).status_code==500
    assert (root/'source').exists() and (other/'source').exists()
    assert len(storage.trash_projects())==2 and purge.pending()==0
    with storage.connect() as db:
        assert db.execute('SELECT COUNT(*) FROM edit_history').fetchone()[0]==2


def test_project_symlink_does_not_delete_external_files(client,tmp_path):
    import shutil
    p,root=trashed()
    shutil.rmtree(root)
    external=tmp_path/'external';external.mkdir();(external/'keep').write_text('keep')
    root.symlink_to(external,target_is_directory=True)
    assert empty(client,[p]).json()['pending_cleanup']==0
    assert not root.is_symlink() and (external/'keep').read_text()=='keep'


def test_active_job_guard_and_empty_project_directory(client):
    p,root=trashed()
    storage.job_put({'id':'active','project_id':p.id,'status':'running'})
    assert empty(client,[p]).status_code==409 and root.exists()
    storage.job_put({'id':'active','project_id':p.id,'status':'done'})
    q=storage.create(Project());q=storage.trash(q.id,q.revision)
    assert empty(client,[p,q]).json()['deleted_count']==2


def test_restart_resumes_only_previously_confirmed_cleanup(client,monkeypatch):
    p,root=trashed()
    real=purge.shutil.rmtree
    def locked(_):raise PermissionError('synthetic lock')
    monkeypatch.setattr(purge.shutil,'rmtree',locked)
    assert empty(client,[p]).json()['pending_cleanup']==1
    monkeypatch.setattr(purge.shutil,'rmtree',real)
    q,untouched=trashed('Still recoverable')
    with TestClient(app) as restarted:
        assert restarted.get('/api/v1/projects-trash/cleanup-status').json()=={'pending':0}
        assert not root.exists()
        assert (untouched/'source').exists()
        assert [item['id'] for item in restarted.get('/api/v1/projects-trash').json()]==[q.id]
