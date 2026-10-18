"""CR-104 AC3/AC4: coordinator revision, assignment and active-role guards."""
from types import SimpleNamespace
import pytest
from app.modules.venues import repository as venues_repository
from tests.test_venue_booking_reject_api import BOOKING_ID, COORDINATOR_ID, URL, bookings  # noqa: F401
from tests.test_event_comments_api import acting_as_another_role

REVISE_URL = f'{URL}/mark-revised'

@pytest.fixture()
def revising(bookings, monkeypatch):
    bookings['booking'].update(status='approved',flag='safety_rejected',flag_reason='Exits blocked')
    bookings['revisions']=[]
    def mark(booking_id,actor_id):
        bookings['revisions'].append((booking_id,actor_id))
        if bookings['outcome']=='ok':
            bookings['booking'].update(flag=None,flag_reason=None)
        return bookings['outcome']
    monkeypatch.setattr(venues_repository,'mark_safety_revision',mark,raising=False)
    return bookings

def test_assigned_coordinator_marks_revised_and_sees_it_unflagged(client,auth_headers,authenticate_as,revising):
    authenticate_as('event_coordinator',user_id=COORDINATOR_ID)
    response=client.post(REVISE_URL,headers=auth_headers)
    assert response.status_code==200
    assert revising['revisions']==[(BOOKING_ID,COORDINATOR_ID)]
    assert response.json()['flag'] is None and response.json()['flag_reason'] is None

@pytest.mark.parametrize('outcome,status,detail',[
    ('booking_not_found',404,None),('not_assigned',403,None),
    ('not_safety_rejected',409,"This booking isn't flagged Safety rejected."),
    ('not_planning',409,'A booking can be marked revised only while the event is in Planning.')])
def test_outcomes_map_to_status(client,auth_headers,authenticate_as,revising,outcome,status,detail):
    authenticate_as('event_coordinator',user_id=COORDINATOR_ID)
    revising['outcome']=outcome
    response=client.post(REVISE_URL,headers=auth_headers)
    assert response.status_code==status
    if detail: assert response.json()['detail']==detail
    assert revising['booking']['flag']=='safety_rejected'

@pytest.mark.parametrize('role',['venue_staff','safety_officer','event_organiser','tech_support','attendee','event_coordinator_lead'])
def test_other_active_roles_are_denied(client,auth_headers,authenticate_as,revising,role):
    authenticate_as(role)
    assert client.post(REVISE_URL,headers=auth_headers).status_code==403
    assert not revising['revisions']

def test_holding_coordinator_role_but_acting_as_venue_staff_is_denied(client,auth_headers,monkeypatch,revising):
    acting_as_another_role(monkeypatch,COORDINATOR_ID,holds='event_coordinator',acts_as='venue_staff')
    assert client.post(REVISE_URL,headers=auth_headers).status_code==403
    assert not revising['revisions']

def test_unauthenticated_is_401(client,revising):
    assert client.post(REVISE_URL).status_code==401
    assert not revising['revisions']

def test_repository_passes_booking_and_actor_and_returns_scalar(monkeypatch):
    calls=[]
    class Client:
        def rpc(self,name,params):
            calls.append((name,params))
            return SimpleNamespace(execute=lambda:SimpleNamespace(data='ok'))
    monkeypatch.setattr(venues_repository,'get_supabase_admin_client',lambda:Client())
    assert hasattr(venues_repository,'mark_safety_revision')
    assert venues_repository.mark_safety_revision(BOOKING_ID,COORDINATOR_ID)=='ok'
    assert calls==[('mark_safety_revision',{'p_booking_id':BOOKING_ID,'p_actor_id':COORDINATOR_ID})]
