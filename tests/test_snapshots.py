"""Historical cards remain independent through editing, migration and export."""
from __future__ import annotations

import copy
import json

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from golf_video_studio import graphics, snapshots, storage
from golf_video_studio.api import app
from golf_video_studio.models import Hole, Overlay, Project, Round, Video


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv('GVS_HOME', str(tmp_path/'home'))
    with TestClient(app) as c:
        yield c


def project():
    return storage.create(Project(round=Round(player='Snapshot Player', course='Test Course',
        holes=[Hole(number=n, par=[4,4,3,5,4][n-1] if n<=5 else 4,
            score=[4,3,3,6,4][n-1] if n<=5 else None) for n in range(1,19)]),
        video=Video(filename='synthetic.mp4',duration=1200,width=480,height=270,fps=24,has_audio=False)))


def save(client, p):
    r=client.put(f"/api/v1/projects/{p['id']}",json=p)
    assert r.status_code==200,r.text
    return r.json()['project']


def insert(client,p,time):
    r=client.post(f"/api/v1/projects/{p['id']}/scorecard-snapshots",json={
        'revision':p['revision'],'timeline_position':time})
    assert r.status_code==201,r.text
    d=r.json()
    return d['project'],d['created_snapshot_id']


def test_five_nine_eighteen_holes_are_independent_with_confirmed_version_history(client):
    p=project().model_dump(mode='json')
    base=f"/api/v1/projects/{p['id']}/scorecard-snapshots"
    preview=client.post(base+'/preview',json={'revision':p['revision'],'timeline_position':150})
    assert preview.status_code==200
    assert storage.load(p['id']).snapshots=={}  # cancel/preview never writes
    p,one=insert(client,p,150)
    first=copy.deepcopy(p['snapshots'][one])
    assert first['current_hole']==6 and first['completed_holes_count']==5
    assert (first['front_nine_score'],first['back_nine_score'],first['total_score'],first['total_par'],first['relative_to_par'])==(20,None,20,20,0)
    assert first['scorecard_data']['course_par']==72
    assert [h['status'] for h in first['scorecard_data']['holes']]==['completed']*5+['current']+['not_played']*12
    assert all(h['score'] is None for h in first['scorecard_data']['holes'][5:])
    oid=p['overlays'][0]['id']
    png=client.get(f"/api/v1/projects/{p['id']}/overlays/{oid}.png").content
    for h in p['round']['holes'][5:9]:h['score']=4
    p=save(client,p)
    assert p['snapshots'][one]==first
    assert client.get(f"/api/v1/projects/{p['id']}/overlays/{oid}.png").content==png
    p,two=insert(client,p,345)
    second=copy.deepcopy(p['snapshots'][two])
    assert second['completed_holes_count']==9 and second['total_score']==36
    for h in p['round']['holes'][9:]:h['score']=4
    p=save(client,p)
    p,three=insert(client,p,930)
    third=copy.deepcopy(p['snapshots'][three])
    assert third['completed_holes_count']==18 and third['current_hole'] is None and third['total_score']==72
    p['round']['holes'][0]['score']=7
    p['round']['player']='Corrected live name'
    p=save(client,p)
    assert [p['snapshots'][s] for s in (one,two,three)]==[first,second,third]
    # Presentation edits and a timeline move do not recapture data or its origin.
    p['overlays'][0].update(start=155,end=163)
    p['overlays'][0]['style'].update(accent='#ff1234',width=.4)
    p=save(client,p)
    assert p['snapshots'][one]==first and first['timeline_position']==150
    body={'revision':p['revision'],'overlay_id':oid}
    assert client.post(base+f'/{one}/replace',json=body).status_code==409
    assert storage.load(p['id']).snapshots[one].model_dump(mode='json')==first
    r=client.post(base+f'/{one}/replace',json={**body,'confirm_replace':True})
    assert r.status_code==200,r.text
    p=r.json()['project'];new=r.json()['created_snapshot_id']
    assert p['overlays'][0]['snapshot_id']==new
    assert p['snapshots'][new]['previous_snapshot_id']==one
    assert p['snapshots'][new]['snapshot_version']==2
    assert p['snapshots'][new]['total_score']==75
    assert [p['snapshots'][s] for s in (one,two,three)]==[first,second,third]
    assert [o['snapshot_id'] for o in p['overlays'][1:]]==[two,three]


def test_frozen_data_and_unknown_completed_par():
    p=Project(round=Round(holes=[Hole(number=n,par=None if n==2 else 4,score=4 if n<=2 else None) for n in range(1,19)]))
    s=snapshots.capture(p,10)
    assert s.total_score==8 and s.total_par is None and s.relative_to_par is None
    assert s.back_nine_score is None
    p.round.holes[0].score=8
    assert s.scorecard_data.holes[0].score==4
    with pytest.raises(ValidationError):s.scorecard_data.holes[0].score=8
    with pytest.raises(ValidationError):s.total_score=99
    with pytest.raises(ValidationError):s.scorecard_data.player='Changed'


def test_api_rejects_rewriting_snapshots_and_stale_confirmations(client):
    p=project().model_dump(mode='json');p,sid=insert(client,p,10)
    url=f"/api/v1/projects/{p['id']}"
    edited=copy.deepcopy(p);edited['snapshots'][sid]['scorecard_data']['player']='Forged'
    assert client.put(url,json=edited).status_code==422
    edited=copy.deepcopy(p);edited['overlays'].append(Overlay(type='full',start=50,end=55).model_dump(mode='json'))
    assert client.put(url,json=edited).status_code==422
    stale=p['revision'];p['name']='New revision';p=save(client,p)
    assert client.post(url+'/scorecard-snapshots',json={'revision':stale,'timeline_position':50}).status_code==409
    assert client.post(url+'/scorecard-snapshots/preview',json={'revision':p['revision'],'timeline_position':50,'current_hole':1}).status_code==422
    assert client.post(url+'/scorecard-snapshots',json={'revision':p['revision'],'timeline_position':1200}).status_code==422
    assert len(storage.load(p['id']).snapshots)==1


def test_legacy_migration_is_persisted_once_before_future_edits(client):
    p=project();raw=p.model_dump(mode='json')
    raw.pop('snapshots')
    raw['overlays']=[Overlay(type='front',start=10,end=15).model_dump(mode='json')]
    with storage.connect() as db:
        db.execute('UPDATE projects SET data=? WHERE id=?',(json.dumps(raw),p.id))
    migrated=storage.load(p.id)
    sid=migrated.overlays[0].snapshot_id
    s=migrated.snapshots[sid]
    assert s.legacy and s.completed_holes_count==5
    assert migrated.revision==p.revision+1
    assert storage.load(p.id).model_dump()==migrated.model_dump()
    migrated.round.holes[0].score=9
    storage.save(migrated)
    assert storage.load(p.id).snapshots[sid]==s


def test_snapshot_ownership_and_reference_validation():
    p=Project();s=snapshots.capture(p,0)
    raw=Project().model_dump();raw['snapshots']={s.id:s.model_dump()}
    with pytest.raises(ValidationError):Project.model_validate(raw)
    with pytest.raises(ValidationError):Project(overlays=[Overlay(type='full',snapshot_id='a'*32)])


def test_export_keeps_three_historical_captures_after_live_correction(client,tmp_path):
    import io
    import shutil
    import subprocess
    import time
    from PIL import Image, ImageChops, ImageStat
    if not shutil.which('ffmpeg'):
        pytest.skip('FFmpeg required')
    source=tmp_path/'source.mp4'
    subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','color=c=0x203040:s=640x360:r=24:d=3',
        '-c:v','libx264','-pix_fmt','yuv420p',str(source)],check=True)
    p=project().model_dump(mode='json')
    p['video']=None
    # Upload through the same endpoint used by web/native rather than seed a source path.
    with storage.connect() as db:
        db.execute('UPDATE projects SET data=? WHERE id=?',(json.dumps(p),p['id']))
    with source.open('rb') as f:
        r=client.post(f"/api/v1/projects/{p['id']}/video",files={'file':('source.mp4',f,'video/mp4')})
    assert r.status_code==200,r.text
    p=r.json()['project']
    def add(at):
        r=client.post(f"/api/v1/projects/{p['id']}/scorecard-snapshots",json={
            'revision':p['revision'],'timeline_position':at,'duration':.8})
        assert r.status_code==201,r.text
        return r.json()['project']
    p=add(.1)
    for h in p['round']['holes'][5:9]:h['score']=4
    p=save(client,p);p=add(1.1)
    for h in p['round']['holes'][9:]:h['score']=4
    p=save(client,p);p=add(2.1)
    p['round']['holes'][0]['score']=9
    p=save(client,p)
    assert [p['snapshots'][o['snapshot_id']]['completed_holes_count'] for o in p['overlays']]==[5,9,18]
    r=client.post(f"/api/v1/projects/{p['id']}/exports",json={'revision':p['revision'],'quality':'high','resolution':'source'})
    assert r.status_code==202,r.text
    jid=r.json()['id']
    for _ in range(200):
        job=next(j for j in client.get('/api/v1/jobs').json() if j['id']==jid)
        if job['status'] in ('done','error'):break
        time.sleep(.05)
    assert job['status']=='done',job
    result=storage.directory(p['id'])/f'{jid}.mp4'
    def frame(path,at):
        raw=subprocess.check_output(['ffmpeg','-v','error','-ss',str(at),'-i',str(path),'-frames:v','1','-f','rawvideo','-pix_fmt','rgb24','pipe:1'])
        return Image.frombytes('RGB',(640,360),raw)
    background=frame(source,.5)
    for overlay,at in zip(p['overlays'],(.5,1.5,2.5)):
        image=Image.open(io.BytesIO(client.get(f"/api/v1/projects/{p['id']}/overlays/{overlay['id']}.png").content))
        style=overlay['style'];expected=background.convert('RGBA')
        image=image.resize((round(style['width']*640),round(style['height']*360)))
        expected.alpha_composite(image,(round(style['x']*640),round(style['y']*360)))
        actual=frame(result,at)
        assert max(ImageStat.Stat(ImageChops.difference(expected.convert('RGB'),actual)).mean)<5
        # The overlay is present, not merely a close match to the source.
        assert max(ImageStat.Stat(ImageChops.difference(background,actual)).mean)>3
