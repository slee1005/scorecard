from __future__ import annotations

import copy
import json
import stat
from urllib.error import HTTPError, URLError

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from golf_video_studio import course_api, storage
from golf_video_studio.api import app


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv('GVS_HOME', str(tmp_path))
    monkeypatch.delenv('GOLFCOURSE_API_KEY', raising=False)
    with TestClient(app) as c:
        yield c


@pytest.fixture
def payload():
    # Synthetic provider-shaped data, not an actual course scorecard.
    tee = {'tee_name':'Blue','course_rating':71.2,'slope_rating':126,
           'total_yards':6400,'par_total':72,'number_of_holes':18,
           'holes':[{'par':4,'yardage':400,'handicap':n} for n in range(1,19)]}
    female = copy.deepcopy(tee)
    female['course_rating'] = 76.1
    female['slope_rating'] = 139
    return {'id':'7k2m9qb4','club_name':'Synthetic Club','course_name':'Synthetic Course',
            'location':{'city':'Test City','state':'Test State','country':'Test Country'},
            'tees':{'male':[tee], 'female':[female]}}


def set_key(client):
    response = client.put('/api/v1/course-provider/settings',json={'api_key':'synthetic-test-key'})
    assert response.status_code == 200
    return response


def test_key_saved_private_never_returned(client):
    assert client.get('/api/v1/course-provider/settings').json() == {'configured':False,'source':'none'}
    response = set_key(client)
    assert 'synthetic-test-key' not in response.text
    assert response.json() == {'configured':True,'source':'local'}
    path = storage.home()/'provider-settings.json'
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert course_api._key() == 'synthetic-test-key'
    assert 'synthetic-test-key' not in client.get('/api/v1/projects').text
    assert client.delete('/api/v1/course-provider/settings').json()['configured'] is False


def test_environment_key_takes_precedence(client,monkeypatch):
    set_key(client)
    monkeypatch.setenv('GOLFCOURSE_API_KEY','environment-key')
    assert course_api._key() == 'environment-key'
    assert client.get('/api/v1/course-provider/settings').json()['source'] == 'environment'
    assert client.put('/api/v1/course-provider/settings',json={'api_key':'new-key'}).status_code == 409
    assert client.delete('/api/v1/course-provider/settings').json()['configured'] is True
    assert course_api._local_key() == ''


def test_missing_invalid_keys_and_origin(client,monkeypatch):
    def forbidden(*a,**kw):
        raise AssertionError('No upstream request without a valid key')
    monkeypatch.setattr(course_api,'_download',forbidden)
    assert client.get('/api/v1/course-provider/search?q=test').status_code == 400
    for key in ('','  ','invalid key','key\r\nheader: bad'):
        assert client.put('/api/v1/course-provider/settings',json={'api_key':key}).status_code == 422
    assert client.put('/api/v1/course-provider/settings',json={'api_key':'key'},headers={'origin':'https://example.invalid'}).status_code == 403


def test_search_query_cache_and_request_count(client,monkeypatch):
    set_key(client)
    calls=[]
    def download(path,key):
        calls.append((path,key))
        return {'courses':[{'id':'7k2m9qb4','club_name':'Synthetic Club','course_name':'Synthetic Course',
                           'location':{'city':'Test'},'tees':{'male':2,'female':1}}]}
    monkeypatch.setattr(course_api,'_download',download)
    a=client.get('/api/v1/course-provider/search',params={'q':'Pine & Hill'})
    b=client.get('/api/v1/course-provider/search',params={'q':'Pine & Hill'})
    assert a.status_code == b.status_code == 200
    assert a.json()['items'][0]['tee_count']==3
    assert not a.json()['cached'] and b.json()['cached']
    assert len(calls)==1 and 'search_query=Pine+%26+Hill' in calls[0][0]
    assert client.get('/api/v1/course-provider/search?q=x').status_code==422


def test_detail_mapping_cache_refresh_and_round_integrity(client,monkeypatch,payload):
    set_key(client)
    calls=[]
    monkeypatch.setattr(course_api,'_download',lambda path,key:(calls.append(path) or copy.deepcopy(payload)))
    url='/api/v1/course-provider/courses/7k2m9qb4/import'
    course=client.post(url).json()
    assert course['source_name']=='GolfCourseAPI' and course['verification']=='imported'
    assert [t['category'] for t in course['tees']]==['male','female']
    assert course['tees'][1]['rating']==76.1 and course['tees'][0]['slope']==126
    assert course['tees'][0]['holes'][17]['handicap']==18
    assert client.post(url).json()['id']==course['id']
    assert len(calls)==1
    p=client.post('/api/v1/projects',json={}).json()['project']
    applied=client.post(f"/api/v1/projects/{p['id']}/course",json={'course_id':course['id'],'tee_id':course['tees'][1]['id'],'revision':0}).json()['project']
    payload['tees']['female'][0]['course_rating']=77.2
    refreshed=client.post(url+'?refresh=true').json()
    assert refreshed['id']!=course['id'] and len(calls)==2
    assert refreshed['tees'][1]['rating']==77.2
    assert storage.load(p['id']).round.rating==76.1
    assert storage.load(p['id']).round.reference.id==course['id']
    assert 'synthetic-test-key' not in json.dumps(applied)


def test_missing_holes_stay_unknown_and_invalid_details_not_saved(client,monkeypatch,payload):
    set_key(client)
    payload['tees']['male'][0]['holes']=payload['tees']['male'][0]['holes'][:9]
    course=course_api.normalize(payload,'7k2m9qb4')
    assert course.tees[0].holes[8].yardage==400
    assert course.tees[0].holes[9].yardage is None and course.tees[0].holes[9].par is None
    payload['tees']['male'][0]['holes'][0]['par']=999
    monkeypatch.setattr(course_api,'_download',lambda *a:payload)
    response=client.post('/api/v1/course-provider/courses/7k2m9qb4/import')
    assert response.status_code==502 and storage.courses()==[]
    assert storage.provider_cache_get('/v1/courses/7k2m9qb4') is None
    assert client.post('/api/v1/course-provider/courses/not-a-valid-id/import').status_code==422


@pytest.mark.parametrize('status,expected',[(401,'golf_api_unauthorized'),(403,'golf_api_forbidden'),(404,'golf_api_not_found'),(429,'golf_api_rate_limited'),(500,'golf_api_unavailable')])
def test_upstream_errors_sanitized(monkeypatch,status,expected):
    class Opener:
        def open(self,req,timeout):
            assert req.full_url=='https://api.golfcourseapi.com/v1/search?search_query=test'
            assert req.get_header('Authorization')=='Bearer secret-key'
            assert timeout==12
            raise HTTPError(req.full_url,status,'error with secret-key',{},None)
    monkeypatch.setattr(course_api,'build_opener',lambda *a:Opener())
    with pytest.raises(HTTPException) as error:
        course_api._download('/v1/search?search_query=test','secret-key')
    assert error.value.detail==expected
    assert 'secret-key' not in str(error.value)


def test_timeouts_and_redirects(monkeypatch):
    class Opener:
        def open(self,*a,**kw):raise URLError('secret-key')
    monkeypatch.setattr(course_api,'build_opener',lambda *a:Opener())
    with pytest.raises(HTTPException) as error:course_api._download('/v1/search?search_query=test','secret-key')
    assert error.value.detail=='golf_api_timeout'
    assert course_api._NoRedirect().redirect_request(None,None,302,'',{},'https://other.invalid') is None
