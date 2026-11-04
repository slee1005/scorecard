from __future__ import annotations

import json
import shutil
import subprocess
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageChops
from pydantic import ValidationError

from golf_video_studio.api import app
from golf_video_studio.models import (Course, Hole, Overlay, Project, Round, Shot, Style,
    Tee, active_overlays, classification, numbered_shots, totals)
from golf_video_studio import graphics, rendering, storage


@pytest.fixture
def client(tmp_path,monkeypatch):
    monkeypatch.setenv('GVS_HOME',str(tmp_path/'home'))
    with TestClient(app) as c:
        yield c


def test_unknown_values_are_not_invented():
    p=Project()
    assert all(h.par is None and h.yardage is None for h in p.round.holes)
    assert totals(p.round.holes)['score'] is None
    assert totals(p.round.holes)['relative'] is None


@pytest.mark.parametrize('delta,kind',[(-3,'under'),(-2,'eagle'),(-1,'birdie'),(0,'par'),(1,'bogey'),(2,'double'),(3,'over')])
def test_scoring(delta,kind):
    assert classification(5,5+delta)==kind
    assert classification(None,4)=='unknown'


def test_front_back_totals_and_partial_round():
    holes=[Hole(number=n,par=4,score=3 if n<=9 else 5,yardage=400) for n in range(1,19)]
    assert totals(holes[:9])['score']==27
    assert totals(holes[9:])['score']==45
    assert totals(holes)['relative']==0
    assert totals(holes)['yardage']==7200
    holes[0].score=None
    holes[1].par=None
    result=totals(holes)
    assert result['played']==17 and result['rated_played']==16
    assert result['relative']==2


def test_order_and_numbering():
    a,b,c=Shot(hole=2),Shot(hole=1),Shot(hole=2)
    p=Project(shots=[a,b,c])
    assert numbered_shots(p)=={a.id:1,b.id:1,c.id:2}
    p.shots.reverse()
    assert numbered_shots(p)[c.id]==1


def test_half_open_intervals_and_collision():
    s=Shot(hole=1)
    a=Overlay(shot_id=s.id,start=0,end=1)
    b=Overlay(shot_id=s.id,start=1,end=2)
    p=Project(shots=[s],overlays=[a,b])
    assert active_overlays(p,0)==[a]
    assert active_overlays(p,1)==[b]
    assert active_overlays(p,2)==[]
    b.start=.9
    with pytest.raises(ValidationError):Project.model_validate(p.model_dump())


def test_simultaneous_card_and_shot():
    s=Shot(hole=1)
    p=Project(shots=[s],overlays=[Overlay(shot_id=s.id),Overlay(type='full',style=Style(x=.04,y=.04,width=.92,height=.26))])
    assert len(active_overlays(p,1))==2


def test_bounds_and_validation():
    with pytest.raises(ValidationError):Style(x=.8,width=.4)
    with pytest.raises(ValidationError):Style(x=float('nan'))
    with pytest.raises(ValidationError):Shot(hole=1,start=5,end=2)
    with pytest.raises(ValidationError):Round(holes=[Hole(number=1)]*18)
    with pytest.raises(ValidationError):Round(date='2026-99-99')


def test_persistence_and_conflict(client):
    a=client.post('/api/v1/projects',json={'name':'A'}).json()['project']
    a['round']['player']='John'
    saved=client.put('/api/v1/projects/'+a['id'],json=a)
    assert saved.status_code==200
    assert saved.json()['project']['revision']==1
    assert client.put('/api/v1/projects/'+a['id'],json=a).status_code==409
    assert client.get('/api/v1/projects/'+a['id']).json()['project']['round']['player']=='John'


def test_csv_atomic_import(client):
    p=client.post('/api/v1/projects',json={}).json()['project']
    url=f"/api/v1/projects/{p['id']}/holes-csv?revision=0"
    bad=client.post(url,files={'file':('holes.csv',b'hole,par,yardage\n1,4,400\n1,3,170')})
    assert bad.status_code==422
    assert storage.load(p['id']).round.holes[0].par is None
    good=client.post(url,files={'file':('holes.csv',b'hole,par,yardage,score\n1,4,400,3\n2,3,170,')})
    assert good.status_code==200
    assert good.json()['totals']['front']['score']==3
    assert good.json()['project']['round']['holes'][2]['par'] is None


def test_course_selection_preserves_scores_and_reference(client):
    p=client.post('/api/v1/projects',json={}).json()['project']
    p['round']['course']='Existing';p['round']['holes'][0]['score']=5
    p=client.put('/api/v1/projects/'+p['id'],json=p).json()['project']
    course=Course(name='Private Test',verification='imported',tees=[Tee(name='Blue',category='Men',rating=71.2,slope=126)])
    c=client.post('/api/v1/courses',json=course.model_dump()).json()
    body=dict(course_id=c['id'],tee_id=c['tees'][0]['id'],revision=p['revision'])
    url='/api/v1/projects/'+p['id']+'/course'
    assert client.post(url,json=body).status_code==409
    body['confirm_replace']=True
    result=client.post(url,json=body).json()['project']
    assert result['round']['holes'][0]['score']==5
    assert result['round']['rating']==71.2
    assert result['round']['reference']['tees'][0]['rating']==71.2
    result['round']['rating']=70.0
    assert client.put('/api/v1/projects/'+p['id'],json=result).status_code==200
    assert storage.load(p['id']).round.reference.tees[0].rating==71.2
    actual=client.get('/api/v1/projects/'+p['id']).json()
    assert 'rating' in actual['overrides']
    actual['project']['round']['reference']['tees'][0]['rating']=66
    assert client.put('/api/v1/projects/'+p['id'],json=actual['project']).status_code==422


def test_origin_and_server_fields(client):
    assert client.post('/api/v1/projects',json={},headers={'origin':'https://evil.example'}).status_code==403
    assert client.get('/',headers={'host':'evil.example'}).status_code==403
    p=client.post('/api/v1/projects',json={}).json()['project']
    p['reference_file']='../../secret'
    assert client.put('/api/v1/projects/'+p['id'],json=p).status_code==422


def test_png_uses_exact_panel(client):
    p=Project(shots=[Shot(hole=1)])
    p.overlays=[Overlay(shot_id=p.shots[0].id)]
    storage.create(p)
    import io
    r=client.get(f'/api/v1/projects/{p.id}/overlays/{p.overlays[0].id}.png')
    actual=Image.open(io.BytesIO(r.content))
    assert actual.mode=='RGBA'
    assert ImageChops.difference(actual,graphics.panel(p,p.overlays[0])).getbbox() is None


@pytest.mark.skipif(not shutil.which('ffmpeg'),reason='FFmpeg required')
def test_real_export_audio_timing_and_graphics(client,tmp_path):
    source=tmp_path/'synthetic.mp4'
    subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','color=c=0x203040:s=480x270:r=24:d=2',
        '-f','lavfi','-i','sine=frequency=440:sample_rate=48000:duration=2','-c:v','libx264','-pix_fmt','yuv420p','-c:a','aac','-shortest',str(source)],check=True)
    p=client.post('/api/v1/projects',json={}).json()['project']
    with source.open('rb') as f:r=client.post(f"/api/v1/projects/{p['id']}/video",files={'file':('clip.mp4',f,'video/mp4')})
    assert r.status_code==200,r.text
    p=r.json()['project'];assert p['video']['has_audio']
    s=Shot(hole=1,number=7,start=.5,end=1.5)
    o=Overlay(shot_id=s.id,start=.5,end=1.5,style=Style(background="#122d24",color="#f4f8e8",accent="#b6d87d",opacity=.7,overlay_opacity=.6))
    card=Overlay(type='full',start=.5,end=1.5,style=Style(x=.04,y=.04,width=.50,height=.56,background='#f5f1e8',color='#20312d',accent='#166b59',overlay_opacity=.8))
    p['shots']=[s.model_dump()];p['overlays']=[o.model_dump(),card.model_dump()]
    p=client.put('/api/v1/projects/'+p['id'],json=p).json()['project']
    r=client.post(f"/api/v1/projects/{p['id']}/exports",json={'revision':p['revision'],'quality':'high','resolution':'source'})
    assert r.status_code==202,r.text
    jid=r.json()['id']
    for _ in range(200):
        job=next(j for j in client.get('/api/v1/jobs').json() if j['id']==jid)
        if job['status'] in ('done','error'):break
        time.sleep(.05)
    assert job['status']=='done',job
    result=storage.directory(p['id'])/f'{jid}.mp4'
    info=rendering.probe(result)
    assert info['has_audio'] and abs(info['duration']-2)<.15
    streams=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-of','json',str(result)]))['streams']
    audio=next(s for s in streams if s['codec_type']=='audio')
    video=next(s for s in streams if s['codec_type']=='video')
    assert video['codec_name']=='h264' and audio['codec_name']=='aac'
    assert abs(float(video.get('start_time',0))-float(audio.get('start_time',0)))<.05
    assert abs(float(video['duration'])-float(audio['duration']))<.15
    def frame(t):
        raw=subprocess.check_output(['ffmpeg','-v','error','-ss',str(t),'-i',str(result),'-frames:v','1','-f','rawvideo','-pix_fmt','rgb24','pipe:1'])
        return Image.frombytes('RGB',(480,270),raw)
    before,during,after=frame(.2),frame(1),frame(1.8)
    assert ImageChops.difference(before,during).getbbox() is not None
    # Exact overlay composition against source at the same resolution, allowing H.264 loss.
    expected=before.convert('RGBA')
    for overlay in (o,card):
        panel=graphics.panel(Project.model_validate(p),overlay).resize((round(overlay.style.width*480),round(overlay.style.height*270)))
        expected.alpha_composite(panel,(round(overlay.style.x*480),round(overlay.style.y*270)))
    from PIL import ImageStat
    difference=ImageStat.Stat(ImageChops.difference(expected.convert('RGB'),during)).mean
    assert max(difference)<6
    assert max(ImageStat.Stat(ImageChops.difference(before,after)).mean)<2
    assert client.get('/api/v1/jobs/'+jid+'/download').status_code==200


def test_restart_marks_interrupted_jobs_failed(client):
    storage.job_put(dict(id='j',project_id='none',status='running',progress=.2))
    rendering.recover()
    assert storage.jobs()[0]['status']=='error'


def test_portrait_panel_preserves_video_aspect():
    from golf_video_studio.models import Video
    shot = Shot(hole=1)
    overlay = Overlay(shot_id=shot.id)
    p = Project(shots=[shot], overlays=[overlay], video=Video(filename='portrait.mp4', duration=10, width=1080, height=1920, fps=30, has_audio=False))
    image = graphics.panel(p, overlay)
    expected = overlay.style.width * 1080 / (overlay.style.height * 1920)
    assert abs(image.width / image.height - expected) < .01


def test_manual_numbers_override_display_without_affecting_automatic_order(client):
    a,b,c=Shot(hole=1),Shot(hole=1,number=7),Shot(hole=1)
    p=Project(shots=[a,b,c])
    assert numbered_shots(p)=={a.id:1,b.id:7,c.id:3}
    p.shots.reverse()
    assert numbered_shots(p)=={c.id:1,b.id:7,a.id:3}
    storage.create(p)
    loaded=storage.load(p.id)
    assert numbered_shots(loaded)[b.id]==7
    loaded.shots[1].number=None
    assert numbered_shots(loaded)[b.id]==2
    for number in (0,100):
        with pytest.raises(ValidationError):Shot(hole=1,number=number)


def test_legacy_style_and_global_transparency():
    legacy=Style.model_validate({'opacity':.5})
    assert legacy.overlay_opacity==1
    p=Project(shots=[Shot(hole=1)])
    o=Overlay(shot_id=p.shots[0].id,style=Style(opacity=.8,overlay_opacity=.5))
    image=graphics.panel(p,o)
    assert image.getchannel('A').getextrema()[1]==128
    assert image.getpixel((image.width-25,image.height-25))[3]==102
    o.style.overlay_opacity=0
    assert graphics.panel(p,o).getchannel('A').getbbox() is None
    o.style.overlay_opacity=1
    o.style.opacity=0
    assert graphics.panel(p,o).getchannel('A').getextrema()[1]==255
    with pytest.raises(ValidationError):Style(overlay_opacity=1.1)
