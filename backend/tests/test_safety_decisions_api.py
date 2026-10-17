"""CR-104 decision guards, readiness, validation and private notification text."""
from copy import deepcopy
import pytest
from app.modules.events import repository
from app.modules.events.schemas import BookingReadiness
from app.modules.venues import service as venues
from app.modules.equipment import service as equipment
from tests.test_event_review_api import event_row, EVENT_ID, COORDINATOR_ID
from tests.test_event_comments_api import acting_as_another_role

BOOKING='b0000000-0000-4000-8000-000000000001'
LINE='b0000000-0000-4000-8000-000000000002'
FOREIGN='b0000000-0000-4000-8000-000000000099'
CASES=[('safety-approve',{'comment':'  PRIVATE-MARKER  '},'confirmed'),
       ('safety-request-changes',{'comment':'  PRIVATE-MARKER  ','booking_ids':[BOOKING,BOOKING],'equipment_request_ids':[LINE,LINE]},'planning'),
       ('safety-reject',{'reason':'  PRIVATE-MARKER  ','booking_ids':[BOOKING],'equipment_request_ids':[LINE]},'planning')]
ROLES=['event_organiser','event_coordinator','venue_staff','tech_support','attendee','event_coordinator_lead']

@pytest.fixture()
def state(monkeypatch):
    state={'event':event_row('safety_review'),'bookings':['approved'],'calls':[],'stale':False,'race':False}
    monkeypatch.setattr(repository,'get_event',lambda _:deepcopy(state['event']))
    monkeypatch.setattr(venues,'booking_readiness_by_event',lambda ids:{EVENT_ID:[BookingReadiness(status=s) for s in state['bookings']]})
    monkeypatch.setattr(venues,'event_booking_ids',lambda _: {BOOKING},raising=False)
    monkeypatch.setattr(equipment,'event_request_ids',lambda _: {LINE},raising=False)
    def rpc(*args,**kwargs):
        state['calls'].append((args,kwargs))
        if state['race']: state['bookings']=[]
        if state['stale']: return None
        state['event'].update(status='confirmed' if 'organiser_message' in kwargs else 'planning',version=4)
        return deepcopy(state['event'])
    monkeypatch.setattr(repository,'safety_approve',rpc)
    monkeypatch.setattr(repository,'safety_return',rpc)
    return state

def post(client,headers,path,body): return client.post(f'/api/v1/events/{EVENT_ID}/{path}',headers=headers,json=body)

@pytest.mark.parametrize('path,body,target',CASES)
def test_decision_and_repeat(client,auth_headers,authenticate_as,state,path,body,target):
    authenticate_as('safety_officer',COORDINATOR_ID)
    result=post(client,auth_headers,path,body)
    assert result.status_code==200
    assert result.json()['status']==target and result.json()['latest_safety_decision'] is None
    args,kwargs=state['calls'][0]
    assert args==(EVENT_ID,COORDINATOR_ID,3)
    assert kwargs['comment']=='PRIVATE-MARKER'
    messages=[v for k,v in kwargs.items() if k.endswith('message')]
    assert messages and all('Partner Summit' in m and 'PRIVATE-MARKER' not in m for m in messages)
    if target=='planning':
        assert kwargs['booking_ids']==[BOOKING] and kwargs['equipment_request_ids']==[LINE]
        assert kwargs['decision']==('changes_requested' if path=='safety-request-changes' else 'arrangement_rejected')
    assert post(client,auth_headers,path,body).status_code==409
    assert len(state['calls'])==1

@pytest.mark.parametrize('path,body,target',CASES)
@pytest.mark.parametrize('status',['draft','submitted','under_review','returned','planning','confirmed','rejected','cancelled','completed',None])
def test_wrong_status(client,auth_headers,authenticate_as,state,path,body,target,status):
    authenticate_as('safety_officer')
    state['event']=event_row(status) if status else None
    result=post(client,auth_headers,path,body)
    assert result.status_code==(404 if status in ('draft',None) else 409)
    if result.status_code==409: assert result.json()['detail']==f"Cannot {path.replace('-',' ')} an event that is {status.replace('_',' ')}"
    assert not state['calls']

@pytest.mark.parametrize('path,body,target',CASES)
@pytest.mark.parametrize('role',ROLES)
def test_decision_roles(client,auth_headers,authenticate_as,state,path,body,target,role):
    authenticate_as(role)
    assert post(client,auth_headers,path,body).status_code==403
    assert not state['calls']

@pytest.mark.parametrize('path,body,target',CASES)
def test_active_role_denied(client,auth_headers,monkeypatch,state,path,body,target):
    acting_as_another_role(monkeypatch,COORDINATOR_ID,'safety_officer','event_coordinator')
    assert post(client,auth_headers,path,body).status_code==403

@pytest.mark.parametrize('path,body,target',CASES)
def test_stale(client,auth_headers,authenticate_as,state,path,body,target):
    authenticate_as('safety_officer')
    state['stale']=True
    result=post(client,auth_headers,path,body)
    assert result.status_code==409 and result.json()['detail']=='This event was updated by someone else. Reload.'

@pytest.mark.parametrize('race',[False,True])
def test_not_ready(client,auth_headers,authenticate_as,state,race):
    authenticate_as('safety_officer')
    if race: state.update(stale=True,race=True)
    else: state['bookings']=[]
    result=post(client,auth_headers,'safety-approve',{})
    assert result.status_code==409
    assert result.json()['detail']=='Not ready for approval: No venue booking is approved.'
    assert len(state['calls'])==(1 if race else 0)

@pytest.mark.parametrize('path,body,target',CASES)
@pytest.mark.parametrize('text',['','   ','x'*1001])
def test_invalid_text(client,auth_headers,authenticate_as,state,path,body,target,text):
    authenticate_as('safety_officer')
    body={**body,('reason' if path=='safety-reject' else 'comment'):text}
    assert post(client,auth_headers,path,body).status_code==422
    assert not state['calls']

@pytest.mark.parametrize('path',['safety-request-changes','safety-reject'])
@pytest.mark.parametrize('field',['booking_ids','equipment_request_ids'])
def test_foreign_ids(client,auth_headers,authenticate_as,state,path,field):
    authenticate_as('safety_officer')
    result=post(client,auth_headers,path,{('reason' if path=='safety-reject' else 'comment'):'private',field:[FOREIGN]})
    assert result.status_code==422 and result.json()['detail']=='Unknown booking or equipment line for this event'
    assert not state['calls']


def test_approve_body_optional(client,auth_headers,authenticate_as,state):
    authenticate_as('safety_officer')
    assert client.post(f'/api/v1/events/{EVENT_ID}/safety-approve',headers=auth_headers).status_code==200
    assert state['calls'][0][1]['comment'] is None

@pytest.mark.parametrize('path,body,target',CASES)
@pytest.mark.parametrize('seam',['get_event','rpc'])
def test_decision_outage_is_503(client,auth_headers,authenticate_as,state,monkeypatch,path,body,target,seam):
    from postgrest.exceptions import APIError
    authenticate_as('safety_officer')
    def unavailable(*a,**k): raise APIError({'message':'offline','code':'PGRST000','details':None,'hint':None})
    name='get_event' if seam=='get_event' else ('safety_approve' if path=='safety-approve' else 'safety_return')
    monkeypatch.setattr(repository,name,unavailable)
    response=post(client,auth_headers,path,body)
    assert response.status_code==503
    assert response.json()['detail']=='The event service is temporarily unavailable. Please try again.'
