"""The CR-104 live probes target missing ids and never mutate shared fixtures."""
import json
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
        assert json.loads(request.content) == {'note': 'live check'}
        assert '00000000-0000-4000-8000-000000000000' in request.url.path
        return httpx.Response(403)
    roles=probe('TC-SDEC-022',respond)
    assert set(roles)==(set(live.ACCOUNTS)|set(live.W7_STAFF_ACCOUNTS))-{'event_coordinator'}
    assert len(requests)==len(roles)


def test_mark_revised_missing_booking_uses_coordinator_only():
    def respond(request):
        assert request.method=='POST' and request.url.path.endswith('/mark-revised')
        assert json.loads(request.content) == {'note': 'live check'}
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
    # CR-108: the text under test is the organiser comment; a private note alone is probed too.
    assert all('booking_id' in body for body in rejects if body.get('organiser_comment', '').strip()=='' or len(body.get('organiser_comment', ''))>1000)
    assert any('organiser_comment' not in body and 'private_note' in body for body in rejects)


def test_other_safety_probes_use_the_new_valid_reject_shape():
    for action,body in live.SAFETY_DECISIONS:
        if action=='safety-reject':
            assert set(body)=={'organiser_comment','booking_id'}


def test_revision_followup_live_check_uses_note_and_named_history(monkeypatch):
    monkeypatch.setattr(live, 'safety_rejection_followup_fixture', lambda *a: ('event', 'old', 'venue'), raising=False)
    monkeypatch.setattr(live, 'db_query', lambda _: [{'name': 'Throwaway Hall'}])
    seen = []
    def respond(request):
        seen.append(request)
        if request.url.path.endswith('/safety-reject'):
            assert json.loads(request.content) == {'booking_id': 'old', 'organiser_comment': 'live check exits', 'checklist': live.safety_checklist(['old'])}
            return httpx.Response(200)
        if request.url.path.endswith('/mark-revised'):
            note = json.loads(request.content)['note']
            return httpx.Response(422 if not note.strip() else 200)
        assert request.url.path.endswith('/safety-decisions')
        return httpx.Response(200, json=[{'decision': 'arrangement_rejected',
            'rejected_venues': [{'venue_name': 'Throwaway Hall'}], 'revision': {'note': 'live check revised'}}])
    assert probe('TC-SDEC-031', respond) == ['safety_officer', 'event_coordinator']
    assert [json.loads(r.content)['note'] for r in seen if r.url.path.endswith('/mark-revised')] == ['   ', 'live check revised']


def test_replacement_followup_live_check_refuses_revision_and_checks_release(monkeypatch):
    monkeypatch.setattr(live, 'safety_rejection_followup_fixture', lambda *a: ('event', 'old', 'venue'), raising=False)
    monkeypatch.setattr(live, 'throwaway_venue', lambda *a: 'new-venue')
    monkeypatch.setattr(live, 'db_query', lambda _: [
        {'id': 'old', 'status': 'released', 'flag': 'safety_rejected'},
        {'id': 'new', 'status': 'approved', 'flag': None}])
    def respond(request):
        path = request.url.path
        if path.endswith('/safety-reject'):
            return httpx.Response(200)
        if path.endswith('/venue-bookings'):
            assert json.loads(request.content) == {'event_id': 'event', 'venue_id': 'new-venue', 'replaces_booking_id': 'old'}
            return httpx.Response(201, json={'id': 'new'})
        if path.endswith('/mark-revised'):
            assert json.loads(request.content)['note'] == 'live check revised'
            return httpx.Response(409, json={'detail': 'A replacement venue has been requested for this booking.'})
        assert path.endswith('/new/approve')
        return httpx.Response(200)
    assert probe('TC-SDEC-032', respond) == ['safety_officer', 'event_coordinator', 'venue_staff']
