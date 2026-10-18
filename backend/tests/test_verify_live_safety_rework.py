"""The CR-104 live probes target missing ids and never mutate shared fixtures."""
from types import SimpleNamespace
import httpx
import pytest
from scripts import verify_live as live


def probe(case_id, handler):
    matches=[check for check in live.API_CHECKS if check.case_id==case_id]
    assert len(matches)==1, f'{case_id} must be registered'
    roles=[]
    def shared(role):
        roles.append(role)
        return SimpleNamespace(headers={'Authorization':role})
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        matches[0].run(SimpleNamespace(api='https://example.invalid/api/v1',client=client,shared=shared))
    return roles


def test_mark_revised_role_denials_use_all_non_coordinator_sessions():
    requests=[]
    def respond(request):
        requests.append(request)
        assert request.method=='POST' and request.url.path.endswith('/mark-revised')
        assert '00000000-0000-4000-8000-000000000000' in request.url.path
        return httpx.Response(403)
    roles=probe('TC-SDEC-022',respond)
    assert set(roles)==(set(live.ACCOUNTS)|set(live.W7_STAFF_ACCOUNTS))-{'event_coordinator'}
    assert len(requests)==len(roles)


def test_mark_revised_missing_booking_uses_coordinator_only():
    def respond(request):
        assert request.method=='POST' and request.url.path.endswith('/mark-revised')
        assert '00000000-0000-4000-8000-000000000000' in request.url.path
        return httpx.Response(404)
    assert probe('TC-SDEC-023',respond)==['event_coordinator']


def test_legacy_reject_arrays_are_probed_and_text_checks_supply_booking_id():
    import json
    requests=[]
    def respond(request):
        body=json.loads(request.content)
        requests.append((request.url.path,body))
        return httpx.Response(422)
    probe('TC-SDEC-016',respond)
    rejects=[body for path,body in requests if path.endswith('/safety-reject')]
    assert any('booking_ids' in body and 'booking_id' not in body for body in rejects)
    assert all('booking_id' in body for body in rejects if body['reason'].strip()=='' or len(body['reason'])>1000)


def test_other_safety_probes_use_the_new_valid_reject_shape():
    for action,body in live.SAFETY_DECISIONS:
        if action=='safety-reject':
            assert set(body)=={'reason','booking_id'}
