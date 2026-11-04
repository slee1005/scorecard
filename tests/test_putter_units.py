from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from golf_video_studio.api import app
from golf_video_studio import graphics, storage
from golf_video_studio.models import Hole, Overlay, Project, Round, Shot, remaining_display


@pytest.mark.parametrize('value,feet',[(None,None),(0,0),(10,30),(8/3,8),(4.1,12.3)])
def test_putter_remaining_conversion_preserves_stored_yards(value,feet):
    s=Shot(hole=1,club='Putter',remaining=value)
    assert remaining_display(s)==(feet,'FT')
    assert s.remaining==value
    restored=Shot.model_validate_json(s.model_dump_json())
    assert remaining_display(restored)==(feet,'FT')
    restored.club='7 Iron'
    assert remaining_display(restored)==(value,'YDS')


def test_putter_popup_uses_feet_only_for_remaining_and_keeps_total_yards(monkeypatch):
    s=Shot(hole=1,club='Putter',remaining=8/3,distance=5)
    p=Project(shots=[s],round=Round(holes=[Hole(number=n,par=4,yardage=405) for n in range(1,19)]))
    values=[]
    original=graphics.centered_text
    def record(draw,box,value,*args,**kwargs):
        values.append(str(value));return original(draw,box,value,*args,**kwargs)
    monkeypatch.setattr(graphics,'centered_text',record)
    graphics.panel(p,Overlay(shot_id=s.id))
    assert '8 FT' in values and '405 YDS' in values and 'PUTTER' in values
    assert '8 YDS' not in values
    values.clear();s.remaining=None
    graphics.panel(p,Overlay(shot_id=s.id));assert '— FT' in values
    values.clear();s.club='Driver';s.remaining=8/3
    graphics.panel(p,Overlay(shot_id=s.id));assert '2.66667 YDS' in values


def test_club_change_and_unit_entry_remain_undoable_without_migration(tmp_path,monkeypatch):
    monkeypatch.setenv('GVS_HOME',str(tmp_path/'home'))
    s=Shot(hole=1,club='7 Iron',remaining=10)
    p=storage.create(Project(shots=[s]))
    with TestClient(app) as c:
        raw=p.model_dump(mode='json');raw['shots'][0]['club']='Putter'
        r=c.put(f'/api/v1/projects/{p.id}',json=raw);assert r.status_code==200
        saved=r.json()['project'];assert remaining_display(Shot.model_validate(saved['shots'][0]))==(30,'FT')
        saved['shots'][0]['remaining']=8/3
        r=c.put(f'/api/v1/projects/{p.id}',json=saved);assert r.status_code==200
        r=c.post(f'/api/v1/projects/{p.id}/history',json={'revision':r.json()['project']['revision'],'scope':'shot','action':'undo'})
        assert r.status_code==200 and r.json()['project']['shots'][0]['remaining']==10
        r=c.post(f'/api/v1/projects/{p.id}/history',json={'revision':r.json()['project']['revision'],'scope':'shot','action':'undo'})
        assert r.status_code==200 and r.json()['project']['shots'][0]['club']=='7 Iron'
