"""CR-103/104 lifecycle, validation and RPC contracts."""
from uuid import UUID
import pytest
from pydantic import ValidationError
from app.modules.events import lifecycle, schemas, repository
from app.core.exceptions import EventTransitionError
from tests.test_events_repository import RpcClient

@pytest.mark.parametrize('status', list(schemas.EventStatus))
def test_approved_change_only_from_confirmed(status):
    assert 'approved_change' in lifecycle.TRANSITIONS
    if status == schemas.EventStatus.confirmed:
        assert lifecycle.target('approved_change', status).value == 'planning'
        assert lifecycle.allowed_from('approved_change') == ['confirmed']
    else:
        with pytest.raises(EventTransitionError): lifecycle.target('approved_change', status)

@pytest.mark.parametrize('name,field', [('SafetyApproveRequest','comment'),('SafetyChangesRequest','comment'),('SafetyRejectRequest','reason')])
@pytest.mark.parametrize('text', ['', '   ', 'x'*1001])
def test_decision_text_validation(name, field, text):
    assert hasattr(schemas, name)
    with pytest.raises(ValidationError): getattr(schemas,name)(**{field:text})

@pytest.mark.parametrize('name,field', [('SafetyChangesRequest','comment')])
def test_decision_ids_are_unique_and_text_trimmed(name, field):
    assert hasattr(schemas,name)
    uid = 'a0000000-0000-4000-8000-000000000001'
    result = getattr(schemas,name)(**{field:'  private  ', 'booking_ids':[uid,uid], 'equipment_request_ids':[uid,uid]})
    assert getattr(result,field) == 'private'
    assert result.booking_ids == result.equipment_request_ids == [UUID(uid)]

@pytest.mark.parametrize('method,rpc,args,kwargs', [
 ('safety_approve','safety_approve_event',('e','a',3),dict(comment=None,organiser_message='o',staff_message='s')),
 ('safety_return','safety_return_event',('e','a',3),dict(decision='changes_requested',comment='c',booking_ids=['b'],equipment_request_ids=['q'],coordinator_message='m')),
 ('return_to_planning','return_event_to_planning',('e',3),dict(from_status='confirmed',reason_code='booking_cancelled',coordinator_message='m',officer_message=None)),
])
def test_safety_rpc_contract(monkeypatch,method,rpc,args,kwargs):
    assert hasattr(repository,method)
    client = RpcClient([{'id':'e'}])
    monkeypatch.setattr(repository,'get_supabase_admin_client',lambda:client)
    fn = getattr(repository,method)
    assert fn(*args,**kwargs) == {'id':'e'}
    expected = {'p_event_id':'e','p_expected_version':3, **{'p_'+k:v for k,v in kwargs.items()}}
    if method != 'return_to_planning': expected['p_actor_id']='a'
    assert client.calls == [(rpc,expected)]
    client.rows=[]
    assert fn(*args,**kwargs) is None

@pytest.mark.parametrize('domain', ['venues','equipment'])
def test_arrangement_ids_include_inactive_records(monkeypatch,domain):
    from app.modules.venues import service as venues
    from app.modules.equipment import service as equipment
    module = venues if domain=='venues' else equipment
    name = 'event_booking_ids' if domain=='venues' else 'event_request_ids'
    assert hasattr(module,name)
    client=__import__('unittest.mock',fromlist=['MagicMock']).MagicMock()
    query=client.table.return_value
    query.select.return_value=query
    query.eq.return_value=query
    query.execute.return_value.data=[{'id':'one'},{'id':'two'}]
    if domain=='venues':
        monkeypatch.setattr(module.repository,'get_supabase_admin_client',lambda:client)
    else:
        monkeypatch.setattr(module.repository,'list_event_requests',lambda _:[{'id':'one'},{'id':'two'}])
    assert getattr(module,name)('e') == {'one','two'}
    if domain=='venues':
        query.eq.assert_called_once_with('event_id','e')
        query.in_.assert_not_called()


def test_queue_uses_latest_history_and_excludes_other_statuses(monkeypatch):
    assert hasattr(repository,'list_safety_queue')
    from unittest.mock import MagicMock
    from types import SimpleNamespace
    client=MagicMock()
    events=client.table.return_value
    events.select.return_value=events
    events.eq.return_value=events
    events.in_.return_value=events
    events.order.return_value=events
    events.execute.side_effect=[SimpleNamespace(data=[{'id':'a','name':'A','status':'safety_review','organiser':{'full_name':'Org'}},{'id':'b','name':'B','status':'safety_review'}]),SimpleNamespace(data=[{'event_id':'a','at':'2026-10-09T03:00:00Z'},{'event_id':'b','at':'2026-10-09T02:00:00Z'},{'event_id':'a','at':'2026-10-09T01:00:00Z'}])]
    monkeypatch.setattr(repository,'get_supabase_admin_client',lambda:client)
    rows=repository.list_safety_queue()
    assert [r['event_id'] for r in rows]==['b','a']
    assert rows[1]['entered_review_at']=='2026-10-09T03:00:00Z'
    assert rows[1]['organiser_name']=='Org'
    assert ('status','safety_review') in [c.args for c in events.eq.call_args_list]
    assert ('to_status','safety_review') in [c.args for c in events.eq.call_args_list]
    events.execute.side_effect=[SimpleNamespace(data=[])]
    assert repository.list_safety_queue()==[]


def test_decisions_embed_decider_and_sort_newest(monkeypatch):
    assert hasattr(repository,'list_safety_decisions')
    from unittest.mock import MagicMock
    client=MagicMock();query=client.table.return_value
    query.select.return_value=query;query.eq.return_value=query;query.order.return_value=query
    query.execute.return_value.data=[{'id':'d','decider':{'full_name':'Officer'}},{'id':'e','decider':None}]
    monkeypatch.setattr(repository,'get_supabase_admin_client',lambda:client)
    assert repository.list_safety_decisions('event')==[{'id':'d','decided_by_name':'Officer'},{'id':'e','decided_by_name':None}]
    query.order.assert_called_with('decided_at',desc=True)
    assert 'profiles!event_safety_decisions_decided_by_fkey(full_name)' in query.select.call_args.args[0]

@pytest.mark.parametrize('domain',['venues','equipment'])
def test_review_arrangement_reads(monkeypatch,domain):
    from app.modules.venues import service as venues
    from app.modules.equipment import service as equipment
    from unittest.mock import MagicMock
    module=venues if domain=='venues' else equipment
    name='event_bookings_with_venues' if domain=='venues' else 'event_lines'
    assert hasattr(module,name)
    if domain=='venues':
        client=MagicMock();query=client.table.return_value
        query.select.return_value=query;query.eq.return_value=query;query.in_.return_value=query
        query.execute.return_value.data=[{'id':'b','venue_id':'v','status':'approved','venues':{'name':'Hall','capacity':20,'venue_layouts':[{'layout':'boardroom','capacity_for_layout':20}],'accessibility_features':['ramp']}}]
        monkeypatch.setattr(module.repository,'get_supabase_admin_client',lambda:client)
        assert module.event_bookings_with_venues('e')==[dict(booking_id='b',venue_id='v',booking_status='approved',venue_name='Hall',capacity=20,layouts=['boardroom'],accessibility_features=['ramp'])]
        query.in_.assert_called_once_with('status',['held','approved','re_review'])
        assert 'venue_layouts(layout)' in query.select.call_args.args[0]
    else:
        monkeypatch.setattr(module.repository,'list_event_requests',lambda _:[{'id':'q','equipment':{'name':'Mic'},'quantity':2,'status':'pending'}])
        assert module.event_lines('e')==[dict(id='q',equipment_name='Mic',quantity=2,status='pending')]


def test_reject_text_trimmed_and_legacy_arrays_ignored():
    uid='a0000000-0000-4000-8000-000000000001'
    result=schemas.SafetyRejectRequest(reason='  private  ',booking_id=uid,booking_ids=[uid],equipment_request_ids=[uid])
    assert result.reason=='private' and result.booking_id==UUID(uid)
    assert result.model_dump().keys()=={'reason','booking_id'}

def test_approved_change_sources_until_68_lands():
    # CR-104 AC6: add preparation here when 68 AC8 creates it.
    assert lifecycle.allowed_from('approved_change') == ['confirmed']
    assert 'preparation' not in {s.value for s in schemas.EventStatus}
