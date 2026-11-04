from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from golf_video_studio import history, snapshots, storage
from golf_video_studio.api import app
from golf_video_studio.models import Overlay, Project, Shot, Style, Video, default_style


@pytest.mark.parametrize('kind',['shot','minimal','full','front','back'])
def test_requested_default_geometry_and_typography_fit_all_frames(kind):
    expected=(.75,.03,.2,.15) if kind in ('shot','minimal') else (.24,.2,.504,.56)
    for width,height in ((1920,1080),(1080,1920)):
        p=Project(video=Video(filename='test.mp4',width=width,height=height,duration=30,fps=24,has_audio=False))
        s=history.shot_style(p) if kind in ('shot','minimal') else snapshots.card_style(p,kind)
        assert (s.x,s.y,s.width,s.height)==expected
        assert (s.font_size,s.radius,s.font,s.panel,s.show_course)==(30,20,'sans',True,True)
        assert s.x+s.width<=1 and s.y+s.height<=1


def test_new_card_and_design_reset_use_defaults_without_migrating_saved_styles(tmp_path,monkeypatch):
    monkeypatch.setenv('GVS_HOME',str(tmp_path/'home'))
    old=Style(x=.04,y=.68,width=.42,height=.25,font_size=24,radius=14)
    shot=Shot(hole=1,start=0,end=5)
    p=Project(shots=[shot],overlays=[Overlay(shot_id=shot.id,style=old,start=0,end=5)],
        video=Video(filename='test.mp4',width=1920,height=1080,duration=30,fps=24,has_audio=False))
    storage.create(p)
    with TestClient(app) as c:
        assert storage.load(p.id).overlays[0].style==old
        r=c.post(f'/api/v1/projects/{p.id}/scorecard-snapshots',json={'revision':p.revision,'timeline_position':10})
        assert r.status_code==201,r.text
        value=r.json()['project']
        assert Style.model_validate(value['overlays'][1]['style'])==default_style('full')
        assert Style.model_validate(value['overlays'][0]['style'])==old
        r=c.post(f'/api/v1/projects/{p.id}/history',json={'revision':value['revision'],'scope':'design','action':'reset','confirm_reset':True})
        assert r.status_code==200,r.text
        value=r.json()['project']
        assert Style.model_validate(value['overlays'][0]['style'])==default_style('shot')
        r=c.post(f'/api/v1/projects/{p.id}/history',json={'revision':value['revision'],'scope':'design','action':'undo'})
        assert r.status_code==200,r.text
        assert Style.model_validate(r.json()['project']['overlays'][0]['style'])==old
