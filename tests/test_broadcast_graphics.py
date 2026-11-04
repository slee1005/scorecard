from __future__ import annotations

import pytest
from PIL import Image, ImageChops, ImageDraw

from golf_video_studio import graphics, snapshots
from golf_video_studio.models import Hole, Overlay, Project, Round, Shot, Style, Video


@pytest.mark.parametrize('par,score', [(4,2),(5,4),(4,5),(4,6),(4,10),(4,40),(None,None)])
@pytest.mark.parametrize('family', ['sans','serif','mono'])
def test_glyph_ink_and_score_mark_share_the_same_center(par,score,family):
    image=Image.new('RGBA',(101,101))
    graphics.score_symbol(ImageDraw.Draw(image),(50,50),64,par,score,'#ffffff','#00ff00','#ff0000',family)
    # Examine the real rendered glyph pixels, rather than repeating the position formula.
    ink=Image.new('L',image.size)
    ink.putdata([255 if r>230 and g>230 and b>230 and a>100 else 0 for r,g,b,a in image.get_flattened_data()])
    box=ink.getbbox()
    assert box is not None
    assert abs((box[0]+box[2]-1)/2-50)<=1
    assert abs((box[1]+box[3]-1)/2-50)<=1
    if par is not None and score!=par:
        marker=Image.new('L',image.size)
        marker.putdata([255 if a and (r>230 and g<20 and b<20 or r<20 and g>230 and b<20) else 0 for r,g,b,a in image.get_flattened_data()])
        bounds=marker.getbbox()
        assert bounds is not None
        assert (bounds[0]+bounds[2]-1)/2==50
        assert (bounds[1]+bounds[3]-1)/2==50


def project():
    pars=[4,5,4,4,4,5,3,3,4,4,4,4,3,5,4,3,5,4]
    scores=[4,4,4,5,4,4,2,3,6,4,4,3,3,3,5,3,4,5]
    holes=[Hole(number=i+1,par=par,score=score,yardage=405 if i==4 else 350) for i,(par,score) in enumerate(zip(pars,scores))]
    return Project(round=Round(player='JOHN LEE',course='Synthetic Club',tee='Blue',holes=holes),shots=[Shot(hole=5,number=2,club='7 Iron',remaining=145)])


def test_shot_uses_real_round_name_score_total_hole_length_club_and_remaining(monkeypatch):
    p=project()
    values=[]
    original=graphics.centered_text
    def record(draw,box,value,*args,**kwargs):
        values.append(str(value))
        return original(draw,box,value,*args,**kwargs)
    monkeypatch.setattr(graphics,'centered_text',record)
    graphics.panel(p,Overlay(shot_id=p.shots[0].id))
    assert {'JOHN LEE','E','05','PAR 4','405 YDS','2','7 IRON','145 YDS'} <= set(values)
    # The hole total must not be replaced by the distance of this individual shot.
    p.shots[0].distance=999
    values.clear()
    graphics.panel(p,Overlay(shot_id=p.shots[0].id))
    assert '405 YDS' in values and '999 YDS' not in values


def test_full_scorecard_rows_have_exactly_nine_shared_column_centers(monkeypatch):
    p=project()
    centers=[]
    original=graphics.score_symbol
    def record(draw,center,*args,**kwargs):
        centers.append(center)
        return original(draw,center,*args,**kwargs)
    monkeypatch.setattr(graphics,'score_symbol',record)
    snap=snapshots.capture(p,0)
    p.snapshots[snap.id]=snap
    graphics.panel(p,Overlay(type='full',snapshot_id=snap.id,style=Style(x=.04,y=.04,width=.5,height=.56)))
    centers=[center for center in centers if center[1] < .8 * round(.56 * 1080)]
    assert len(centers)==18
    assert [x for x,y in centers[:9]]==[x for x,y in centers[9:]]
    assert len({y for x,y in centers[:9]})==len({y for x,y in centers[9:]})==1
    assert centers[0][1]<centers[9][1]


@pytest.mark.parametrize('kind', ['shot','minimal','full','front','back'])
@pytest.mark.parametrize('dimensions',[(1920,1080),(1080,1920)])
def test_layouts_are_rgba_nonempty_and_respect_overall_transparency(kind,dimensions):
    p=project()
    p.video=Video(filename='test.mp4',duration=10,width=dimensions[0],height=dimensions[1],fps=30,has_audio=False)
    style=Style(x=.04,y=.04,width=.7,height=.5,color='#20312d',background='#f5f1e8',accent='#166b59')
    o=Overlay(type=kind,shot_id=p.shots[0].id if kind in ('shot','minimal') else None,style=style)
    if kind in ('full','front','back'):
        snap=snapshots.capture(p,0)
        p.snapshots[snap.id]=snap
        o.snapshot_id=snap.id
    image=graphics.panel(p,o)
    assert image.mode=='RGBA' and image.getchannel('A').getbbox() is not None
    o.style.overlay_opacity=0
    assert graphics.panel(p,o).getchannel('A').getbbox() is None


def test_missing_round_values_are_not_rendered_as_even_par(monkeypatch):
    p=Project(shots=[Shot(hole=2)])
    values=[]
    monkeypatch.setattr(graphics,'centered_text',lambda draw,box,value,*a,**kw:values.append(str(value)))
    graphics.panel(p,Overlay(shot_id=p.shots[0].id))
    assert 'E' not in values and '—' in values and '— YDS' in values


def test_shot_score_excludes_current_and_later_holes_and_reacts_to_prior_corrections():
    p=project();overlay=Overlay(shot_id=p.shots[0].id)
    before=graphics.panel(p,overlay).tobytes()
    for h in p.round.holes[4:]:h.score=33
    assert graphics.panel(p,overlay).tobytes()==before
    p.round.holes[0].score=8
    assert graphics.panel(p,overlay).tobytes()!=before


@pytest.mark.parametrize('hole,expected',[(1,0),(2,0),(3,-1),(5,0),(18,-3)])
def test_score_before_each_shot_hole(hole,expected):
    from golf_video_studio.models import score_before_hole
    assert score_before_hole(project(),hole)==expected


@pytest.mark.parametrize('field',['par','score'])
def test_missing_prior_values_leave_cumulative_shot_score_unknown(field):
    from golf_video_studio.models import score_before_hole
    p=project();setattr(p.round.holes[1],field,None)
    assert score_before_hole(p,5) is None
    assert score_before_hole(p,1)==0
    assert score_before_hole(p,2)==0


def test_broadcast_places_remaining_above_total_and_enlarges_requested_text(monkeypatch):
    p=project();values={}
    original=graphics.centered_text
    def record(draw,box,value,size,*args,**kwargs):
        values[str(value)]=(box,size)
        return original(draw,box,value,size,*args,**kwargs)
    monkeypatch.setattr(graphics,'centered_text',record)
    graphics.panel(p,Overlay(shot_id=p.shots[0].id,style=Style(width=.5,height=.3,y=.05)))
    remaining,remaining_size=values['145 YDS'];total,total_size=values['405 YDS']
    assert remaining[3]<total[1] and remaining_size>total_size
    assert values['LEFT'][0][3]<remaining[1]
    assert values['TOTAL'][0][3]<total[1]
    # At the design scale these requests are substantially larger than old 10–11px labels.
    k=min(.5*1920/620,.3*1080/254)
    for label,minimum in [('HOLE',20),('LEFT',20),('TO PAR',18),('PAR 4',22),('CLUB',18),('7 IRON',28)]:
        assert values[label][1]>=minimum*k-.01


@pytest.mark.parametrize('family',['sans','serif','mono'])
@pytest.mark.parametrize('font_size',[12,30,48])
def test_broadcast_text_ink_stays_inside_its_assigned_regions(monkeypatch,family,font_size):
    p=project();p.round.player='A LONG PLAYER NAME';p.shots[0].club='3 Hybrid';p.shots[0].remaining=1500
    original=graphics.centered_text
    def check(draw,box,value,size,color,font_family='sans',align='center'):
        layer=Image.new('RGBA',(1200,1200))
        original(ImageDraw.Draw(layer),box,value,size,color,font_family,align)
        bounds=layer.getbbox()
        if bounds:
            assert bounds[0]>=box[0]-1 and bounds[1]>=box[1]-1
            assert bounds[2]<=box[2]+2 and bounds[3]<=box[3]+2
        return original(draw,box,value,size,color,font_family,align)
    monkeypatch.setattr(graphics,'centered_text',check)
    graphics.panel(p,Overlay(shot_id=p.shots[0].id,style=Style(x=.75,y=.03,width=.2,height=.15,font=family,font_size=font_size,radius=20)))
