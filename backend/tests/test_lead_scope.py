"""CR-101 AC5: which events a Lead sees. Pure rules, no I/O."""

from app.modules.events.lead_scope import active_counts, in_lead_scope

ME = "lead-1"
OTHER = "lead-2"
LEADS = {ME, OTHER}


def row(coordinator_id, assigned_by):
    return {"coordinator_id": coordinator_id, "assigned_by": assigned_by}


def test_every_lead_sees_the_unassigned_queue():
    assert in_lead_scope(row(None, None), ME, LEADS)
    assert in_lead_scope(row(None, OTHER), ME, LEADS)


def test_a_lead_sees_events_they_assigned_or_last_reassigned():
    assert in_lead_scope(row("c1", ME), ME, LEADS)


def test_a_lead_does_not_see_events_another_current_lead_assigned():
    assert not in_lead_scope(row("c1", OTHER), ME, LEADS)


def test_events_assigned_before_the_lead_role_existed_are_visible_to_every_lead():
    assert in_lead_scope(row("c1", None), ME, LEADS)
    assert in_lead_scope(row("c1", None), OTHER, LEADS)


def test_with_a_single_lead_they_see_everything():
    assert in_lead_scope(row("c1", ME), ME, {ME})
    assert in_lead_scope(row("c1", None), ME, {ME})


def test_events_assigned_by_someone_who_is_no_longer_a_lead_are_not_orphaned():
    assert in_lead_scope(row("c1", "former-lead"), ME, LEADS)


def test_active_counts_count_assigned_events_per_coordinator_and_skip_unassigned():
    rows = [row("c1", ME), row("c1", None), row("c2", ME), row(None, None)]
    assert active_counts(rows) == {"c1": 2, "c2": 1}
