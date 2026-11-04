"""Build each story's starting state for the live demo.

Run after `demo_db.py swap`, from backend/ with the backend running on this branch:

    python scripts/demo_data.py --load              # every story not loaded yet
    python scripts/demo_data.py --reset 55 CR-99    # delete those stories' records and build them again
    python scripts/demo_data.py --reset             # every story

Every record a story creates is named `Demo · <ID> · <what it is>`, so it can't be
mistaken for seed data and the live checks' cleanup (`live-check …`) never deletes
it. One story's records are separate from another's, so demonstrating one story
never uses up another's starting state. States are reached through the API, signed
in as the seeded accounts, so their history and notifications are real; SQL only
for plain fixtures with no endpoint behind them.

Dates start on 1 Dec 2026 (after the presentation) unless a story's acceptance
criteria depend on time relative to now, in which case it is loaded on the day.
What was built is written to ~/connectsphere-demo/loaded.json.
"""

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Callable

import httpx

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.verify_live import SGT, CheckBlocked, CheckFailed, Context, db_query

DEMO_PREFIX = "Demo · "
DEMO_EMAIL_DOMAIN = "@connectsphere.dev"
FIRST_DEMO_DAY = date(2026, 12, 1)
LOADED_FILE = Path.home() / "connectsphere-demo" / "loaded.json"


@dataclass
class Story:
    id: str
    title: str
    build: Callable[[Context], dict]
    time_relative: bool = False


STORIES: dict[str, Story] = {}


def story(story_id: str, title: str, *, time_relative: bool = False):
    def register(build: Callable[[Context], dict]) -> Callable[[Context], dict]:
        STORIES[story_id] = Story(story_id, title, build, time_relative)
        return build
    return register


def demo_name(story_id: str, label: str) -> str:
    return f"{DEMO_PREFIX}{story_id} · {label}"


def demo_email(story_id: str) -> str:
    """The address a sign-up story's card has the presenter type, deleted on reset."""
    return f"demo+{story_id.lower()}{DEMO_EMAIL_DOMAIN}"


def today_sgt() -> date:
    return datetime.now(SGT).date()


def demo_start(days: int, hour: int, duration_h: int, *, relative: bool = False) -> tuple[str, str]:
    """An event window in Singapore time, `days` after 1 Dec 2026 (or after today)."""
    first = today_sgt() if relative else FIRST_DEMO_DAY
    start = datetime.combine(first + timedelta(days=days), time(hour), SGT)
    return start.isoformat(), (start + timedelta(hours=duration_h)).isoformat()


def _pattern(story_id: str) -> str:
    return f"{DEMO_PREFIX}{story_id} · %"


def is_loaded(story_id: str) -> bool:
    pattern = _pattern(story_id)
    return bool(db_query(
        f"select name from public.events where name like '{pattern}' union all "
        f"select name from public.venues where name like '{pattern}' union all "
        f"select name from public.equipment where name like '{pattern}' limit 1"
    ))


def delete_story(story_id: str) -> int:
    """Deletes a story's records: bookings before their events and venues (those
    foreign keys restrict), then blocks, events, equipment, venues and its sign-up
    account. History, notifications, layouts and reservations cascade."""
    pattern = _pattern(story_id)
    events = f"select id from public.events where name like '{pattern}'"
    venues = f"select id from public.venues where name like '{pattern}'"
    db_query(f"delete from public.venue_bookings where event_id in ({events}) or venue_id in ({venues})")
    db_query(f"delete from public.venue_blocks where notes like '{pattern}'")
    deleted = len(db_query(f"delete from public.events where name like '{pattern}' returning id"))
    db_query(f"delete from public.equipment where name like '{pattern}'")
    db_query(f"delete from public.venues where name like '{pattern}'")
    db_query(f"delete from auth.users where email = '{demo_email(story_id)}'")
    return deleted


def _selected(ids: list[str] | None) -> list[Story]:
    for story_id in ids or []:
        if story_id not in STORIES:
            raise SystemExit(f"no demo story {story_id}")
    return [STORIES[i] for i in ids] if ids else list(STORIES.values())


def load(ctx: Context, ids: list[str] | None = None) -> dict[str, dict]:
    built = json.loads(LOADED_FILE.read_text()) if LOADED_FILE.exists() else {}
    for item in _selected(ids):
        if is_loaded(item.id):
            continue
        try:
            built[item.id] = item.build(ctx)
        except (CheckFailed, CheckBlocked, httpx.HTTPError) as error:
            raise SystemExit(f"{item.id}: {error}") from error
        LOADED_FILE.parent.mkdir(parents=True, exist_ok=True)
        LOADED_FILE.write_text(json.dumps(built, indent=1, ensure_ascii=False))
    return built


def reset(ctx: Context, ids: list[str] | None = None) -> dict[str, dict]:
    for item in _selected(ids):
        delete_story(item.id)
    return load(ctx, ids)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--load", nargs="*", metavar="ID")
    action.add_argument("--reset", nargs="*", metavar="ID")
    parser.add_argument("--api", default="http://localhost:8000/api/v1")
    args = parser.parse_args()

    with httpx.Client(timeout=30) as client:
        ctx = Context(api=args.api, client=client)
        try:
            built = reset(ctx, args.reset) if args.reset is not None else load(ctx, args.load)
        finally:
            ctx.logout_all()
    print(f"{len(built)} stories loaded; details in {LOADED_FILE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
