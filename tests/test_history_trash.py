from __future__ import annotations

import copy

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from golf_video_studio import history, rendering, storage
from golf_video_studio.api import app
from golf_video_studio.models import Course, Hole, Overlay, Project, Round, Shot, Tee, Video


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv('GVS_HOME', str(tmp_path/'home'))
    with TestClient(app) as c:
        yield c


def seed():
    shot = Shot(hole=1,start=10,end=15)
    p = Project(round=Round(player='Saved player',holes=[Hole(number=n,par=4,score=4 if n<=5 else None) for n in range(1,19)]),
        shots=[shot],overlays=[Overlay(shot_id=shot.id,start=10,end=15),Overlay(type='full',start=20,end=25)],
        video=Video(filename='test.mp4',duration=60,width=960,height=540,fps=24,has_audio=False))
    return storage.create(p).model_dump(mode='json')


def save(c,p):
    r=c.put('/api/v1/projects/'+p['id'],json=p)
    assert r.status_code==200,r.text
    return r.json()['project']


def act(c,p,scope,action,expected=200):
    r=c.post(f"/api/v1/projects/{p['id']}/history",json={'revision':p['revision'],'scope':scope,'action':action,'confirm_reset':True})
    assert r.status_code==expected,r.text
    return r.json()['project'] if expected==200 else r


def test_independent_persisted_scopes_and_redo_branches(client):
    p=seed();snap=copy.deepcopy(p['snapshots'])
    p['round']['holes'][0]['score']=6;p=save(client,p)
    p['overlays'][0]['style']['accent']='#112233';p=save(client,p)
    p['shots'][0]['club']='7 Iron';p=save(client,p)
    p=act(client,p,'round','undo')
    assert p['round']['holes'][0]['score']==4
    assert p['shots'][0]['club']=='7 Iron' and p['overlays'][0]['style']['accent']=='#112233'
    p=act(client,p,'shot','undo')
    assert p['shots'][0]['club']=='Driver' and p['overlays'][0]['style']['accent']=='#112233'
    p=act(client,p,'design','undo')
    assert p['overlays'][0]['style']['accent']=='#29c4b5'
    p=act(client,p,'round','redo');p=act(client,p,'shot','redo');p=act(client,p,'design','redo')
    assert p['round']['holes'][0]['score']==6 and p['shots'][0]['club']=='7 Iron'
    assert p['snapshots']==snap
    p=act(client,p,'round','undo')
    p['round']['holes'][0]['score']=8;p=save(client,p)
    assert history.status(p['id'])['round']=={'undo':1,'redo':0}
    assert history.status(p['id'])['shot']['undo']==1
    act(client,p,'round','redo',409)
    # History is persisted, not browser-local; a second client can continue it.
    with TestClient(app) as second:
        p=act(second,p,'round','undo')
        assert p['round']['holes'][0]['score']==4


@pytest.mark.parametrize('scope',['round','shot','design'])
def test_reset_is_one_undoable_step_and_preserves_captures(client,scope):
    p=seed()
    p['overlays'][0]['style']['accent']='#112233';p=save(client,p)
    before=copy.deepcopy(p)
    p=act(client,p,scope,'reset')
    assert p['snapshots']==before['snapshots'] and p['video']==before['video']
    if scope=='round':
        assert p['round']['player']=='' and all(h['score'] is None and h['par'] is None for h in p['round']['holes'])
        assert p['shots']==before['shots']
    elif scope=='shot':
        assert p['shots']==[] and len(p['overlays'])==1 and p['overlays'][0]['type']=='full'
        assert p['round']==before['round']
    else:
        assert p['overlays'][0]['style']['accent']=='#34c6e5'
        assert [(o['start'],o['end'],o['snapshot_id']) for o in p['overlays']]==[(o['start'],o['end'],o['snapshot_id']) for o in before['overlays']]
    p=act(client,p,scope,'undo')
    assert history.state(Project.model_validate(p))==history.state(Project.model_validate(before))
    assert p['snapshots']==before['snapshots']
    p=act(client,p,scope,'redo')
    assert p['snapshots']==before['snapshots']


def test_round_reset_restores_imported_defaults_and_undo_preserves_reference(client):
    tee=Tee(name='Blue',holes=[Hole(number=n,par=4,yardage=350) for n in range(1,19)])
    course=Course(name='Published course',tees=[tee])
    r=Round(course='Override',player='Player',tee='Edited',reference=course,reference_tee_id=tee.id,
        holes=[Hole(number=n,par=5,score=6) for n in range(1,19)])
    p=storage.create(Project(round=r)).model_dump(mode='json');before=copy.deepcopy(p)
    p=act(client,p,'round','reset')
    assert p['round']['reference']==before['round']['reference']
    assert p['round']['course']=='Published course' and p['round']['tee']=='Blue'
    assert all(h['score'] is None and h['par']==4 for h in p['round']['holes'])
    p=act(client,p,'round','undo');assert p['round']==before['round']


def test_card_deletion_and_snapshot_replacement_can_be_undone_without_recapture(client):
    p=seed();original=copy.deepcopy(p['overlays'][1]);snapshots=copy.deepcopy(p['snapshots'])
    p['overlays'].pop();p=save(client,p)
    p=act(client,p,'design','undo')
    assert p['overlays'][1]==original and p['snapshots']==snapshots
    p['round']['holes'][0]['score']=7;p=save(client,p)
    sid=original['snapshot_id']
    r=client.post(f"/api/v1/projects/{p['id']}/scorecard-snapshots/{sid}/replace",json={
        'revision':p['revision'],'overlay_id':original['id'],'confirm_replace':True})
    assert r.status_code==200,r.text
    p=r.json()['project'];new=r.json()['created_snapshot_id']
    p=act(client,p,'design','undo')
    assert p['overlays'][1]['snapshot_id']==sid and new in p['snapshots']
    p=act(client,p,'design','redo')
    assert p['overlays'][1]['snapshot_id']==new and p['snapshots'][sid]==snapshots[sid]


def test_cross_scope_dependencies_reject_without_overwriting_or_consuming_history(client):
    p=seed()
    shot=Shot(hole=2,start=30,end=35)
    overlay=Overlay(shot_id=shot.id,start=30,end=35)
    p['shots'].append(shot.model_dump(mode='json'));p['overlays'].append(overlay.model_dump(mode='json'));p=save(client,p)
    p['overlays'][-1]['style']['accent']='#112233';p=save(client,p)
    revision=p['revision'];counts=history.status(p['id'])
    act(client,p,'shot','undo',409)
    assert storage.load(p['id']).revision==revision and history.status(p['id'])==counts
    p=act(client,p,'design','undo');p=act(client,p,'shot','undo')
    assert len(p['shots'])==1


def test_history_stale_confirm_and_bounded_history(client):
    p=seed();url=f"/api/v1/projects/{p['id']}/history"
    assert client.post(url,json={'revision':p['revision'],'scope':'round','action':'reset'}).status_code==409
    old=p['revision']
    for n in range(105):
        p['round']['player']=str(n);p=save(client,p)
    assert history.status(p['id'])['round']=={'undo':100,'redo':0}
    assert client.post(url,json={'revision':old,'scope':'round','action':'undo'}).status_code==409
    assert client.post(url,json={'revision':p['revision'],'scope':'snapshots','action':'reset','confirm_reset':True}).status_code==422


def test_project_trash_restore_retains_source_exports_and_history(client):
    p=seed();p['round']['player']='Edited';p=save(client,p)
    root=storage.directory(p['id']);(root/'source').write_bytes(b'original media');(root/'export.mp4').write_bytes(b'export')
    url='/api/v1/projects/'+p['id']
    assert client.request('DELETE',url,json={'revision':p['revision']}).status_code==409
    # TestClient.delete has no json helper in some HTTPX versions; use request.
    r=client.request('DELETE',url,json={'revision':p['revision'],'confirm_delete':True})
    assert r.status_code==200,r.text
    assert client.get(url).status_code==404
    assert client.get('/api/v1/projects').json()==[]
    assert (root/'source').read_bytes()==b'original media' and (root/'export.mp4').exists()
    trash=client.get('/api/v1/projects-trash').json();assert len(trash)==1
    assert client.post(url+'/restore',json={'revision':p['revision']}).status_code==409
    r=client.post(url+'/restore',json={'revision':trash[0]['revision']})
    assert r.status_code==200,r.text
    restored=r.json()['project'];assert restored['snapshots']==p['snapshots']
    assert r.json()['history']['round']['undo']==1
    restored=act(client,restored,'round','undo')
    assert restored['round']['player']=='Saved player'
    assert client.get('/api/v1/projects-trash').json()==[]


def test_active_export_blocks_trash_and_trashed_project_blocks_queue(client,monkeypatch):
    p=seed();url='/api/v1/projects/'+p['id']
    storage.job_put({'id':'active','project_id':p['id'],'status':'queued'})
    assert client.request('DELETE',url,json={'revision':p['revision'],'confirm_delete':True}).status_code==409
    storage.job_put({'id':'active','project_id':p['id'],'status':'done'})
    assert client.request('DELETE',url,json={'revision':p['revision'],'confirm_delete':True}).status_code==200
    monkeypatch.setattr(rendering,'binary',lambda _: 'ffmpeg')
    with pytest.raises(HTTPException) as exc:
        rendering.submit(Project.model_validate(p),'high','source')
    assert exc.value.status_code==409


def test_batched_mobile_sync_splits_round_shot_and_style_history(client):
    p=seed()
    p['round']['player']='Batch player'
    p['shots'][0]['club']='7 Iron'
    p['overlays'][0]['style']['accent']='#123456'
    p=save(client,p)
    assert history.status(p['id'])=={s:{'undo':1,'redo':0} for s in ('round','shot','design')}
    p=act(client,p,'round','undo')
    assert p['round']['player']=='Saved player' and p['shots'][0]['club']=='7 Iron'
    p=act(client,p,'shot','undo')
    assert p['shots'][0]['club']=='Driver' and p['overlays'][0]['style']['accent']=='#123456'
    p=act(client,p,'design','undo')
    assert p['overlays'][0]['style']['accent']=='#29c4b5'


def test_shot_timing_undo_keeps_later_design_changes(client):
    p=seed()
    p['shots'][0].update(start=11,end=16)
    p['overlays'][0].update(start=11,end=16)
    p=save(client,p)
    p['overlays'][0]['style']['accent']='#123456';p=save(client,p)
    p=act(client,p,'shot','undo')
    assert p['shots'][0]['start']==10 and p['overlays'][0]['start']==10
    assert p['overlays'][0]['style']['accent']=='#123456'
    p=act(client,p,'shot','redo')
    assert p['shots'][0]['start']==11 and p['overlays'][0]['start']==11


def test_unsafe_design_reset_is_atomic_and_does_not_consume_history(client):
    p=seed()
    # A nine-hole card normally fits beside the shot; changing its existing position
    # can make the factory placement overlap another same-time card on reset.
    p['overlays'][1]['start']=10;p['overlays'][1]['end']=15
    p['overlays'][1]['style'].update(x=.55,y=.04,width=.4,height=.56)
    p['overlays'][0]['style'].update(x=.04,y=.04,width=.4,height=.25)
    p=save(client,p)
    # Both factory panels fit vertically, so use a second card at another position.
    card=Overlay(type='front',start=10,end=15)
    card.style.x=.55;card.style.y=.65;card.style.width=.4;card.style.height=.3
    # Dedicated insert records this card from the current live scores.
    r=client.post(f"/api/v1/projects/{p['id']}/scorecard-snapshots",json={
        'revision':p['revision'],'timeline_position':10,'duration':5,'type':'front','style':card.style.model_dump()})
    assert r.status_code==201,r.text
    p=r.json()['project'];counts=history.status(p['id'])
    act(client,p,'design','reset',409)
    assert storage.load(p['id']).model_dump(mode='json')==p
    assert history.status(p['id'])==counts
