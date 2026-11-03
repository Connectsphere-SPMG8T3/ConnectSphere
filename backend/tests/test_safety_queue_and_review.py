"""CR-103 private review reads and CR-104 organiser-safe decision summaries."""
from copy import deepcopy
import pytest
import httpx
from app.modules.events import repository
from app.modules.events.schemas import BookingReadiness
from app.modules.venues import service as venues
from app.modules.equipment import service as equipment
from tests.test_event_review_api import event_row,EVENT_ID,COORDINATOR_ID,ORGANISER_ID
from tests.test_event_comments_api import acting_as_another_role
from tests.test_safety_decisions_api import ROLES, BOOKING, LINE

CHECKLIST=[{'factor':'layout','booking_id':BOOKING,'rating':'concern','note':'PRIVATE-NOTE-ON-LAYOUT'},
           {'factor':'equipment_placement','booking_id':None,'rating':'satisfactory','note':None}]
DECISION={'id':BOOKING,'decision':'changes_requested','comment':'PRIVATE-LEAK-MARKER','organiser_comment':'ORGANISER-MARKER',
          'checklist':CHECKLIST,'reason_code':None,
          'affected_booking_ids':[BOOKING],'affected_equipment_request_ids':[LINE],'rejected_venue_ids':[],
          'decided_by_name':'Officer','decided_at':'2026-10-09T01:00:00Z'}

@pytest.fixture()
def state(monkeypatch):
    for name in ('booking_venue_names','venue_names'):
        monkeypatch.setattr(venues,name,lambda _: {},raising=False)
    monkeypatch.setattr(venues,'safety_revisions',lambda _: [],raising=False)
    monkeypatch.setattr(equipment,'line_names',lambda _: {},raising=False)
    state={'event':event_row('safety_review'),'decisions':[deepcopy(DECISION)],'queue':[]}
    state['event'].update(organiser={'full_name':'Organiser'},coordinator={'id':COORDINATOR_ID,'full_name':'Coordinator'})
    monkeypatch.setattr(repository,'get_event',lambda _:deepcopy(state['event']))
    monkeypatch.setattr(repository,'list_safety_decisions',lambda _:deepcopy(state['decisions']),raising=False)
    monkeypatch.setattr(repository,'list_safety_queue',lambda:deepcopy(state['queue']),raising=False)
    monkeypatch.setattr(repository,'list_status_history',lambda _:[])
    monkeypatch.setattr(repository,'list_assignment_history',lambda _:[])
    monkeypatch.setattr(repository,'list_events',lambda _:[deepcopy(state['event'])])
    monkeypatch.setattr(repository,'list_comments',lambda _:[])
    monkeypatch.setattr(venues,'active_booking_for_event',lambda _:None)
    monkeypatch.setattr(venues,'booking_readiness_by_event',lambda _:{EVENT_ID:[BookingReadiness(status='approved')]})
    monkeypatch.setattr(venues,'event_bookings_with_venues',lambda _:[dict(booking_id=BOOKING,venue_id=LINE,venue_name='Hall',booking_status='approved',capacity=24,layouts=['boardroom'],accessibility_features=['ramp'])],raising=False)
    monkeypatch.setattr(equipment,'event_lines',lambda _:[dict(id=LINE,equipment_name='Mic',quantity=2,status='pending')],raising=False)
    monkeypatch.setattr(equipment,'exit_confirmation',lambda _:state.get('exit'))
    return state

GETS=['/api/v1/events/safety-queue',f'/api/v1/events/{EVENT_ID}/safety-review',f'/api/v1/events/{EVENT_ID}/safety-decisions']
@pytest.mark.parametrize('url',GETS)
@pytest.mark.parametrize('role',ROLES)
def test_read_guards(client,auth_headers,authenticate_as,state,url,role):
    authenticate_as(role,COORDINATOR_ID)
    result=client.get(url,headers=auth_headers)
    assert result.status_code==(200 if role=='event_coordinator' and url.endswith('safety-decisions') else 403)

@pytest.mark.parametrize('url',GETS)
def test_active_role_read_denial(client,auth_headers,monkeypatch,state,url):
    acting_as_another_role(monkeypatch,COORDINATOR_ID,'safety_officer','event_organiser')
    assert client.get(url,headers=auth_headers).status_code==403

@pytest.mark.parametrize('attendance,capacity,ratio',[(12,24,.5),(12,0,None),(None,24,None)])
def test_review_shape(client,auth_headers,authenticate_as,state,monkeypatch,attendance,capacity,ratio):
    authenticate_as('safety_officer')
    state['event']['expected_attendance']=attendance
    monkeypatch.setattr(venues,'event_bookings_with_venues',lambda _:[dict(booking_id=BOOKING,venue_id=LINE,venue_name='Hall',booking_status='approved',capacity=capacity,layouts=['boardroom'],accessibility_features=['ramp'])])
    result=client.get(GETS[1],headers=auth_headers)
    assert result.status_code==200
    data=result.json()
    assert data['event']==dict(id=EVENT_ID,name='Partner Summit',organiser_name='Organiser',coordinator_name='Coordinator',starts_at='2026-11-12T10:00:00+08:00',ends_at='2026-11-12T12:00:00+08:00',expected_attendance=attendance,accessibility_needs=None,registration=dict(enabled=False,capacity=None,opens_at=None,closes_at=None))
    assert data['exit_confirmation'] is None
    assert data['venues'][0]['attendance_to_capacity']==ratio
    assert data['venues'][0]['emergency_access'] is data['venues'][0]['restrictions'] is None
    assert data['equipment_lines']==[dict(id=LINE,equipment_name='Mic',quantity=2,status='pending')]
    assert data['decisions'][0]['private_note']=='PRIVATE-LEAK-MARKER'
    assert data['decisions'][0]['organiser_comment']=='ORGANISER-MARKER'

@pytest.mark.parametrize('status',[None,'draft','planning','confirmed'])
def test_review_not_found(client,auth_headers,authenticate_as,state,status):
    authenticate_as('safety_officer')
    state['event']=event_row(status) if status else None
    assert client.get(GETS[1],headers=auth_headers).status_code==404

@pytest.mark.parametrize('role,uid,code',[('safety_officer','other',200),('event_coordinator',COORDINATOR_ID,200),('event_coordinator','other',403)])
def test_decisions_relationship(client,auth_headers,authenticate_as,state,role,uid,code):
    authenticate_as(role,uid)
    result=client.get(GETS[2],headers=auth_headers)
    assert result.status_code==code
    if code==200:
        assert result.json()[0]['private_note']=='PRIVATE-LEAK-MARKER'
        assert result.json()[0]['organiser_comment']=='ORGANISER-MARKER'
        assert [(c['factor'],c['rating'],c['note']) for c in result.json()[0]['checklist']]==[('layout','concern','PRIVATE-NOTE-ON-LAYOUT'),('equipment_placement','satisfactory',None)]

@pytest.mark.parametrize('role',['event_organiser','event_coordinator'])
@pytest.mark.parametrize('status',['planning','safety_review','confirmed','under_review','cancelled'])
def test_latest_decision_visibility(client,auth_headers,authenticate_as,state,role,status):
    authenticate_as(role,ORGANISER_ID if role=='event_organiser' else COORDINATOR_ID)
    state['event']['status']=status
    result=client.get(f'/api/v1/events/{EVENT_ID}',headers=auth_headers)
    assert result.status_code==200
    latest=result.json().get('latest_safety_decision','MISSING')
    if role=='event_coordinator' and status=='planning':
        assert latest['private_note']=='PRIVATE-LEAK-MARKER' and latest['organiser_comment']=='ORGANISER-MARKER'
    elif role=='event_organiser' and status in ('planning','safety_review','confirmed'):
        assert latest==dict(decision='changes_requested',reason_label='The Safety Officer asked for changes to the arrangements.',organiser_comment='ORGANISER-MARKER',decided_at='2026-10-09T01:00:00Z')
    else: assert latest is None
    if role=='event_organiser':
        for url in [f'/api/v1/events/{EVENT_ID}',f'/api/v1/events/{EVENT_ID}/history',f'/api/v1/events/{EVENT_ID}/comments','/api/v1/events']:
            text=client.get(url,headers=auth_headers).text
            # AC5: the private note and the checklist (with its notes) never reach the organiser, by any route.
            assert 'PRIVATE-LEAK-MARKER' not in text and 'PRIVATE-NOTE-ON-LAYOUT' not in text and 'private_note' not in text


def test_queue_order_and_empty(client,auth_headers,authenticate_as,state):
    authenticate_as('safety_officer')
    response=client.get(GETS[0],headers=auth_headers)
    assert response.status_code==200 and response.json()=={'items':[]}
    state['queue']=[dict(event_id=id,name=id,organiser_name='Org',starts_at=None,expected_attendance=12,entered_review_at=time) for id,time in [('c','2026-10-09T03:00:00Z'),('b','2026-10-09T01:00:00Z'),('a','2026-10-09T01:00:00Z')]]
    assert [x['event_id'] for x in client.get(GETS[0],headers=auth_headers).json()['items']]==['a','b','c']

@pytest.mark.parametrize('url',GETS)
def test_read_outage_is_503(client,auth_headers,authenticate_as,state,monkeypatch,url):
    authenticate_as('safety_officer')
    def unavailable(*a): raise httpx.ConnectError('offline')
    monkeypatch.setattr(repository,'get_event',unavailable)
    monkeypatch.setattr(repository,'list_safety_queue',unavailable)
    result=client.get(url,headers=auth_headers)
    assert result.status_code==503
    assert result.json()['detail']=='The event service is temporarily unavailable. Please try again.'

@pytest.mark.parametrize('decision,label',[
 ('approved','Approved by the Safety Officer.'),
 ('arrangement_rejected','The Safety Officer rejected a venue for this event; its booking is flagged Safety rejected.'),
 ('withdrawn','An arrangement changed, so the event went back to planning.'),
])
def test_each_organiser_label_is_private(client,auth_headers,authenticate_as,state,decision,label):
    authenticate_as('event_organiser',ORGANISER_ID)
    state['event']['status']='planning'
    state['decisions'][0]['decision']=decision
    response=client.get(f'/api/v1/events/{EVENT_ID}',headers=auth_headers)
    assert response.status_code==200
    assert response.json()['latest_safety_decision']['reason_label']==label
    assert 'PRIVATE-LEAK-MARKER' not in response.text and 'PRIVATE-NOTE-ON-LAYOUT' not in response.text


def test_no_decision_leaves_latest_null(client,auth_headers,authenticate_as,state):
    authenticate_as('event_coordinator',COORDINATOR_ID)
    state['event']['status']='planning'
    state['decisions']=[]
    assert client.get(f'/api/v1/events/{EVENT_ID}',headers=auth_headers).json()['latest_safety_decision'] is None


def test_internal_decisions_service_denies_other_roles(state):
    from app.modules.events import service
    from app.core.exceptions import NotAssignedCoordinatorError
    with pytest.raises(NotAssignedCoordinatorError): service.safety_decisions(EVENT_ID,ORGANISER_ID,'event_organiser')


@pytest.mark.parametrize('status',[None,'draft'])
def test_decisions_missing_or_draft(client,auth_headers,authenticate_as,state,status):
    authenticate_as('safety_officer')
    state['event']=event_row(status) if status else None
    assert client.get(GETS[2],headers=auth_headers).status_code==404


def test_event_read_outage_is_503(client,auth_headers,authenticate_as,state,monkeypatch):
    authenticate_as('event_organiser',ORGANISER_ID)
    state['event']['status']='planning'
    def unavailable(*a): raise httpx.ReadTimeout('offline')
    monkeypatch.setattr(repository,'list_safety_decisions',unavailable)
    assert client.get(f'/api/v1/events/{EVENT_ID}',headers=auth_headers).status_code==503


def test_review_shows_who_ticked_the_exit_box_and_when(client,auth_headers,authenticate_as,state):
    """SCRUM-24 AC10 on CR-103 AC3's page."""
    from app.modules.equipment.schemas import ExitConfirmation
    authenticate_as('safety_officer')
    state['exit']=ExitConfirmation(confirmed_by_name='Tan Wei',confirmed_at='2026-10-19T03:00:00Z')
    data=client.get(GETS[1],headers=auth_headers).json()
    assert data['exit_confirmation']=={'confirmed_by_name':'Tan Wei','confirmed_at':'2026-10-19T03:00:00Z'}


def test_the_organiser_gets_no_comment_for_a_decision_recorded_before_organiser_comments(client,auth_headers,authenticate_as,state):
    authenticate_as('event_organiser',ORGANISER_ID)
    state['event']['status']='planning'
    del state['decisions'][0]['organiser_comment']
    latest=client.get(f'/api/v1/events/{EVENT_ID}',headers=auth_headers).json()['latest_safety_decision']
    assert latest['organiser_comment'] is None
