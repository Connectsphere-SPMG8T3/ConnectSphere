-- SCRUM-61 event comments: the real function, table constraints and RLS.
-- Run with the Supabase MCP execute_sql or `psql "$DATABASE_URL" -f`. Raises on
-- the first failure and prints COMMENT CHECKS PASSED otherwise. Everything runs
-- inside `begin; ... rollback;`, so the throwaway events leave no trace.
-- Uses the seeded organiser (…0001), coordinator (…0002, who also holds
-- venue_staff) and venue staff (…0003).

begin;

insert into public.events (id, organiser_id, coordinator_id, status, name) values
    ('e0000000-0000-4000-8000-0000000006a1', 'a0000000-0000-4000-8000-000000000001',
     'a0000000-0000-4000-8000-000000000002', 'under_review', 'Comment check (rolled back)'),
    ('e0000000-0000-4000-8000-0000000006a2', 'a0000000-0000-4000-8000-000000000001',
     null, 'under_review', 'Comment check, unassigned (rolled back)'),
    ('e0000000-0000-4000-8000-0000000006a3', 'a0000000-0000-4000-8000-000000000001',
     'a0000000-0000-4000-8000-000000000002', 'draft', 'Comment check, draft (rolled back)'),
    ('e0000000-0000-4000-8000-0000000006a4', 'a0000000-0000-4000-8000-000000000001',
     'a0000000-0000-4000-8000-000000000002', 'rejected', 'Comment check, closed (rolled back)');

do $$
declare
    v_event uuid := 'e0000000-0000-4000-8000-0000000006a1';
    v_organiser uuid := 'a0000000-0000-4000-8000-000000000001';
    v_coordinator uuid := 'a0000000-0000-4000-8000-000000000002';
    v_comment public.event_comments;
    v_rows integer;
    v_before timestamptz := now();
begin
    -- Organiser posts: trimmed, timestamped by the database, coordinator notified.
    select * into v_comment from public.add_event_comment(
        v_event, v_organiser, '  Can we recce the hall on Friday?  ', 'The organiser commented on "Comment check (rolled back)".');
    if v_comment.body is distinct from 'Can we recce the hall on Friday?' or v_comment.author_id is distinct from v_organiser then
        raise exception 'COMMENT FAIL: the organiser''s comment was not stored trimmed with its author';
    end if;
    if v_comment.created_at is null or v_comment.created_at < v_before then
        raise exception 'COMMENT FAIL: created_at was not set by the database';
    end if;
    select count(*) into v_rows from public.notifications
     where event_id = v_event and type = 'comment_added' and recipient_id = v_coordinator;
    if v_rows <> 1 then raise exception 'COMMENT FAIL: the coordinator was not notified exactly once'; end if;
    select count(*) into v_rows from public.notifications
     where event_id = v_event and type = 'comment_added' and recipient_id = v_organiser;
    if v_rows <> 0 then raise exception 'COMMENT FAIL: the organiser was notified of their own comment'; end if;

    -- Coordinator replies: organiser notified.
    perform public.add_event_comment(v_event, v_coordinator, 'Booked for 3pm.', 'Your coordinator commented on "Comment check (rolled back)".');
    select count(*) into v_rows from public.notifications
     where event_id = v_event and type = 'comment_added' and recipient_id = v_organiser;
    if v_rows <> 1 then raise exception 'COMMENT FAIL: the organiser was not notified of the reply'; end if;

    -- No coordinator assigned: the comment is saved, nobody is notified.
    select count(*) into v_rows from public.add_event_comment(
        'e0000000-0000-4000-8000-0000000006a2', v_organiser, 'Anyone there?', 'msg');
    if v_rows <> 1 then raise exception 'COMMENT FAIL: a comment on an unassigned event was refused'; end if;
    select count(*) into v_rows from public.notifications where event_id = 'e0000000-0000-4000-8000-0000000006a2';
    if v_rows <> 0 then raise exception 'COMMENT FAIL: an unassigned event produced a notification'; end if;

    -- Draft and closed events: no row, nothing written.
    select count(*) into v_rows from public.add_event_comment('e0000000-0000-4000-8000-0000000006a3', v_organiser, 'x', 'msg');
    if v_rows <> 0 then raise exception 'COMMENT FAIL: a draft accepted a comment'; end if;
    select count(*) into v_rows from public.add_event_comment('e0000000-0000-4000-8000-0000000006a4', v_organiser, 'x', 'msg');
    if v_rows <> 0 then raise exception 'COMMENT FAIL: a rejected event accepted a comment'; end if;
    select count(*) into v_rows from public.event_comments
     where event_id in ('e0000000-0000-4000-8000-0000000006a3', 'e0000000-0000-4000-8000-0000000006a4');
    if v_rows <> 0 then raise exception 'COMMENT FAIL: a refused comment was stored'; end if;

    -- The table refuses blank and overlong bodies by itself.
    begin
        insert into public.event_comments (event_id, author_id, body) values (v_event, v_organiser, '   ');
        raise exception 'COMMENT FAIL: a blank body was accepted';
    exception when check_violation then null;
    end;
    begin
        insert into public.event_comments (event_id, author_id, body) values (v_event, v_organiser, repeat('x', 1001));
        raise exception 'COMMENT FAIL: a 1001-character body was accepted';
    exception when check_violation then null;
    end;

    -- API-only: not callable by signed-in users.
    if has_function_privilege('authenticated', 'public.add_event_comment(uuid, uuid, text, text)', 'execute') then
        raise exception 'COMMENT FAIL: authenticated can execute add_event_comment';
    end if;
end $$;

-- RLS: the owning organiser, acting as organiser, reads both comments; cannot edit or delete.
select set_config('request.jwt.claims', '{"sub":"a0000000-0000-4000-8000-000000000001","role":"authenticated"}', true);
set local role authenticated;
do $$
declare v_rows integer;
begin
    if (select count(*) from public.event_comments where event_id = 'e0000000-0000-4000-8000-0000000006a1') <> 2 then
        raise exception 'COMMENT FAIL: the owning organiser cannot read the thread';
    end if;
    update public.event_comments set body = 'edited' where event_id = 'e0000000-0000-4000-8000-0000000006a1';
    get diagnostics v_rows = row_count;
    if v_rows <> 0 then raise exception 'COMMENT FAIL: the organiser edited a comment'; end if;
    delete from public.event_comments where event_id = 'e0000000-0000-4000-8000-0000000006a1';
    get diagnostics v_rows = row_count;
    if v_rows <> 0 then raise exception 'COMMENT FAIL: the organiser deleted a comment'; end if;
end $$;
reset role;

-- RLS: the assigned coordinator, acting as coordinator, reads both comments.
select set_config('request.jwt.claims', '{"sub":"a0000000-0000-4000-8000-000000000002","role":"authenticated"}', true);
set local role authenticated;
do $$
begin
    if (select count(*) from public.event_comments where event_id = 'e0000000-0000-4000-8000-0000000006a1') <> 2 then
        raise exception 'COMMENT FAIL: the assigned coordinator cannot read the thread';
    end if;
end $$;
reset role;

-- RLS: the same coordinator account, in a session acting as venue staff, sees nothing (SCRUM-76).
insert into auth.sessions (id, user_id, created_at, updated_at)
values ('c0000000-0000-4000-8000-0000000006c1', 'a0000000-0000-4000-8000-000000000002', now(), now());
insert into public.session_active_roles (session_id, profile_id, role)
values ('c0000000-0000-4000-8000-0000000006c1', 'a0000000-0000-4000-8000-000000000002', 'venue_staff');
select set_config('request.jwt.claims',
    '{"sub":"a0000000-0000-4000-8000-000000000002","role":"authenticated","session_id":"c0000000-0000-4000-8000-0000000006c1"}', true);
set local role authenticated;
do $$
begin
    if (select count(*) from public.event_comments where event_id = 'e0000000-0000-4000-8000-0000000006a1') <> 0 then
        raise exception 'COMMENT FAIL: the coordinator acting as venue staff can read the thread';
    end if;
end $$;
reset role;

-- RLS: an unrelated staff member sees nothing.
select set_config('request.jwt.claims', '{"sub":"a0000000-0000-4000-8000-000000000003","role":"authenticated"}', true);
set local role authenticated;
do $$
begin
    if (select count(*) from public.event_comments where event_id = 'e0000000-0000-4000-8000-0000000006a1') <> 0 then
        raise exception 'COMMENT FAIL: venue staff can read the thread';
    end if;
end $$;
reset role;

select 'COMMENT CHECKS PASSED' as result;
rollback;
