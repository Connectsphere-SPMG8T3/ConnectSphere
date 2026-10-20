"""113 in-app notifications, through the HTTP API with the repository mocked."""

import base64

import pytest

from app.modules.notifications import repository, service
from tests.test_event_comments_api import acting_as_another_role

USER_ID = "a0000000-0000-4000-8000-000000000002"
OTHER_ID = "a0000000-0000-4000-8000-000000000009"
EVENT_ID = "e0000000-0000-4000-8000-000000000201"
BASE = "/api/v1/notifications"
ALL_ROLES = [
    "event_organiser", "event_coordinator", "event_coordinator_lead",
    "venue_staff", "tech_support", "safety_officer", "attendee",
]


def row(i, role="event_coordinator", read_at=None, created="2026-10-20T03:00:00+00:00"):
    return {"id": f"00000000-0000-4000-8000-{i:012d}", "recipient_id": USER_ID, "recipient_role": role,
            "event_id": EVENT_ID, "type": "event_assigned", "message": f"m{i}", "read_at": read_at,
            "created_at": created}


@pytest.fixture()
def inbox(monkeypatch):
    """In-memory rows; the fake repository applies the same filters the real one must."""
    state = {"rows": [], "calls": []}

    def visible(recipient_id, role):
        return [r for r in state["rows"] if r["recipient_id"] == recipient_id and r["recipient_role"] == role]

    def count_unread(recipient_id, role):
        state["calls"].append(("count", recipient_id, role))
        rows = visible(recipient_id, role)
        return {"count": sum(1 for r in rows if r["read_at"] is None),
                "latest_at": max((r["created_at"] for r in rows), default=None)}

    def list_page(recipient_id, role, limit, before):
        state["calls"].append(("list", recipient_id, role, limit, before))
        rows = sorted(visible(recipient_id, role), key=lambda r: (r["created_at"], r["id"]), reverse=True)
        if before:
            rows = [r for r in rows if (r["created_at"], r["id"]) < before]
        return rows[: limit + 1]

    def mark_read(notification_id, recipient_id, role):
        for r in visible(recipient_id, role):
            if r["id"] == notification_id:
                r["read_at"] = r["read_at"] or "2026-10-20T04:00:00+00:00"
                return True
        return False

    def mark_all_read(recipient_id, role):
        updated = 0
        for r in visible(recipient_id, role):
            if r["read_at"] is None:
                r["read_at"] = "2026-10-20T04:00:00+00:00"
                updated += 1
        return updated

    for name, fn in [("count_unread", count_unread), ("list_page", list_page),
                     ("mark_read", mark_read), ("mark_all_read", mark_all_read)]:
        monkeypatch.setattr(repository, name, fn)
    return state


class TestUnreadCount:
    def test_counts_only_unread_rows_for_the_active_role(self, client, auth_headers, authenticate_as, inbox):
        authenticate_as("event_coordinator", user_id=USER_ID)
        inbox["rows"] = [row(1), row(2, read_at="x"), row(3, role="event_organiser")]

        body = client.get(f"{BASE}/unread-count", headers=auth_headers).json()

        assert body["count"] == 1
        assert body["latest_at"]

    def test_no_rows_means_zero_and_no_latest(self, client, auth_headers, authenticate_as, inbox):
        authenticate_as("event_coordinator", user_id=USER_ID)

        assert client.get(f"{BASE}/unread-count", headers=auth_headers).json() == {"count": 0, "latest_at": None}

    def test_requires_a_session(self, client):
        assert client.get(f"{BASE}/unread-count").status_code == 401

    @pytest.mark.parametrize("role", ALL_ROLES)
    def test_every_role_may_read_its_own(self, client, auth_headers, authenticate_as, inbox, role):
        authenticate_as(role, user_id=USER_ID)

        assert client.get(f"{BASE}/unread-count", headers=auth_headers).status_code == 200


class TestActiveRoleDenial:  # SCRUM-76 and the AGENTS.md security baseline
    def test_a_user_acting_as_another_role_sees_none_of_the_other_roles_rows(
        self, client, auth_headers, monkeypatch, inbox
    ):
        inbox["rows"] = [row(1, role="event_coordinator"), row(2, role="event_organiser")]
        acting_as_another_role(monkeypatch, USER_ID, holds="event_coordinator", acts_as="event_organiser")

        items = client.get(BASE, headers=auth_headers).json()["items"]

        assert [i["message"] for i in items] == ["m2"]
        assert client.get(f"{BASE}/unread-count", headers=auth_headers).json()["count"] == 1

    def test_marking_a_row_of_another_role_is_404_and_changes_nothing(
        self, client, auth_headers, monkeypatch, inbox
    ):
        inbox["rows"] = [row(1, role="event_coordinator")]
        acting_as_another_role(monkeypatch, USER_ID, holds="event_coordinator", acts_as="event_organiser")

        response = client.post(f"{BASE}/{inbox['rows'][0]['id']}/read", headers=auth_headers)

        assert response.status_code == 404
        assert inbox["rows"][0]["read_at"] is None

    def test_read_all_as_another_role_leaves_the_first_roles_rows_unread(
        self, client, auth_headers, monkeypatch, inbox
    ):
        inbox["rows"] = [row(1, role="event_coordinator")]
        acting_as_another_role(monkeypatch, USER_ID, holds="event_coordinator", acts_as="event_organiser")

        assert client.post(f"{BASE}/read-all", headers=auth_headers).json() == {"updated": 0}
        assert inbox["rows"][0]["read_at"] is None


class TestList:
    def test_newest_first_with_link_read_flag_and_no_internal_fields(
        self, client, auth_headers, authenticate_as, inbox
    ):
        authenticate_as("event_coordinator", user_id=USER_ID)
        inbox["rows"] = [row(1, created="2026-10-20T01:00:00+00:00"),
                         row(2, read_at="x", created="2026-10-20T02:00:00+00:00")]

        page = client.get(BASE, headers=auth_headers).json()

        items = page["items"]
        assert [i["message"] for i in items] == ["m2", "m1"]
        assert items[0]["read"] is True and items[1]["read"] is False
        assert items[0]["link"] == f"/coordinator/events/{EVENT_ID}"
        assert set(items[0]) == {"id", "event_id", "type", "message", "link", "read", "created_at"}
        assert page["next_before"] is None

    def test_rows_sharing_a_timestamp_page_without_skips_or_repeats(
        self, client, auth_headers, authenticate_as, inbox
    ):
        authenticate_as("event_coordinator", user_id=USER_ID)
        inbox["rows"] = [row(i) for i in range(1, 6)]  # five rows, one created_at
        seen, cursor = [], None

        for _ in range(10):
            url = f"{BASE}?limit=2" + (f"&before={cursor}" if cursor else "")
            page = client.get(url, headers=auth_headers).json()
            seen += [i["message"] for i in page["items"]]
            cursor = page["next_before"]
            if not cursor:
                break

        assert sorted(seen) == ["m1", "m2", "m3", "m4", "m5"]
        assert len(seen) == 5

    def test_the_default_page_size_is_20(self, client, auth_headers, authenticate_as, inbox):
        authenticate_as("event_coordinator", user_id=USER_ID)

        client.get(BASE, headers=auth_headers)

        assert inbox["calls"][-1][3] == 20

    @pytest.mark.parametrize("query", ["limit=0", "limit=101", "before=garbage"])
    def test_a_bad_query_is_422(self, client, auth_headers, authenticate_as, inbox, query):
        authenticate_as("event_coordinator", user_id=USER_ID)

        assert client.get(f"{BASE}?{query}", headers=auth_headers).status_code == 422

    def test_no_event_id_means_no_link(self, client, auth_headers, authenticate_as, inbox):
        authenticate_as("event_coordinator", user_id=USER_ID)
        inbox["rows"] = [{**row(1), "event_id": None}]

        assert client.get(BASE, headers=auth_headers).json()["items"][0]["link"] is None


class TestMarkRead:
    def test_marks_one_and_is_idempotent(self, client, auth_headers, authenticate_as, inbox):
        authenticate_as("event_coordinator", user_id=USER_ID)
        inbox["rows"] = [row(1)]
        url = f"{BASE}/{inbox['rows'][0]['id']}/read"

        assert client.post(url, headers=auth_headers).json() == {"id": inbox["rows"][0]["id"], "read": True}
        first = inbox["rows"][0]["read_at"]
        assert client.post(url, headers=auth_headers).status_code == 200
        assert inbox["rows"][0]["read_at"] == first

    def test_someone_elses_id_is_404(self, client, auth_headers, authenticate_as, inbox):
        authenticate_as("event_coordinator", user_id=OTHER_ID)
        inbox["rows"] = [row(1)]  # belongs to USER_ID

        assert client.post(f"{BASE}/{inbox['rows'][0]['id']}/read", headers=auth_headers).status_code == 404

    def test_a_malformed_id_is_422(self, client, auth_headers, authenticate_as, inbox):
        authenticate_as("event_coordinator", user_id=USER_ID)

        assert client.post(f"{BASE}/not-a-uuid/read", headers=auth_headers).status_code == 422

    def test_read_all_touches_only_the_callers_rows_in_the_active_role(
        self, client, auth_headers, authenticate_as, inbox
    ):
        authenticate_as("event_coordinator", user_id=USER_ID)
        inbox["rows"] = [row(1), row(2), row(3, role="event_organiser")]

        assert client.post(f"{BASE}/read-all", headers=auth_headers).json() == {"updated": 2}
        assert inbox["rows"][2]["read_at"] is None


class TestLinkFor:
    @pytest.mark.parametrize("role,expected", [
        ("event_organiser", f"/events/{EVENT_ID}"),
        ("event_coordinator", f"/coordinator/events/{EVENT_ID}"),
        ("event_coordinator_lead", f"/lead/events/{EVENT_ID}"),
        ("tech_support", f"/tech-support/events/{EVENT_ID}"),
        ("safety_officer", f"/safety/events/{EVENT_ID}"),
        ("venue_staff", "/dashboard/venue-staff/requests"),
        ("attendee", "/dashboard/attendee"),
    ])
    def test_each_role_links_to_its_own_page(self, role, expected):
        assert service.link_for(role, EVENT_ID) == expected

    @pytest.mark.parametrize("role", ["event_organiser", "event_coordinator", "event_coordinator_lead",
                                      "tech_support", "safety_officer"])
    def test_event_pages_need_an_event(self, role):
        assert service.link_for(role, None) is None

    def test_roles_without_an_event_page_still_link_to_their_queue(self):
        assert service.link_for("venue_staff", None) == "/dashboard/venue-staff/requests"
        assert service.link_for("attendee", None) == "/dashboard/attendee"

    def test_an_unknown_role_has_no_link(self):
        assert service.link_for("nobody", EVENT_ID) is None


class TestCursor:
    def test_round_trips(self):
        cursor = service.encode_cursor("2026-10-20T03:00:00+00:00", "id-1")

        assert service.decode_cursor(cursor) == ("2026-10-20T03:00:00+00:00", "id-1")
        assert "+" not in cursor and " " not in cursor  # safe in a URL query

    @pytest.mark.parametrize("bad", ["", "garbage", "bm90LWEtY3Vyc29y", "%%%"])
    def test_a_malformed_cursor_raises_value_error(self, bad):
        with pytest.raises(ValueError):
            service.decode_cursor(bad)

    @pytest.mark.parametrize("raw", [b"|id-1", b"2026-10-20T03:00:00+00:00|"])
    def test_a_cursor_missing_its_time_or_its_id_raises_value_error(self, raw):
        with pytest.raises(ValueError):
            service.decode_cursor(base64.urlsafe_b64encode(raw).decode())
