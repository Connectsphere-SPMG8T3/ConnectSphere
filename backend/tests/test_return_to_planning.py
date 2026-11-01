"""CR-104 shared withdrawal contract; no caller wiring."""
from copy import deepcopy
import pytest
from app.modules.events import service, repository, schemas, lifecycle
from tests.test_event_review_api import event_row, EVENT_ID

@pytest.mark.parametrize('source', ['safety_review','confirmed','preparation','draft','submitted','under_review','returned','planning','rejected','cancelled','completed',None])
@pytest.mark.parametrize('reason', ['arrangement_flagged','booking_cancelled','technical_not_ready','approved_details_changed'])
def test_return_contract(monkeypatch,source,reason):
    assert hasattr(service,'return_to_planning')
    row = event_row(source) if source else None
    monkeypatch.setattr(repository,'get_event',lambda _:deepcopy(row))
    calls=[]
    def rpc(*args,**kwargs):
        calls.append((args,kwargs))
        return {**row,'status':'planning','version':4}
    monkeypatch.setattr(repository,'return_to_planning',rpc)
    actions=[]
    original=lifecycle.target
    def target(action,status):
        actions.append(action)
        return original(action,status)
    monkeypatch.setattr(lifecycle,'target',target)
    result=service.return_to_planning(EVENT_ID,reason_code=schemas.ReturnReason(reason),message='SECRET-MARKER',actor_id='ignored')
    # D71: Preparation returns like Confirmed (REQUIREMENTS §6.7 approved_change).
    if source not in ('safety_review','confirmed','preparation'):
        assert result is None and not calls
        return
    assert result.status.value == 'planning'
    assert actions == [('safety_withdraw' if source=='safety_review' else 'approved_change')]
    args,kwargs=calls[0]
    assert args == (EVENT_ID,3)
    assert kwargs['from_status']==source and kwargs['reason_code']==reason
    assert 'Partner Summit' in kwargs['coordinator_message']
    assert 'SECRET-MARKER' not in str(kwargs)
    assert bool(kwargs['officer_message']) == (source=='safety_review')
    monkeypatch.setattr(repository,'return_to_planning',lambda *a,**k:None)
    assert service.return_to_planning(EVENT_ID,reason_code=schemas.ReturnReason(reason)) is None


def test_reason_messages_differ(monkeypatch):
    assert hasattr(service,'return_to_planning')
    monkeypatch.setattr(repository,'get_event',lambda _:event_row('safety_review'))
    messages=[]
    monkeypatch.setattr(repository,'return_to_planning',lambda *a,**k:messages.append(k))
    for reason in schemas.ReturnReason: service.return_to_planning(EVENT_ID,reason_code=reason)
    assert len({x['coordinator_message'] for x in messages})==4
    assert len({x['officer_message'] for x in messages})==4
