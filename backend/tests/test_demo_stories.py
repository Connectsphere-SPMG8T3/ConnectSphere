"""demo_stories.py's event lifecycle helper for the live demo: which API calls each
stage makes, in order, without live API access (an httpx mock transport answers)."""

import httpx
import pytest

from scripts import demo_stories
from scripts.verify_live import Context


@pytest.fixture()
def calls(monkeypatch):
    sent = []

    def handler(request):
        path = request.url.path.removeprefix("/api/v1")
        sent.append((request.method, path))
        if path == "/auth/login":
            return httpx.Response(200, json={"access_token": "t", "refresh_token": "r"})
        return httpx.Response(201, json={"id": "x", "lines": [{"id": "l"}], "status": "held"})

    client = httpx.Client(transport=httpx.MockTransport(handler), base_url="http://api")
    ctx = Context(api="http://api/api/v1", client=client)
    monkeypatch.setattr(demo_stories, "_sessions", {})
    return sent, ctx


def steps(sent):
    return [(m, p.replace("/x", "/{id}").replace("/l/", "/{line}/")) for m, p in sent if p != "/auth/login"]


def test_planning_stops_before_any_venue_request(calls):
    sent, ctx = calls
    demo_stories.build_event(ctx, "34", "Approve me", "planning", day=0)
    assert steps(sent) == [
        ("POST", "/events"),
        ("POST", "/events/{id}/submit"),
        ("POST", "/events/{id}/assign"),
        ("POST", "/events/{id}/approve"),
    ]


def test_draft_only_creates(calls):
    sent, ctx = calls
    demo_stories.build_event(ctx, "9", "Draft", "draft", day=0)
    assert steps(sent) == [("POST", "/events")]


def test_held_extends_the_hold_past_the_presentation(calls):
    sent, ctx = calls
    demo_stories.build_event(ctx, "36", "Approve hold", "held", day=0)
    assert steps(sent)[-2:] == [("POST", "/venue-bookings"), ("PATCH", "/venue-bookings/{id}/expiry")]


def test_relative_events_keep_the_default_hold_expiry(calls):
    sent, ctx = calls
    demo_stories.build_event(ctx, "90", "Soon", "held", day=2, relative=True)
    assert steps(sent)[-1] == ("POST", "/venue-bookings")


def test_confirmed_passes_every_arrangement_and_the_safety_check(calls):
    sent, ctx = calls
    demo_stories.build_event(ctx, "85", "Cancel booking", "confirmed", day=0)
    assert steps(sent)[4:] == [
        ("POST", "/venue-bookings"),
        ("PATCH", "/venue-bookings/{id}/expiry"),
        ("POST", "/venue-bookings/{id}/approve"),
        ("POST", "/equipment/requests"),
        ("POST", "/equipment/requests/{line}/reserve"),
        ("PUT", "/equipment/events/{id}/exit-confirmation"),
        ("POST", "/events/{id}/send-for-safety-check"),
        ("POST", "/events/{id}/safety-approve"),
    ]


def test_without_equipment_the_ready_stage_makes_no_equipment_calls(calls):
    sent, ctx = calls
    demo_stories.build_event(ctx, "82", "No kit", "ready", day=0, equipment=())
    assert not [p for _, p in steps(sent) if p.startswith("/equipment")]


def test_preparation_records_venue_preparation(calls):
    sent, ctx = calls
    demo_stories.build_event(ctx, "CR-111", "Prep", "preparation", day=0)
    assert steps(sent)[-1] == ("PUT", "/venue-bookings/{id}/preparation")


def test_unknown_stage_is_refused(calls):
    _, ctx = calls
    with pytest.raises(ValueError, match="unknown stage"):
        demo_stories.build_event(ctx, "1", "x", "approved", day=0)
