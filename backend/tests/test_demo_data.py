"""demo_data.py's story registry, naming, load and reset for the live demo, without
live database or API access: statements are captured, not run."""

import pytest

from scripts import demo_data


@pytest.fixture()
def sql(monkeypatch):
    """Every statement sent; `answers` maps a substring to the rows to return."""
    class Sent(list):
        pass

    sent = Sent()
    answers = {}

    def db_query(statement):
        sent.append(statement)
        for needle, rows in answers.items():
            if needle in statement:
                return rows
        return []

    monkeypatch.setattr(demo_data, "db_query", db_query)
    sent.answers = answers
    return sent


@pytest.fixture()
def registry(monkeypatch, tmp_path):
    built = []
    stories = {}
    monkeypatch.setattr(demo_data, "STORIES", stories)
    monkeypatch.setattr(demo_data, "LOADED_FILE", tmp_path / "loaded.json")

    def add(story_id):
        def build(ctx):
            built.append(story_id)
            return {"event": f"{story_id}-event"}
        stories[story_id] = demo_data.Story(story_id, "title", build)

    return add, built


def test_demo_name():
    assert demo_data.demo_name("CR-99", "Held booking") == "Demo · CR-99 · Held booking"


def test_demo_start_is_singapore_time_from_1_december():
    assert demo_data.demo_start(0, 10, 2) == ("2026-12-01T10:00:00+08:00", "2026-12-01T12:00:00+08:00")
    assert demo_data.demo_start(3, 23, 2) == ("2026-12-04T23:00:00+08:00", "2026-12-05T01:00:00+08:00")


def test_relative_demo_start_counts_from_today(monkeypatch):
    monkeypatch.setattr(demo_data, "today_sgt", lambda: demo_data.date(2026, 11, 10))
    assert demo_data.demo_start(1, 9, 1, relative=True) == ("2026-11-11T09:00:00+08:00", "2026-11-11T10:00:00+08:00")


def test_load_builds_each_story_and_records_it(sql, registry):
    add, built = registry
    add("55")
    result = demo_data.load(object())
    assert built == ["55"]
    assert result == {"55": {"event": "55-event"}}
    assert "55-event" in demo_data.LOADED_FILE.read_text()


def test_load_skips_a_story_already_loaded(sql, registry):
    add, built = registry
    add("55")
    sql.answers["Demo · 55 · %"] = [{"name": "Demo · 55 · Withdraw"}]
    demo_data.load(object())
    assert built == []


def test_load_names_the_story_that_failed(sql, registry):
    add, _ = registry

    def broken(ctx):
        raise demo_data.CheckFailed("expected 201, got 409")

    demo_data.STORIES["CR-99"] = demo_data.Story("CR-99", "title", broken)
    with pytest.raises(SystemExit, match="CR-99: expected 201, got 409"):
        demo_data.load(object())


def test_unknown_story_id_is_refused(sql, registry):
    with pytest.raises(SystemExit, match="no demo story 999"):
        demo_data.load(object(), ["999"])


def test_reset_deletes_only_that_story(sql, registry):
    add, built = registry
    add("55")
    demo_data.reset(object(), ["55"])
    deletes = [s for s in sql if s.lstrip().lower().startswith("delete")]
    assert deletes and all("Demo · 55 · %" in s or "demo+55@" in s or "demo+55-%" in s for s in deletes)
    assert built == ["55"]


def test_delete_story_removes_bookings_before_events(sql):
    demo_data.delete_story("CR-99")
    bookings = next(i for i, s in enumerate(sql) if "delete from public.venue_bookings" in s)
    events = next(i for i, s in enumerate(sql) if "delete from public.events" in s)
    assert bookings < events


def test_delete_story_removes_its_sign_up_account(sql):
    demo_data.delete_story("CR-99")
    assert any("delete from auth.users" in s and "demo+cr-99@connectsphere.dev" in s for s in sql)


def test_delete_story_removes_its_extra_attendee_accounts(sql):
    """Waitlist and registration stories sign up demo+<id>-a@…, demo+<id>-b@… attendees."""
    demo_data.delete_story("86")
    assert any("delete from auth.users" in s and "demo+86-%@connectsphere.dev" in s for s in sql)
    assert demo_data.demo_email("86", "a") == "demo+86-a@connectsphere.dev"
